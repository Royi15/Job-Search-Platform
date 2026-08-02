import { useEffect, useRef, useState } from "react";
import mermaid from "mermaid";

let initialized = false;
function ensureInit() {
  if (initialized) return;
  mermaid.initialize({
    startOnLoad: false,
    theme: "neutral",
    securityLevel: "strict",
    suppressErrorRendering: true,
  });
  initialized = true;
}

let idCounter = 0;

// Mermaid only treats " as meaningful when it wraps an entire label
// (A["some, label"]) — a stray " in the middle of an unwrapped label
// breaks its parser outright. This happens in practice with Hebrew
// abbreviations that use the gershayim mark (e.g. תנ"ך, רמב"ם), which is
// typed with the same character as a straight quote. The prompt tells the
// model to avoid this, but that's not a guarantee, so swap any quote that
// isn't immediately touching a bracket (i.e. not part of Mermaid's own
// label-wrapping syntax) for the real Hebrew gershayim character — visibly
// identical to a reader, but a different codepoint Mermaid never treats as
// a delimiter.
function sanitizeMermaid(code: string): string {
  return code.replace(/(?<![[({])"(?![\])}])/g, "״");
}

/** Renders model-generated Mermaid flowchart syntax as an inline SVG. The
 * model occasionally produces syntax that fails to parse — that's caught
 * and the block renders nothing rather than crashing the page or showing
 * raw Mermaid source, since a broken diagram isn't useful to a student and
 * one bad diagram shouldn't take out the rest of the notebook. */
export default function Diagram({ code }: { code: string }) {
  const [svg, setSvg] = useState<string | null>(null);
  const idRef = useRef(`notebook-diagram-${idCounter++}`);

  useEffect(() => {
    ensureInit();
    let cancelled = false;
    mermaid
      .render(idRef.current, sanitizeMermaid(code))
      .then(({ svg }) => {
        if (!cancelled) setSvg(svg);
      })
      .catch(() => {
        if (!cancelled) setSvg(null);
      });
    return () => {
      cancelled = true;
    };
  }, [code]);

  if (!svg) return null;
  return <div className="notebook-diagram" dir="ltr" dangerouslySetInnerHTML={{ __html: svg }} />;
}
