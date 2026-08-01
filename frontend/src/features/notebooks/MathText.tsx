import katex from "katex";
import "katex/dist/katex.min.css";
import { bidiSafe } from "../../utils/bidi";

// Matches $$block math$$ first (so its inner $ signs aren't mistaken for
// inline delimiters), then $inline math$ in whatever text remains.
const MATH_TOKEN = /\$\$([\s\S]+?)\$\$|\$([^$\n]+?)\$/g;

function renderKatex(latex: string, displayMode: boolean): string {
  try {
    return katex.renderToString(latex, { throwOnError: false, displayMode });
  } catch {
    return latex;
  }
}

/** Renders a string that may contain LaTeX math ($inline$ / $$block$$),
 * used everywhere notebook content (bullets, table cells, summaries) is
 * shown so formulas the model wrote render as real math, not raw LaTeX.
 *
 * Also Hebrew-safe: plain (non-math) segments run through bidiSafe() so
 * Hebrew/English mixed prose renders correctly, and math segments — like
 * an embedded English word — are isolated with dir="ltr" so a formula
 * embedded in an RTL sentence doesn't get dragged into the surrounding
 * reordering (math notation always reads left-to-right, regardless of the
 * notebook's language).
 *
 * `dir` is the notebook's own base direction. A $$block$$ formula renders
 * as a block-level <div> (needed to center it on its own line), which —
 * when nested inside the caller's <p>/<li> — forces any prose before/after
 * it in the same string into a browser-generated anonymous block box. That
 * box is supposed to inherit alignment from the ancestor's dir/text-align,
 * but that inheritance isn't reliable in practice for RTL (it silently
 * fell back to left-aligned in testing), so when this text actually
 * contains a block formula, every surrounding text segment gets its
 * alignment set directly instead of counting on inheritance. */
export default function MathText({ text, dir = "ltr" }: { text: string; dir?: "rtl" | "ltr" }) {
  const nodes: (string | { html: string; display: boolean })[] = [];
  let lastIndex = 0;

  for (const match of text.matchAll(MATH_TOKEN)) {
    const index = match.index ?? 0;
    if (index > lastIndex) nodes.push(text.slice(lastIndex, index));
    if (match[1] !== undefined) {
      nodes.push({ html: renderKatex(match[1], true), display: true });
    } else if (match[2] !== undefined) {
      nodes.push({ html: renderKatex(match[2], false), display: false });
    }
    lastIndex = index + match[0].length;
  }
  if (lastIndex < text.length) nodes.push(text.slice(lastIndex));

  const hasBlockMath = nodes.some((n) => typeof n !== "string" && n.display);
  const textAlign = dir === "rtl" ? "right" : "left";

  return (
    <>
      {nodes.map((n, i) =>
        typeof n === "string" ? (
          hasBlockMath ? (
            <span key={i} style={{ display: "block", textAlign }} dir={dir}>
              {bidiSafe(n)}
            </span>
          ) : (
            <span key={i}>{bidiSafe(n)}</span>
          )
        ) : n.display ? (
          <div key={i} className="katex-block" dir="ltr" dangerouslySetInnerHTML={{ __html: n.html }} />
        ) : (
          <span key={i} dir="ltr" dangerouslySetInnerHTML={{ __html: n.html }} />
        )
      )}
    </>
  );
}
