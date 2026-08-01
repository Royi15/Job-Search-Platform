import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { SECTIONS } from "../config/sections";

export default function Welcome() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [query, setQuery] = useState("");

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    return SECTIONS.filter((s) => s.label.toLowerCase().startsWith(q));
  }, [query]);

  function goTo(path: string) {
    setQuery("");
    navigate(path);
  }

  return (
    <div>
      <header className="welcome-header">
        <div className="brand">
          Job<span style={{ color: "var(--yellow)" }}>Pilot</span>
        </div>
        <button
          className="btn btn-ghost btn-sm"
          onClick={() => {
            logout();
            navigate("/");
          }}
        >
          Logout
        </button>
      </header>
      <main className="main">
        <div className="welcome-hero">
          <h1 className="welcome-title">Welcome, {user?.full_name ?? user?.email}</h1>
          <div className="search-wrap search-wrap-lg">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Jump to a section… (e.g. “resumes”)"
              autoComplete="off"
            />
            {results.length > 0 && (
              <div className="search-results panel">
                {results.map((r) => (
                  <button
                    key={r.path}
                    type="button"
                    className="search-result-item"
                    onClick={() => goTo(r.path)}
                  >
                    <span>{r.icon}</span> {r.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
        <div className="feature-cards" style={{ marginTop: 32 }}>
          <Link to="/app/job" className="feature-card">
            <div className="icon">💼</div>
            <h3>JOB</h3>
            <p>Track applications, get real-time alerts, tailor your resume with AI, and practice interviews.</p>
          </Link>
          <Link to="/app/study" className="feature-card">
            <div className="icon">📚</div>
            <h3>STUDY</h3>
            <p>Generate study notebooks and prep materials while you search.</p>
          </Link>
        </div>
      </main>
    </div>
  );
}
