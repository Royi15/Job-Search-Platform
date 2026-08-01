import { Link } from "react-router-dom";

const STUDY_CARDS = [
  {
    to: "/app/study/notebooks",
    icon: "📓",
    title: "Notebook Generator",
    text: "Turn a topic, lecture, or job description into a structured study notebook — coming soon.",
  },
  {
    to: "/app/study/trivisum",
    icon: "📝",
    title: "Trivisum",
    text: "Details coming soon.",
  },
];

export default function StudyHome() {
  return (
    <div>
      <h1>Study</h1>
      <p className="page-sub">Pick a tool to keep sharpening your skills.</p>
      <div className="feature-cards">
        {STUDY_CARDS.map((c) => (
          <Link key={c.to} to={c.to} className="feature-card">
            <div className="icon">{c.icon}</div>
            <h3>{c.title}</h3>
            <p>{c.text}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
