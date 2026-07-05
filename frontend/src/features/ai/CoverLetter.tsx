import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import api from "../../api/client";
import type { Generation } from "../../api/types";
import { useGeneration, useParsedResumes } from "./useGeneration";

export default function CoverLetter() {
  const resumes = useParsedResumes();
  const [resumeId, setResumeId] = useState("");
  const [jd, setJd] = useState("");
  const [kind, setKind] = useState<"cover_letter" | "linkedin_message">("cover_letter");
  const [copied, setCopied] = useState(false);
  const { generation, setGeneration, running } = useGeneration();
  const result = generation?.status === "done" ? generation.result : null;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setCopied(false);
    const { data } = await api.post<Generation>("/ai/cover-letter", {
      resume_id: Number(resumeId),
      job_description: jd,
      kind,
    });
    setGeneration(data);
  }

  async function copy() {
    if (!result?.text) return;
    await navigator.clipboard.writeText(result.text);
    setCopied(true);
  }

  return (
    <div>
      <h1>Magic Cover Letter</h1>
      <p className="page-sub">
        A targeted cover letter or LinkedIn message, grounded in your actual
        resume and the exact job description.
      </p>

      {resumes.length === 0 ? (
        <div className="empty">
          First <Link to="/app/resumes" style={{ color: "var(--blue)" }}>upload a resume</Link> and
          wait for parsing to finish.
        </div>
      ) : (
        <form className="form-grid" onSubmit={submit}>
          <div className="form-row">
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
              <label>Type</label>
              <select value={kind} onChange={(e) => setKind(e.target.value as typeof kind)}>
                <option value="cover_letter">Cover letter</option>
                <option value="linkedin_message">LinkedIn message</option>
              </select>
            </div>
          </div>
          <div>
            <label>Job description</label>
            <textarea required minLength={50} rows={9} value={jd}
              onChange={(e) => setJd(e.target.value)} />
          </div>
          <button className="btn btn-yellow" disabled={running} style={{ justifySelf: "start" }}>
            {running ? "Writing… this can take a few minutes" : "✨ Generate"}
          </button>
        </form>
      )}

      {generation?.status === "failed" && (
        <div className="auth-error" style={{ marginTop: 16 }}>
          Generation failed: {generation.error}
        </div>
      )}

      {result?.text && (
        <div style={{ marginTop: 24, maxWidth: 860 }}>
          <div className="disclaimer">
            <span>⚠️</span>
            <span>
              AI-generated draft — it can contain mistakes or overstate your
              experience. Read it fully, fix anything inaccurate, and add your
              personal touch before sending. Recruiters can smell an unedited
              AI letter.
            </span>
          </div>
          {result.subject && (
            <div className="panel" style={{ marginBottom: 12 }}>
              <div className="meta">Suggested subject</div>
              <strong>{result.subject}</strong>
            </div>
          )}
          <div className="letter-output">{result.text}</div>
          <div style={{ marginTop: 12 }}>
            <button className="btn btn-blue btn-sm" onClick={copy}>
              {copied ? "Copied ✓" : "Copy to clipboard"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
