import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

const NAV = [
  { to: "/app", label: "📋 Board", end: true },
  { to: "/app/alerts", label: "🔔 Job Alerts" },
  { to: "/app/preferences", label: "🎯 Preferences" },
  { to: "/app/resumes", label: "📄 Resumes" },
  { to: "/app/tailor", label: "🛡️ ATS Tailor" },
  { to: "/app/cover-letter", label: "✨ Cover Letter" },
  { to: "/app/settings", label: "⚙️ Settings" },
];

export default function AppLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          Job<span style={{ color: "var(--yellow)" }}>Pilot</span>
        </div>
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) => (isActive ? "active" : "")}
          >
            {item.label}
          </NavLink>
        ))}
        <div className="spacer" />
        <div className="user">{user?.email}</div>
        <button
          className="btn btn-ghost btn-sm"
          onClick={() => {
            logout();
            navigate("/");
          }}
        >
          Logout
        </button>
      </aside>
      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}
