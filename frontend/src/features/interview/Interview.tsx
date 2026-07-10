import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import CodeMirror from "@uiw/react-codemirror";
import { python } from "@codemirror/lang-python";
import { javascript } from "@codemirror/lang-javascript";
import { java } from "@codemirror/lang-java";
import { cpp } from "@codemirror/lang-cpp";
import { vscodeDark } from "@uiw/codemirror-theme-vscode";
import api from "../../api/client";
import type { InterviewSession } from "../../api/types";
import { useParsedResumes } from "../ai/useGeneration";

const STAGE_LABELS: Record<string, string> = {
  behavioral: "Stage 1 · Getting to know you",
  technical: "Stage 2 · Technical — timed ⏱️",
  grading: "Grading",
  done: "Done",
};

const QUESTION_REVEAL_DELAY_MS = 1000;

type CodeLang = "python" | "javascript" | "java" | "cpp" | "text";

const LANG_OPTIONS: { value: CodeLang; label: string }[] = [
  { value: "python", label: "Python" },
  { value: "javascript", label: "JavaScript / TypeScript" },
  { value: "java", label: "Java" },
  { value: "cpp", label: "C++" },
  { value: "text", label: "Plain text / pseudocode" },
];

function langExtension(lang: CodeLang) {
  switch (lang) {
    case "python": return [python()];
    case "javascript": return [javascript({ typescript: true })];
    case "java": return [java()];
    case "cpp": return [cpp()];
    default: return [];
  }
}

function Timer({ askedAt, limitSeconds, onExpire }: {
  askedAt: string;
  limitSeconds: number;
  onExpire: () => void;
}) {
  const deadline = new Date(askedAt).getTime() + limitSeconds * 1000;
  const [remaining, setRemaining] = useState(Math.round((deadline - Date.now()) / 1000));
  const expired = useRef(false);

  useEffect(() => {
    expired.current = false;
    const tick = setInterval(() => {
      const left = Math.round((deadline - Date.now()) / 1000);
      setRemaining(left);
      if (left <= 0 && !expired.current) {
        expired.current = true;
        clearInterval(tick);
        onExpire();
      }
    }, 500);
    return () => clearInterval(tick);
  }, [deadline]);

  const shown = Math.max(0, remaining);
  const minutes = Math.floor(shown / 60);
  const seconds = String(shown % 60).padStart(2, "0");
  return (
    <span className={`timer ${shown <= 30 ? "danger" : ""}`}>
      ⏱️ {minutes}:{seconds}
    </span>
  );
}

