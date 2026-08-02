export type Hub = "job" | "study";

export interface Section {
  icon: string;
  label: string;
  path: string;
  hub: Hub;
  end?: boolean; // true for a hub's index route, so NavLink doesn't stay active on children
}

export const SECTIONS: Section[] = [
  { icon: "📋", label: "Board", path: "/app/job", hub: "job", end: true },
  { icon: "🔔", label: "Job Alerts", path: "/app/job/alerts", hub: "job" },
  { icon: "🎯", label: "Preferences", path: "/app/job/preferences", hub: "job" },
  { icon: "📄", label: "Resumes", path: "/app/job/resumes", hub: "job" },
  { icon: "🛡️", label: "ATS Tailor", path: "/app/job/tailor", hub: "job" },
  { icon: "✨", label: "Cover Letter", path: "/app/job/cover-letter", hub: "job" },
  { icon: "🎤", label: "Interview Sim", path: "/app/job/interview", hub: "job" },
  { icon: "⚙️", label: "Settings", path: "/app/job/settings", hub: "job" },
  { icon: "📓", label: "Notebook Generator", path: "/app/study", hub: "study", end: true },
  { icon: "📝", label: "Trivisum", path: "/app/study/trivisum", hub: "study" },
];
