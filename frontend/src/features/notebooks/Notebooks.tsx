import { useEffect, useRef, useState, type MouseEvent } from "react";
import api from "../../api/client";
import type { Notebook, NotebookBlock, NotebookPageContent } from "../../api/types";
import MathText from "./MathText";
import Diagram from "./Diagram";
import ErrorBoundary from "../../components/ErrorBoundary";

type DisplayPage =
  | { kind: "page"; page: NotebookPageContent }
  | { kind: "glossary"; terms: { term: string; definition: string }[] };

const SOURCE_ICON: Record<Notebook["source_type"], string> = {
  pdf: "📄",
  pptx: "📊",
  mp3: "🎧",
};

// Mirrors backend's settings.notebook_generation_limit — a cap on how many
// notebooks a user can have AT ONCE (deleting one frees up a slot). The
// backend is the real enforcement point; this just lets the upload form
// hide itself with an accurate message instead of failing with a 429.
// notebooks.length is an accurate live count of this because GET
// /notebooks is capped at this same limit server-side.
const MAX_NOTEBOOKS_PER_USER = 30;

// Every notebook gets its own color identity derived from its subject
// ("Chemistry" always lands on the same hue, "Machine Learning" a totally
// different one) instead of a fixed rainbow cycled the same way every time —
// so notebooks actually look distinct from each other, not like the same
// template reused with different text.
function subjectHue(subject: string | undefined): number {
  const s = subject || "General";
  let hash = 0;
  for (let i = 0; i < s.length; i++) hash = (hash * 31 + s.charCodeAt(i)) >>> 0;
  return hash % 360;
}

