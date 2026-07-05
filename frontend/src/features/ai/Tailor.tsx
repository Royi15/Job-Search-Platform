import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import api from "../../api/client";
import type { Generation } from "../../api/types";
import { useGeneration, useParsedResumes } from "./useGeneration";

export default function Tailor() {
  const resumes = useParsedResumes();
  const [resumeId, setResumeId] = useState("");
  const [jd, setJd] = useState("");
  const { generation, setGeneration, running } = useGeneration();
  const result = generation?.status === "done" ? generation.result : null;

  async function submit(e: FormEvent) {
    e.preventDefault();
    const { data } = await api.post<Generation>("/ai/tailor", {
      resume_id: Number(resumeId),
      job_description: jd,
    });
    setGeneration(data);
  }

  return (
    <div>
      <h1>ATS Tailor</h1>
      <p className="page-sub">
        Paste a job description — we find the keyword gap and rewrite your
        resume sentences to close it, without inventing experience.
      </p>

      {resumes.length === 0 ? (
        <div className="empty">
          First <Link to="/app/resumes" style={{ color: "var(--blue)" }}>upload a resume</Link> and
          wait for parsing to finish.
        </div>
      ) : (
        <form className="form-grid" onSubmit={submit}>
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
            <label>Job description (paste the full text)</label>
            <textarea required minLength={50} rows={9} value={jd}
              onChange={(e) => setJd(e.target.value)} />
          </div>
          <button className="btn btn-yellow" disabled={running} style={{ justifySelf: "start" }}>
            {running ? "Analyzing… (~20s)" : "🛡️ Jailbreak the ATS"}
          </button>
        </form>
      )}

      {generation?.status === "failed" && (
        <div className="auth-error" style={{ marginTop: 16 }}>
          Generation failed: {generation.error}
        </div>
      )}

      {result && (
        <div style={{ marginTop: 24, maxWidth: 860 }}>
          <div className="disclaimer">
            <span>⚠️</span>
            <span>
              These suggestions are AI-generated and can be wrong. Read every
              rewrite before using it — make sure it stays true to your actual
              experience, and never submit a claim you can't back up in an
              interview. The scores are rough estimates of keyword matching,
              not a guarantee of how any specific company's ATS will rank you.
            </span>
          </div>
          <div className="score-row">
            <div className="score-box">
              <div className="n">{result.ats_score_before}%</div>
              <div className="l">ATS score before</div>
            </div>
            <div className="score-box after">
              <div className="n">{result.ats_score_after}%</div>
              <div className="l">ATS score after</div>
            </div>
          </div>

          <div className="panel">
            <h3>The gap</h3>
            <p style={{ margin: 0 }}>{result.gap_summary}</p>
            <div className="chips">
              {result.keywords_missing.map((k) => (
                <span className="chip red" key={k}>missing: {k}</span>
              ))}
            </div>
          </div>

          <h2 style={{ fontSize: 17, margin: "22px 0 10px" }}>Suggested rewrites</h2>
          <div className="stack">
            {result.rewrites.map((rw, i) => (
              <div className="panel rewrite" key={i}>
                <div className="orig">{rw.original}</div>
                <div className="new">{rw.rewritten}</div>
                <div className="chips">
                  {rw.keywords_injected.map((k) => (
                    <span className="chip green" key={k}>+{k}</span>
                  ))}
                </div>
              </div>
            ))}
          </div>

          {result.keywords_not_injectable.length > 0 && (
            <div className="panel" style={{ marginTop: 14 }}>
              <h3>Couldn't add honestly</h3>
              <p className="meta">
                These JD keywords have no truthful home in your resume — consider
                actually learning them: {result.keywords_not_injectable.join(", ")}
              </p>
            </div>
          )}

          {result.extra_tips.length > 0 && (
            <div className="panel" style={{ marginTop: 14 }}>
              <h3>Tips for this application</h3>
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {result.extra_tips.map((t, i) => <li key={i}>{t}</li>)}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
