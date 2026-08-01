import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { SECTIONS, type Hub } from "../config/sections";

export default function AppLayout({ hub }: { hub: Hub }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const items = SECTIONS.filter((s) => s.hub === hub);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link to="/app" className="brand" style={{ textDecoration: "none", color: "inherit" }}>
          Job<span style={{ color: "var(--yellow)" }}>Pilot</span>
        </Link>
        <Link to="/app" className="sidebar-back">
          ← Back
        </Link>
        {items.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            end={item.end}
            className={({ isActive }) => (isActive ? "active" : "")}
          >
            {item.icon} {item.label}
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
