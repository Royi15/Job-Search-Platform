import { useEffect, useRef, useState } from "react";
import api from "../../api/client";
import type { Resume } from "../../api/types";

export default function Resumes() {
  const [resumes, setResumes] = useState<Resume[]>([]);
  const [uploading, setUploading] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  async function load() {
    const { data } = await api.get<Resume[]>("/resumes");
    setResumes(data);
    return data;
  }

  useEffect(() => {
    load();
  }, []);

  // While any resume is still being parsed by the worker, poll every 3 s.
  useEffect(() => {
    if (!resumes.some((r) => r.parse_status === "pending")) return;
    const timer = setInterval(load, 3000);
    return () => clearInterval(timer);
  }, [resumes]);

  async function upload(file: File) {
    setUploading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      await api.post("/resumes", form);
      await load();
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  async function setPrimary(id: number) {
    await api.post(`/resumes/${id}/primary`);
    await load();
  }

  async function remove(r: Resume) {
    if (!window.confirm(`Delete "${r.original_filename}"? This can't be undone.`))
      return;
    await api.delete(`/resumes/${r.id}`);
    await load();
  }

  return (
    <div>
      <h1>Resumes</h1>
      <p className="page-sub">
        Upload a PDF — we run it through a simulated ATS parser so you can see
        exactly what the screening robots extract from it.
      </p>

      <div className="panel" style={{ maxWidth: 560 }}>
        <label>Upload resume (PDF, up to 8 MB)</label>
        <input
          ref={fileInput}
          type="file"
          accept="application/pdf"
          disabled={uploading}
          onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])}
        />
      </div>

      <div className="stack" style={{ marginTop: 20 }}>
        {resumes.map((r) => (
          <div className="panel" key={r.id}>
            <h3>
              {r.original_filename}{" "}
              {r.is_primary && <span className="badge done">primary</span>}{" "}
              <span className={`badge ${r.parse_status}`}>
                {r.parse_status === "pending" ? "parsing…" : r.parse_status}
              </span>
            </h3>
            <div className="meta">
              Uploaded {new Date(r.uploaded_at).toLocaleString()}
            </div>
            {r.parse_status === "done" && (
              <>
                <div className="meta" style={{ marginTop: 10 }}>
                  Skills the ATS sees in your resume (a simulation — real
                  screening systems vary and may read your resume differently):
                </div>
                <div className="chips">
                  {(r.extracted?.skills ?? []).map((s) => (
                    <span className="chip green" key={s}>{s}</span>
                  ))}
                  {(r.extracted?.skills ?? []).length === 0 && (
                    <span className="chip red">none detected — that's a problem!</span>
                  )}
                </div>
              </>
            )}
            <div className="actions">
              {!r.is_primary && (
                <button className="btn btn-ghost btn-sm" onClick={() => setPrimary(r.id)}>
                  Make primary
                </button>
              )}
              <button className="btn btn-danger btn-sm" onClick={() => remove(r)}>
                Delete
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
