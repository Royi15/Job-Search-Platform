export type ApplicationStatus =
  | "applied"
  | "phone_interview"
  | "home_assignment"
  | "technical_interview"
  | "rejected"
  | "offer";

export interface Me {
  id: number;
  email: string;
  full_name: string | null;
  telegram_linked: boolean;
}

export interface Application {
  id: number;
  job_id: number | null;
  company: string;
  title: string;
  url: string | null;
  status: ApplicationStatus;
  sort_order: number;
  notes: string | null;
  applied_at: string;
  updated_at: string;
}

export interface Job {
  id: number;
  source: string;
  title: string;
  company: string | null;
  location: string | null;
  is_remote: boolean;
  url: string;
  description: string | null;
  posted_at: string | null;
}

export interface Alert {
  id: number;
  matched_at: string;
  notified_at: string | null;
  dismissed: boolean;
  job: Job;
}

export interface Preference {
  id: number;
  name: string;
  title_keywords: string[];
  must_have_keywords: string[];
  exclude_keywords: string[];
  locations: string[];
  remote_ok: boolean;
  is_active: boolean;
  created_at: string;
}

export interface Resume {
  id: number;
  original_filename: string;
  parse_status: "pending" | "done" | "failed";
  extracted: {
    skills?: string[];
    sections_detected?: string[];
    skills_source?: "ai" | "dictionary";
  } | null;
  is_primary: boolean;
  uploaded_at: string;
}

export interface Rewrite {
  original: string;
  rewritten: string;
  keywords_injected: string[];
}

export interface TailoringResult {
  ats_score_before: number;
  ats_score_after: number;
  keywords_matched: string[];
  keywords_missing: string[];
  gap_summary: string;
  rewrites: Rewrite[];
  keywords_not_injectable: string[];
  extra_tips: string[];
}

export interface InterviewEntry {
  stage: "behavioral" | "technical";
  question: string;
  transition: string | null;
  asked_at: string;
  time_limit_seconds: number | null;
  answer: string | null;
  answered_at: string | null;
  overtime: boolean;
}

export interface TechnicalReview {
  question_index: number;
  score: number;
  review: string;
  better_answer_hint?: string;
  overtime_penalty_applied?: boolean;
}

export interface InterviewReport {
  score?: number;
  summary?: string;
  strengths?: string[];
  improvements?: string[];
  behavioral?: {
    communication: number;
    structure: number;
    relevance: number;
    comments: string;
  };
  technical_reviews?: TechnicalReview[];
  error?: string;
}

export interface InterviewSession {
  id: number;
  job_description: string;
  title: string | null;
  stage: "behavioral" | "technical" | "grading" | "done";
  status: "active" | "grading" | "done" | "failed" | "abandoned";
  transcript: InterviewEntry[];
  report: InterviewReport | null;
  created_at: string;
}

export interface Generation {
  id: number;
  kind: "resume_tailoring" | "cover_letter" | "linkedin_message";
  status: "pending" | "running" | "done" | "failed";
  result: (TailoringResult & { text?: string; subject?: string }) | null;
  error: string | null;
  created_at: string;
  completed_at: string | null;
}
