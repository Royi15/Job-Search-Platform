# Frontend — React (Vite + TypeScript) SPA

The complete web app: public landing page + the logged-in dashboard.
Deployed on Vercel; talks to the FastAPI backend over HTTPS.

## Run it

```bash
npm install
cp .env.example .env.local     # points at http://localhost:8000 by default
npm run dev                    # http://localhost:5173
```

`npm run build` type-checks (strict) and produces `dist/`.

## Pages

| Route              | What it is                                                        |
|--------------------|-------------------------------------------------------------------|
| `/`                | Landing page (hero + features + how-it-works), links to sign-up   |
| `/login` `/register` | Email/password auth against `/auth/*`                           |
| `/app`             | **Board** — drag-and-drop Kanban (dnd-kit), add/delete cards      |
| `/app/alerts`      | Matched jobs feed; "I applied ✅" copies a job onto the board      |
| `/app/preferences` | Saved-search CRUD (title/must/exclude keywords, locations)        |
| `/app/resumes`     | PDF upload + "what the ATS sees" skills view (polls while parsing)|
| `/app/tailor`      | ATS Tailor: JD in → gap, before/after score, sentence rewrites    |
| `/app/cover-letter`| Cover letter / LinkedIn message generator with copy button        |
| `/app/settings`    | Telegram deep-link account linking, Discord feed info             |

## Structure

```
src/
├── api/client.ts        # axios: base URL, bearer header, silent 401→refresh→retry
├── api/types.ts         # mirrors the backend Pydantic schemas
├── auth/AuthContext.tsx # user state, login/register/logout
├── pages/               # Landing, AuthPage, AppLayout (sidebar shell)
└── features/            # one folder per product feature
    ├── board/           # Kanban: optimistic move + rollback on error
    ├── alerts/  preferences/  resumes/  settings/
    └── ai/              # Tailor, CoverLetter + useGeneration polling hook
```

Conventions: async AI work returns 202 from the API — the `useGeneration`
hook polls `/ai/generations/{id}` every 2.5 s until `done`/`failed`. Board
drag-and-drop updates state optimistically and rolls back if the API call
fails. Tokens live in localStorage; the axios interceptor refreshes the
access token transparently.

## Deploy (Vercel)

Import the repo, set root directory to `frontend/`, add env var
`VITE_API_BASE_URL=https://api.<your-domain>` — then add the Vercel URL to
`CORS_ORIGINS` in the backend `.env`.
