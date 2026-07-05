import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

export default function AuthPage({ mode }: { mode: "login" | "register" }) {
  const { login, register } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const isLogin = mode === "login";

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      if (isLogin) await login(email, password);
      else await register(email, password, fullName);
      navigate("/app");
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      if (typeof detail === "string") {
        setError(detail);
      } else if (Array.isArray(detail)) {
        // FastAPI validation errors (422): a list of {loc, msg, type} objects
        setError(
          detail
            .map((d: any) => (d.loc?.includes("email") ? "Please enter a valid email address" : d.msg))
            .filter(Boolean)
            .join(". ") || "Please check your input"
        );
      } else {
        setError("Something went wrong — try again");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-wrap">
      <div className="auth-card">
        <Link to="/" className="brand">
          Job<span style={{ color: "var(--yellow)" }}>Pilot</span>
        </Link>
        <h1>{isLogin ? "Welcome back" : "Create your account"}</h1>
        <form onSubmit={onSubmit}>
          {!isLogin && (
            <div>
              <label>Full name</label>
              <input
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="Israel Israeli"
              />
            </div>
          )}
          <div>
            <label>Email</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@university.ac.il"
            />
          </div>
          <div>
            <label>Password {!isLogin && "(at least 8 characters)"}</label>
            <input
              type="password"
              required
              minLength={isLogin ? undefined : 8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          {error && <div className="auth-error">{error}</div>}
          <button className="btn btn-yellow" disabled={busy}>
            {busy ? "…" : isLogin ? "Login" : "Sign up free"}
          </button>
        </form>
        <div className="auth-alt">
          {isLogin ? (
            <>
              New here? <Link to="/register">Create an account</Link>
            </>
          ) : (
            <>
              Already registered? <Link to="/login">Login</Link>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
