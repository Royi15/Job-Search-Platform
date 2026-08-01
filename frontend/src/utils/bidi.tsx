const IS_HEBREW = (ch: string) => /[֐-׿]/.test(ch);
const IS_LATIN = (ch: string) => /[A-Za-z0-9]/.test(ch);
const BRACKET_PAIRS: Record<string, string> = { "(": ")", "[": "]", "{": "}" };

// Hebrew text that hyphen- or bracket-attaches an English phrase with no
// space (e.g. "ה-Time complexity" or "ה(complexity)") breaks the browser's
// bidi reordering if we isolate whole whitespace-delimited tokens — the
// Hebrew letter gets dragged into the English run's LTR isolate along with
// it, which visually swaps their order and mirrors brackets the wrong way.
// Instead, classify every character as Hebrew/Latin/neutral and group into
// runs, wrapping only the Latin runs in <bdi dir="ltr">. Hebrew never
// enters an LTR isolate.
export function bidiSafe(text: string): (string | JSX.Element)[] {
  const chars = Array.from(text);
  const strong = chars.map((ch) => (IS_HEBREW(ch) ? "he" : IS_LATIN(ch) ? "la" : null));

  const nearestStrong = (from: number, step: 1 | -1): "he" | "la" | null => {
    for (let i = from; i >= 0 && i < chars.length; i += step) {
      if (strong[i]) return strong[i] as "he" | "la";
    }
    return null;
  };

  // A "(" and its matching ")" must resolve to the SAME script, or they stop
  // being a matched pair — e.g. a parenthetical mixing Hebrew and English
  // ("(תגובות מ-Chunk)") would otherwise attach the opening bracket to the
  // Hebrew word right after it and the closing bracket to the English word
  // right before it, landing them in different runs so they no longer
  // visually pair up. Match brackets with a stack, then assign both ends the
  // script of the first strong character actually inside the pair.
  const pairOf = new Array<number | null>(chars.length).fill(null);
  const openStack: number[] = [];
  chars.forEach((ch, i) => {
    if (BRACKET_PAIRS[ch]) openStack.push(i);
    else if (Object.values(BRACKET_PAIRS).includes(ch) && openStack.length) {
      const openIdx = openStack.pop()!;
      pairOf[openIdx] = i;
      pairOf[i] = openIdx;
    }
  });

  const effective: ("he" | "la")[] = new Array(chars.length);
  chars.forEach((ch, i) => {
    if (strong[i]) effective[i] = strong[i] as "he" | "la";
    else if (BRACKET_PAIRS[ch] && pairOf[i] !== null) {
      const closeIdx = pairOf[i]!;
      let inner: "he" | "la" | null = null;
      for (let k = i + 1; k < closeIdx; k++) if (strong[k]) { inner = strong[k] as "he" | "la"; break; }
      effective[i] = inner ?? nearestStrong(i - 1, -1) ?? nearestStrong(closeIdx + 1, 1) ?? "he";
    }
  });
  // Closing brackets take whatever script their (already-resolved) opener got.
  chars.forEach((ch, i) => {
    if (pairOf[i] !== null && effective[i] === undefined) effective[i] = effective[pairOf[i]!];
  });
  // Everything else (plain punctuation, unmatched brackets, spaces).
  chars.forEach((_ch, i) => {
    if (effective[i] === undefined) effective[i] = nearestStrong(i - 1, -1) ?? nearestStrong(i + 1, 1) ?? "he";
  });

  // A space OR trailing punctuation (. , ? ! ; :) that bridges two DIFFERENT
  // scripts must stand alone rather than merge into either neighboring run:
  // merging it into an LTR run pushes it to that run's own trailing edge,
  // but since the run's box is placed as one unit inside the outer RTL
  // flow, that edge faces away from the Hebrew word it's supposed to lead
  // into — so a trailing "," on an English word ends up on the wrong side,
  // same as the space bug. A boundary character between two words of the
  // SAME script (e.g. "Node.js") still merges normally.
  const isSpace = (ch: string) => /\s/.test(ch);
  const BOUNDARY_PUNCT = new Set([".", ",", "?", "!", ";", ":"]);
  const runs: { latin: boolean | null; text: string }[] = [];
  chars.forEach((ch, i) => {
    if (isSpace(ch) || BOUNDARY_PUNCT.has(ch)) {
      const prevLatin = runs.length ? runs[runs.length - 1].latin : null;
      const nextStrong = nearestStrong(i + 1, 1);
      const nextLatin = nextStrong === null ? null : nextStrong === "la";
      if (prevLatin !== null && nextLatin !== null && prevLatin !== nextLatin) {
        runs.push({ latin: null, text: ch });
        return;
      }
    }
    const latin = effective[i] === "la";
    const last = runs[runs.length - 1];
    if (last && last.latin === latin) last.text += ch;
    else runs.push({ latin, text: ch });
  });

  return runs.map((r, i) => (r.latin ? <bdi key={i} dir="ltr">{r.text}</bdi> : <span key={i}>{r.text}</span>));
}
