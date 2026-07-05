import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "../../api/client";
import type { Alert } from "../../api/types";

export default function AlertsFeed() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    api.get<Alert[]>("/alerts").then((r) => {
      setAlerts(r.data);
      setLoaded(true);
    });
  }, []);

  async function applied(alert: Alert) {
    await api.post(`/applications/from-alert/${alert.id}`);
    setAlerts(alerts.filter((a) => a.id !== alert.id));
  }

  async function dismiss(alert: Alert) {
    await api.post(`/alerts/${alert.id}/dismiss`);
    setAlerts(alerts.filter((a) => a.id !== alert.id));
  }

  return (
    <div>
      <h1>Job Alerts</h1>
      <p className="page-sub">
        Jobs that matched your <Link to="/app/preferences" style={{ color: "var(--blue)" }}>preferences</Link>.
        The worker checks LinkedIn every hour; matches also arrive on Telegram.
      </p>
      {loaded && alerts.length === 0 && (
        <div className="empty">
          No matches yet. Make sure you created at least one active search
          preference — new student jobs are checked against it every hour.
        </div>
      )}
      <div className="stack">
        {alerts.map((alert) => (
          <div className="panel" key={alert.id}>
            <h3>{alert.job.title}</h3>
            <div className="meta">
              {alert.job.company ?? "Unknown company"}
              {alert.job.location ? ` · ${alert.job.location}` : ""}
              {alert.job.is_remote ? " · Remote" : ""} · found{" "}
              {new Date(alert.matched_at).toLocaleString()}
            </div>
            <div className="actions">
              <a className="btn btn-ghost btn-sm" href={alert.job.url} target="_blank" rel="noreferrer">
                View posting ↗
              </a>
              <button className="btn btn-yellow btn-sm" onClick={() => applied(alert)}>
                I applied ✅ — add to board
              </button>
              <button className="btn btn-ghost btn-sm" onClick={() => dismiss(alert)}>
                Dismiss
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
