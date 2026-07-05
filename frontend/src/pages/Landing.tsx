import { Link } from "react-router-dom";

const FEATURES = [
  {
    icon: "🔔",
    title: "Real-Time Job Alerts",
    text: "We scan LinkedIn for fresh student jobs around the clock and ping you on Telegram the moment one matches your criteria.",
  },
  {
    icon: "🛡️",
    title: "ATS Jailbreaker",
    text: "See your resume the way the screening robot sees it, and let AI rewrite sentences to beat the keyword filter — honestly.",
  },
  {
    icon: "🗂️",
    title: "Application Tracker",
    text: "A drag-and-drop board that follows every application from Applied to Offer. No more spreadsheet chaos.",
  },
  {
    icon: "✨",
    title: "Magic Cover Letter",
    text: "Targeted cover letters and LinkedIn messages generated from your resume and the exact job description.",
  },
];

const STEPS = [
  {
    num: "1",
    title: "Tell us what you're looking for",
    text: "Set your desired titles, keywords and locations. Link your Telegram in one tap.",
  },
  {
    num: "2",
    title: "We hunt while you study",
    text: "New student jobs land in your Telegram and in our community Discord feed — before most people see them.",
  },
  {
    num: "3",
    title: "Apply smarter, track everything",
    text: "Tailor your resume to each job with AI, generate the cover letter, and drag the application across your board.",
  },
];

export default function Landing() {
  return (
    <div>
      <header className="landing-nav">
        <div className="brand">
          Job<span>Pilot</span>
        </div>
        <nav className="links">
          <a href="#features">Features</a>
          <a href="#how">How it works</a>
          <a href="#about">About</a>
        </nav>
        <div className="actions">
          <Link to="/login" className="btn btn-ghost">
            Login
          </Link>
          <Link to="/register" className="btn btn-blue">
            SIGN UP FREE
          </Link>
        </div>
      </header>

      <section className="hero">
        <div>
          <h1>Land your first tech job, faster!</h1>
          <p className="sub">
            We find student jobs for you 24/7, beat the resume-screening robots
            with AI, and keep every application organized. Built for students.
          </p>
          <div className="hero-cta">
            <Link to="/register" className="btn btn-yellow">
              GET JOB ALERTS
            </Link>
            <a href="#how" className="btn btn-ghost">
              SEE HOW IT WORKS
            </a>
          </div>
        </div>
        <div className="hero-art">
          <div className="caption">Job hunt on autopilot</div>
          <div className="emoji-collage">
            🔎💼🤖
            <br />
            📄✅✉️
          </div>
        </div>
      </section>

      <section className="section" id="features">
        <h2>Features at a Glance</h2>
        <div className="feature-cards">
          {FEATURES.map((f) => (
            <div className="feature-card" key={f.title}>
              <div className="icon">{f.icon}</div>
              <h3>{f.title}</h3>
              <p>{f.text}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="section" id="how">
        <h2>How it works</h2>
        <div className="steps">
          {STEPS.map((s) => (
            <div className="step" key={s.num}>
              <div className="num">{s.num}</div>
              <h3>{s.title}</h3>
              <p style={{ color: "var(--muted)", fontSize: 13 }}>{s.text}</p>
            </div>
          ))}
        </div>
      </section>

      <footer className="landing-footer" id="about">
        JobPilot — a job-search platform for students and juniors. Real-time
        LinkedIn job discovery · Telegram &amp; Discord alerts · AI resume
        tailoring · application tracking.
      </footer>
    </div>
  );
}