export default function Notebooks() {
  const [notebooks, setNotebooks] = useState<Notebook[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);
  const [pageIndex, setPageIndex] = useState(0);
  const [pageDirection, setPageDirection] = useState<"next" | "prev">("next");
  const [printMode, setPrintMode] = useState(false);
  const [language, setLanguage] = useState<"en" | "he">("en");

  // Opening a different notebook (or the same one again) always starts on page 1.
  useEffect(() => {
    setPageIndex(0);
  }, [selectedId]);

  async function load() {
    const { data } = await api.get<Notebook[]>("/notebooks");
    setNotebooks(data);
    return data;
  }

  useEffect(() => {
    load();
  }, []);

  // While any notebook is still being generated, poll every 3 s.
  useEffect(() => {
    if (!notebooks.some((n) => n.status === "pending" || n.status === "running")) return;
    const timer = setInterval(load, 3000);
    return () => clearInterval(timer);
  }, [notebooks]);

  async function upload(file: File) {
    setUploading(true);
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("language", language);
      await api.post("/notebooks", form);
      await load();
    } catch (err: any) {
      setError(err.response?.data?.detail ?? "Could not upload — try again");
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  async function remove(n: Notebook, e: MouseEvent) {
    e.stopPropagation();
    if (!window.confirm(`Delete "${n.title ?? n.original_filename}"? This can't be undone.`)) return;
    await api.delete(`/notebooks/${n.id}`);
    if (selectedId === n.id) setSelectedId(null);
    await load();
  }

  const selected = notebooks.find((n) => n.id === selectedId) ?? null;

  function downloadPdf(title: string) {
    const previousTitle = document.title;
    document.title = title; // browsers suggest this as the saved PDF's filename
    const restore = () => {
      document.title = previousTitle;
      setPrintMode(false);
      window.removeEventListener("afterprint", restore);
    };
    window.addEventListener("afterprint", restore);
    // The PDF must contain every page, not just whichever one is on screen —
    // flip into "show everything, no pagination" mode, then let that render
    // before opening the print dialog.
    setPrintMode(true);
    setTimeout(() => window.print(), 60);
  }

  // ---------- Detail view ----------
  if (selected && selected.content) {
    const c = selected.content;
    const notebookTitle = c.title ?? selected.title ?? selected.original_filename;
    const notebookLanguage = selected.language;
    // Base direction must come from the notebook's language, not be
    // re-guessed per fragment: dir="auto" picks direction from the first
    // *strong* character in that one fragment, so a block that's just a
    // stray formula/number/punctuation (no Hebrew letters at all) silently
    // falls back to the browser default of LTR and detaches from the rest
    // of an RTL page. bidiSafe() already isolates embedded English/math
    // runs within a paragraph, so the container itself doesn't need "auto".
    const contentDir = notebookLanguage === "he" ? "rtl" : "auto";
    // A display ($$...$$) formula mid-sentence renders as a block-level
    // <div> (needed so it can be centered on its own line) nested inside
    // the surrounding <p>/<li> — any prose that follows it in the same
    // string ends up in a browser-generated anonymous block box around
    // that trailing text. That box is supposed to inherit alignment from
    // dir="rtl" via "text-align: start", but that resolution isn't
    // reliable in practice, so set the actual alignment explicitly instead
    // of leaning on inheritance.
    const textAlign: "right" | "left" = notebookLanguage === "he" ? "right" : "left";
    const mathDir: "rtl" | "ltr" = notebookLanguage === "he" ? "rtl" : "ltr";
    const hue = subjectHue(c.subject);

    const pages: DisplayPage[] = [
      ...c.pages.map((page) => ({ kind: "page" as const, page })),
      ...(c.key_terms && c.key_terms.length > 0 ? [{ kind: "glossary" as const, terms: c.key_terms }] : []),
    ];
    const clampedIndex = Math.min(pageIndex, Math.max(0, pages.length - 1));
    const showCover = printMode || clampedIndex === 0;

    function renderBlock(block: NotebookBlock, i: number) {
      switch (block.type) {
        case "text":
          return (
            <p className="notebook-text" dir={contentDir} style={{ textAlign }} key={i}>
              <MathText text={block.content} dir={mathDir} />
            </p>
          );
        case "bullets":
          return (
            <ul className="notebook-bullets" key={i}>
              {(block.items ?? []).map((b, j) => (
                <li key={j} dir={contentDir} style={{ textAlign }}>
                  <MathText text={b} dir={mathDir} />
                </li>
              ))}
            </ul>
          );
        case "table":
          return (
            <div style={{ overflowX: "auto" }} key={i}>
              <table className="notebook-table">
                <thead>
                  <tr>
                    {(block.headers ?? []).map((h, j) => (
                      <th key={j} dir={contentDir} style={{ textAlign }}>
                        <MathText text={h} dir={mathDir} />
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(block.rows ?? []).map((row, j) => (
                    <tr key={j}>
                      {(row ?? []).map((cell, k) => (
                        <td key={k} dir={contentDir} style={{ textAlign }}>
                          <MathText text={cell} dir={mathDir} />
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        case "callout":
          return (
            <div className="notebook-callout" dir={contentDir} style={{ textAlign }} key={i}>
              <MathText text={block.content} dir={mathDir} />
            </div>
          );
        case "diagram":
          return <Diagram code={block.content ?? ""} key={i} />;
        default:
          return null;
      }
    }

    function renderPage(dp: DisplayPage) {
      if (dp.kind === "glossary") {
        return (
          <div className="notebook-section">
            <h3 className="notebook-heading" dir={contentDir} style={{ textAlign }}>
              <span className="notebook-section-icon" dir="ltr">📖</span>{" "}
              {notebookLanguage === "he" ? "מונחי מפתח" : "Key terms"}
            </h3>
            <dl className="notebook-glossary">
              {dp.terms.map((kt, i) => (
                <div key={i}>
                  <dt dir={contentDir} style={{ textAlign }}>
                    <MathText text={kt.term} dir={mathDir} />
                  </dt>
                  <dd dir={contentDir} style={{ textAlign }}>
                    <MathText text={kt.definition} dir={mathDir} />
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        );
      }
      const page = dp.page;
      return (
        <div className="notebook-section">
          <h3 className="notebook-heading" dir={contentDir} style={{ textAlign }}>
            <span className="notebook-section-icon" dir="ltr">{page.icon || "•"}</span> {page.heading}
          </h3>
          <div className="notebook-blocks">{page.blocks.map((block, i) => renderBlock(block, i))}</div>
        </div>
      );
    }

    return (
      <div style={{ maxWidth: 760, margin: "0 auto" }}>
        <div className="no-print" style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
          <button className="btn btn-ghost btn-sm" onClick={() => setSelectedId(null)}>
            ← Back to notebooks
          </button>
          <button className="btn btn-yellow btn-sm" onClick={() => downloadPdf(notebookTitle)}>
            ⬇️ Export as PDF
          </button>
        </div>

        <div
          className={`notebook-paper ${c.paper_style === "lined" ? "lined" : ""}`}
          style={{ ["--nb-accent" as string]: `hsl(${hue}, 62%, 42%)` }}
        >
          <div className="notebook-page-body">
            {showCover && (
              <>
                {c.subject && (
                  <div className="notebook-subject" dir={contentDir} style={{ textAlign }}>
                    {c.subject}
                  </div>
                )}
                <h1 className="notebook-title" dir={contentDir} style={{ textAlign }}>
                  {notebookTitle}
                </h1>
                {c.summary && (
                  <p className="notebook-summary" dir={contentDir} style={{ textAlign }}>
                    <MathText text={c.summary} dir={mathDir} />
                  </p>
                )}
              </>
            )}

            {printMode ? (
              <div className="stack">
                {pages.map((page, i) => (
                  <ErrorBoundary key={i} fallback={<div className="empty">This page couldn't be displayed.</div>}>
                    <div>{renderPage(page)}</div>
                  </ErrorBoundary>
                ))}
              </div>
            ) : (
              <ErrorBoundary
                key={clampedIndex}
                fallback={
                  <div className="empty">
                    This page couldn't be displayed — try Prev/Next to move to another page.
                  </div>
                }
              >
                <div
                  className={`notebook-page-anim ${pageDirection === "next" ? "notebook-page-next" : "notebook-page-prev"}`}
                >
                  {pages[clampedIndex] && renderPage(pages[clampedIndex])}
                </div>
              </ErrorBoundary>
            )}
          </div>
        </div>

        {!printMode && pages.length > 1 && (
          <div className="notebook-nav no-print">
            <button
              className="btn btn-ghost btn-sm"
              disabled={clampedIndex === 0}
              onClick={() => {
                setPageDirection("prev");
                setPageIndex((p) => Math.max(0, p - 1));
              }}
            >
              ← Prev
            </button>
            <span className="page-count">
              Page {clampedIndex + 1} of {pages.length}
            </span>
            <button
              className="btn btn-ghost btn-sm"
              disabled={clampedIndex === pages.length - 1}
              onClick={() => {
                setPageDirection("next");
                setPageIndex((p) => Math.min(pages.length - 1, p + 1));
              }}
            >
              Next →
            </button>
          </div>
        )}
      </div>
    );
  }

  // ---------- List view ----------
  const atNotebookLimit = notebooks.length >= MAX_NOTEBOOKS_PER_USER;

  return (
    <div>
      <h1>📓 Notebook Generator</h1>
      <p className="page-sub">
        Upload a PDF, PowerPoint, or MP3 recording — we'll turn it into structured study notes
        with headlines, bullet points, and tables where content compares naturally.
      </p>

      <div className="panel" style={{ maxWidth: 560 }}>
        <div className="meta" style={{ marginBottom: 14 }} dir="ltr">
          {notebooks.length} / {MAX_NOTEBOOKS_PER_USER} notebooks
        </div>
        {atNotebookLimit ? (
          <div className="empty">
            You've reached the limit of {MAX_NOTEBOOKS_PER_USER} notebooks. Delete one below to
            make room for a new one.
          </div>
        ) : (
          <>
            <label>Notebook language</label>
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value as "en" | "he")}
              disabled={uploading}
              style={{ marginBottom: 14 }}
            >
              <option value="en">English</option>
              <option value="he">עברית (Hebrew)</option>
            </select>
            <label>Upload source (PDF/PPTX up to 20 MB, MP3 up to 150 MB)</label>
            <input
              ref={fileInput}
              type="file"
              accept=".pdf,.pptx,.mp3,application/pdf,application/vnd.openxmlformats-officedocument.presentationml.presentation,audio/mpeg"
              disabled={uploading}
              onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])}
            />
            {error && <div className="auth-error" style={{ marginTop: 8 }}>{error}</div>}
          </>
        )}
      </div>

      <div className="stack" style={{ marginTop: 20 }}>
        {notebooks.map((n) => (
          <div
            className={`panel${n.status === "done" ? " list-card" : ""}`}
            key={n.id}
            style={{ cursor: n.status === "done" ? "pointer" : "default" }}
            onClick={() => n.status === "done" && setSelectedId(n.id)}
          >
            <h3 style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, margin: 0 }}>
              <span dir="auto">
                <span dir="ltr">{SOURCE_ICON[n.source_type]}</span> {n.title ?? n.original_filename}
              </span>
              {n.status === "done" && <span className="badge done">ready</span>}
              {n.status === "failed" && <span className="badge failed">failed</span>}
              {(n.status === "pending" || n.status === "running") && (
                <span className="badge pending">{n.status === "pending" ? "queued" : "generating…"}</span>
              )}
            </h3>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 6 }}>
              <span className="meta">{new Date(n.created_at).toLocaleString()}</span>
              <button className="btn btn-danger btn-sm" onClick={(e) => remove(n, e)}>
                Delete
              </button>
            </div>
            {n.status === "failed" && n.error && (
              <div className="auth-error" style={{ marginTop: 8 }}>{n.error}</div>
            )}
          </div>
        ))}
        {notebooks.length === 0 && (
          <div className="empty">Upload a file above to generate your first notebook.</div>
        )}
      </div>
    </div>
  );
}
