# Deployment — Azure Standard_B1s (Ubuntu 22.04/24.04)

One VM runs nginx, the FastAPI API (Uvicorn), the ARQ worker, and PostgreSQL.
Redis is external (Upstash free tier). Everything is supervised by **systemd** —
no PM2/Supervisor needed; systemd is already there, survives reboots, and gives
you journald logs for free.

## 0. Sizing reality check (1 vCPU / 1 GiB RAM)

| Process        | Approx. RSS |
|----------------|-------------|
| PostgreSQL     | ~150 MB (tuned down, see §2) |
| Uvicorn (1 worker) | ~120 MB |
| ARQ worker     | ~110 MB |
| nginx          | ~10 MB  |

That fits, but **add swap first** — a B1s without swap will OOM-kill Postgres
under load:

```bash
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

## 1. Provision

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3.12-venv python3-pip postgresql nginx git ufw

# Dedicated non-login user; code lives in /opt/jobsearch
sudo useradd --system --create-home --shell /usr/sbin/nologin jobsearch
sudo git clone https://github.com/<you>/Job-Search-Platform.git /opt/jobsearch
sudo chown -R jobsearch:jobsearch /opt/jobsearch
```

Firewall — only SSH and HTTP(S) are reachable; Postgres and Uvicorn bind to
localhost and are never exposed:

```bash
sudo ufw allow OpenSSH && sudo ufw allow 'Nginx Full' && sudo ufw enable
```

## 2. PostgreSQL

```bash
sudo -u postgres psql -c "CREATE USER jobsearch WITH PASSWORD '<strong-pw>';"
sudo -u postgres psql -c "CREATE DATABASE jobsearch OWNER jobsearch;"
sudo -u postgres psql -d jobsearch -c "CREATE EXTENSION IF NOT EXISTS citext;"
sudo -u jobsearch psql -d jobsearch -f /opt/jobsearch/db/schema.sql
```

Tune for 1 GiB total RAM (`/etc/postgresql/16/main/conf.d/lowmem.conf`):

```
shared_buffers = 128MB
work_mem = 4MB
maintenance_work_mem = 32MB
max_connections = 30
```

## 3. Backend environment

```bash
cd /opt/jobsearch/backend
sudo -u jobsearch python3 -m venv .venv
sudo -u jobsearch .venv/bin/pip install -r requirements.txt
sudo -u jobsearch cp .env.example .env
sudo nano /opt/jobsearch/backend/.env      # fill in real secrets
sudo chmod 600 /opt/jobsearch/backend/.env # secrets readable by owner only
sudo chown jobsearch:jobsearch /opt/jobsearch/backend/.env
```

## 4. systemd services (24/7 supervision)

```bash
sudo cp /opt/jobsearch/deploy/jobsearch-api.service    /etc/systemd/system/
sudo cp /opt/jobsearch/deploy/jobsearch-worker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now jobsearch-api jobsearch-worker
```

`Restart=always` + `RestartSec=3` means a crash (or an OOM kill) restarts the
process within seconds; `enable` means both come back after a VM reboot.
`After=postgresql.service` orders startup correctly.

Operations cheat sheet:

```bash
systemctl status jobsearch-api jobsearch-worker
journalctl -u jobsearch-api -f          # live API logs
journalctl -u jobsearch-worker --since "1 hour ago"
sudo systemctl restart jobsearch-api    # after a deploy
```

Deploying a new version:

```bash
cd /opt/jobsearch && sudo -u jobsearch git pull
sudo -u jobsearch backend/.venv/bin/pip install -r backend/requirements.txt
sudo systemctl restart jobsearch-api jobsearch-worker
```

## 5. nginx + TLS

```bash
sudo cp /opt/jobsearch/deploy/nginx-jobsearch.conf /etc/nginx/sites-available/jobsearch
sudo ln -s /etc/nginx/sites-available/jobsearch /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx

# Free TLS (required for the Telegram webhook):
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d api.<your-domain>
```

No domain? Point a free DuckDNS subdomain at the VM's public IP — Telegram
webhooks require valid HTTPS.

## 6. Telegram webhook registration (one-time)

```bash
curl "https://api.telegram.org/bot<BOT_TOKEN>/setWebhook" \
  -d "url=https://api.<your-domain>/telegram/webhook" \
  -d "secret_token=<TELEGRAM_WEBHOOK_SECRET from .env>"
```

Telegram now POSTs updates to FastAPI; the handler rejects any request whose
`X-Telegram-Bot-Api-Secret-Token` header doesn't match.

## 7. Discord community channel (one-time)

In your Discord server: **Server Settings → Integrations → Webhooks →
New Webhook**, pick the jobs channel, copy the URL into
`DISCORD_WEBHOOK_URL` in `.env`, then `sudo systemctl restart jobsearch-worker`.
That's the whole integration — the worker POSTs every newly found student job
to the channel; there is no Discord bot process to host.

## 8. Frontend (Vercel)

The SPA is static — deploy `frontend/` on Vercel (free), set
`VITE_API_BASE_URL=https://api.<your-domain>`, and add the Vercel URL to
`CORS_ORIGINS` in the backend `.env`.