export default function Interview() {
  const resumes = useParsedResumes();
  const [session, setSession] = useState<InterviewSession | null>(null);
  const [view, setView] = useState<"loading" | "setup" | "live">("loading");
  const [resumeId, setResumeId] = useState("");
  const [jd, setJd] = useState("");
  const [answer, setAnswer] = useState("");
  const [code, setCode] = useState("");
  const [codeLang, setCodeLang] = useState<CodeLang>("python");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const answerRef = useRef("");
  answerRef.current = answer;
  const codeRef = useRef("");
  codeRef.current = code;
  const codeLangRef = useRef<CodeLang>("python");
  codeLangRef.current = codeLang;
  const codeExtensions = useMemo(() => langExtension(codeLang), [codeLang]);
  const chatLogRef = useRef<HTMLDivElement>(null);

  // Keep the newest message in view as the transcript grows
  useEffect(() => {
    const el = chatLogRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [session?.transcript.length]);

  // The interviewer "sends" the transition line first, then the question
  // a beat later — like a real person typing two messages, not a robot
  // dumping both at once. Only the newest entry ever animates; anything
  // already in history (e.g. after a page refresh) renders instantly.
  const [questionRevealed, setQuestionRevealed] = useState(true);
  useEffect(() => {
    const transcript = session?.transcript ?? [];
    const latest = transcript[transcript.length - 1];
    if (latest && latest.answer === null && latest.transition) {
      setQuestionRevealed(false);
      const t = setTimeout(() => setQuestionRevealed(true), QUESTION_REVEAL_DELAY_MS);
      return () => clearTimeout(t);
    }
    setQuestionRevealed(true);
  }, [session?.transcript.length]);

  // Resume an in-progress interview after a page refresh
  useEffect(() => {
    api
      .get<InterviewSession>("/interviews/current")
      .then((r) => {
        if (r.data.status === "active" || r.data.status === "grading") {
          setSession(r.data);
          setView("live");
        } else {
          setView("setup");
        }
      })
      .catch(() => setView("setup"));
  }, []);

  // Poll while the worker grades
  useEffect(() => {
    if (session?.status !== "grading") return;
    const poll = setInterval(async () => {
      const { data } = await api.get<InterviewSession>(`/interviews/${session.id}`);
      setSession(data);
    }, 2500);
    return () => clearInterval(poll);
  }, [session?.id, session?.status]);

  async function start(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const { data } = await api.post<InterviewSession>("/interviews", {
        resume_id: Number(resumeId),
        job_description: jd,
      });
      setSession(data);
      setView("live");
    } catch (err: any) {
      setError(err.response?.data?.detail ?? "Could not start the interview");
    } finally {
      setBusy(false);
    }
  }

  const submitAnswer = useCallback(
    async (text: string) => {
      if (!session || busy) return;
      setBusy(true);
      setError("");
      try {
        const { data } = await api.post<InterviewSession>(
          `/interviews/${session.id}/answer`,
          { answer: text }
        );
        setSession(data);
        setAnswer("");
        setCode("");
      } catch (err: any) {
        setError(err.response?.data?.detail ?? "Could not submit — try again");
      } finally {
        setBusy(false);
      }
    },
    [session, busy]
  );

  // The code editor is a separate pane, but the grader only sees plain text —
  // fold both boxes into one answer, labeled, so nothing changes server-side.
  function composeAnswer(text: string, codeText: string, lang: CodeLang): string {
    const trimmedCode = codeText.trim();
    if (!trimmedCode) return text;
    const langLabel = LANG_OPTIONS.find((o) => o.value === lang)?.label ?? lang;
    return `${text}\n\nCODE (${langLabel}):\n${trimmedCode}`;
  }

  async function stopInterview() {
    if (!session) return;
    if (
      !window.confirm(
        "Stop this interview and go back? Your progress won't be saved as a finished interview."
      )
    )
      return;
    setBusy(true);
    try {
      await api.post(`/interviews/${session.id}/abandon`);
    } catch {
      // best-effort — let the user leave either way, it's a soft action
    } finally {
      setBusy(false);
      setSession(null);
      setView("setup");
    }
  }

  if (view === "loading") return <div className="page-loader">Loading…</div>;

  // ---------- Setup ----------
  if (view === "setup" || !session) {
    return (
      <div>
        <h1>Interview Simulator</h1>
        <p className="page-sub">
          A two-stage mock interview built from your resume and a real job
          description: warm-up questions, then timed technical ones — and an
          honest grade at the end.
        </p>
        {resumes.length === 0 ? (
          <div className="empty">
            First <Link to="/app/resumes" style={{ color: "var(--blue)" }}>upload a resume</Link>{" "}
            so the interviewer knows who you are.
          </div>
        ) : (
          <form className="form-grid" onSubmit={start}>
            <div>
              <label>Resume</label>
              <select required value={resumeId} onChange={(e) => setResumeId(e.target.value)}>
                <option value="">Choose…</option>
                {resumes.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.original_filename} {r.is_primary ? "(primary)" : ""}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label>Job description (the role you're interviewing for)</label>
              <textarea required minLength={50} rows={8} value={jd}
                onChange={(e) => setJd(e.target.value)} />
            </div>
            {error && <div className="auth-error">{error}</div>}
            <button className="btn btn-yellow" disabled={busy} style={{ justifySelf: "start" }}>
              {busy ? "Preparing…" : "🎤 Start the interview"}
            </button>
            <p className="meta" style={{ margin: 0 }}>
              Stage 2 questions are real technical problems with a 15-minute
              timer each — running out auto-submits whatever you've written.
              Treat it like the real thing: no tab-switching to Google.
            </p>
          </form>
        )}
      </div>
    );
  }

  // ---------- Report ----------
  if (session.status === "done" || session.status === "failed") {
    const report = session.report ?? {};
    const technicalEntries = session.transcript.filter((e) => e.stage === "technical");
    return (
      <div style={{ maxWidth: 860 }}>
        <h1>Interview Report</h1>
        {session.status === "failed" ? (
          <div className="auth-error" style={{ marginTop: 12 }}>
            Grading failed: {report.error} — your answers are saved; try a new
            interview later.
          </div>
        ) : (
          <>
            <div className="score-row">
              <div className="score-box after">
                <div className="n">{report.score}/100</div>
                <div className="l">Interview grade</div>
              </div>
            </div>

            <div className="panel">
              <h3>Interviewer's summary</h3>
              <p style={{ margin: 0 }}>{report.summary}</p>
              {report.behavioral?.comments && (
                <p className="meta" style={{ marginTop: 10 }}>
                  Stage 1: {report.behavioral.comments} (communication{" "}
                  {report.behavioral.communication}/10 · structure{" "}
                  {report.behavioral.structure}/10 · relevance{" "}
                  {report.behavioral.relevance}/10)
                </p>
              )}
            </div>

            <h2 style={{ fontSize: 17, margin: "22px 0 10px" }}>Stage 2 — question by question</h2>
            <div className="stack">
              {(report.technical_reviews ?? []).map((review) => {
                const entry = technicalEntries[review.question_index - 1];
                return (
                  <div className="panel rewrite" key={review.question_index}>
                    <div className="meta">Q{review.question_index}: {entry?.question}</div>
                    <div style={{ margin: "8px 0 4px", fontWeight: 700 }}>
                      {review.score}/10{" "}
                      {entry?.overtime && <span className="chip red">⏱️ overtime −2</span>}
                    </div>
                    <p style={{ margin: 0 }}>{review.review}</p>
                    {review.better_answer_hint && (
                      <p className="meta" style={{ marginTop: 8 }}>
                        💡 {review.better_answer_hint}
                      </p>
                    )}
                  </div>
                );
              })}
            </div>

            <div className="form-row" style={{ marginTop: 18, maxWidth: 860 }}>
              <div className="panel">
                <h3>Strengths</h3>
                <ul style={{ margin: 0, paddingLeft: 18 }}>
                  {(report.strengths ?? []).map((s, i) => <li key={i}>{s}</li>)}
                </ul>
              </div>
              <div className="panel">
                <h3>Work on this</h3>
                <ul style={{ margin: 0, paddingLeft: 18 }}>
                  {(report.improvements ?? []).map((s, i) => <li key={i}>{s}</li>)}
                </ul>
              </div>
            </div>
          </>
        )}
        <div style={{ marginTop: 20 }}>
          <button className="btn btn-yellow" onClick={() => { setSession(null); setView("setup"); }}>
            🎤 New interview
          </button>
        </div>
      </div>
    );
  }

  // ---------- Grading spinner ----------
  if (session.status === "grading") {
    return (
      <div className="empty-center">
        <div style={{ fontSize: 44 }}>🧮</div>
        <p style={{ fontWeight: 600, color: "var(--text)" }}>
          The interviewer is writing up your evaluation…
        </p>
        <p style={{ margin: 0 }}>Usually under a minute. Don't close the page.</p>
      </div>
    );
  }

  // ---------- Live interview ----------
  const answered = session.transcript.filter((e) => e.answer !== null).length;
  const total = 6; // 3 behavioral + 3 technical
  const lastIndex = session.transcript.length - 1;
  const isTechnicalStage = session.stage === "technical";

  const chatPane = (
    <div className="chat-card">
      <div className="chat-log" ref={chatLogRef}>
        {session.transcript.map((entry, i) => {
          const isLatest = i === lastIndex;
          const showQuestion = !isLatest || questionRevealed || !entry.transition;
          return (
            <div key={i}>
              {entry.transition && (
                <div className="bubble q">
                  <span className="who">Interviewer</span>
                  {entry.transition}
                </div>
              )}
              {isLatest && !showQuestion ? (
                <div className="bubble q typing-bubble">
                  <span className="who">Interviewer</span>
                  <span className="typing-dots"><span /><span /><span /></span>
                </div>
              ) : (
                <div className="bubble q">
                  <span className="who">Interviewer</span>
                  {entry.question}
                  {isLatest && entry.time_limit_seconds && (
                    <div style={{ marginTop: 8 }}>
                      <Timer
                        askedAt={entry.asked_at}
                        limitSeconds={entry.time_limit_seconds}
                        onExpire={() =>
                          submitAnswer(
                            composeAnswer(
                              answerRef.current || "(ran out of time)",
                              codeRef.current,
                              codeLangRef.current
                            )
                          )
                        }
                      />
                    </div>
                  )}
                </div>
              )}
              {entry.answer !== null && (
                <div className="bubble a">
                  <span className="who">You</span>
                  {entry.answer}
                </div>
              )}
            </div>
          );
        })}
      </div>

      <form
        className="chat-input-bar"
        onSubmit={(e) => {
          e.preventDefault();
          if (answer.trim() || code.trim()) submitAnswer(composeAnswer(answer, code, codeLang));
        }}
      >
        <textarea
          rows={3}
          placeholder={
            isTechnicalStage
              ? "Explain your approach… (use the code editor on the right for actual code)"
              : "Type your answer… (be specific, like you would out loud)"
          }
          value={answer}
          onChange={(e) => setAnswer(e.target.value)}
          disabled={busy}
        />
        <button className="btn btn-blue" disabled={busy || !(answer.trim() || code.trim())}>
          {busy ? "…" : "Send"}
        </button>
      </form>
    </div>
  );

  return (
    <div className={isTechnicalStage ? "interview-shell interview-shell-wide" : "interview-shell"}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
        <div>
          <h1>Interview Simulator</h1>
          <p className="page-sub" style={{ margin: 0 }}>
            {STAGE_LABELS[session.stage]} · question {answered + 1} of {total}
          </p>
        </div>
        <button className="btn btn-ghost btn-sm" onClick={stopInterview} disabled={busy}>
          Stop interview
        </button>
      </div>

      {isTechnicalStage ? (
        <div className="interview-split" style={{ marginTop: 20 }}>
          {chatPane}
          <div className="code-panel">
            <div className="code-panel-header">
              <span>Code (optional)</span>
              <select
                value={codeLang}
                onChange={(e) => setCodeLang(e.target.value as CodeLang)}
                disabled={busy}
              >
                {LANG_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
            <CodeMirror
              className="code-panel-editor"
              value={code}
              onChange={setCode}
              theme={vscodeDark}
              extensions={codeExtensions}
              editable={!busy}
              height="100%"
              placeholder="// Optional — write code here if the question calls for it"
            />
          </div>
        </div>
      ) : (
        <div style={{ marginTop: 20 }}>{chatPane}</div>
      )}
      {error && <div className="auth-error" style={{ marginTop: 10 }}>{error}</div>}
    </div>
  );
}
