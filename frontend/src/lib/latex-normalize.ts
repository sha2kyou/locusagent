/** Repair LaTeX commands broken by JSON escape decoding — mirror agent/latex_normalize.py */

const MATH_SEGMENT_RE = /\$\$[\s\S]*?\$\$|\$[^$\n]+\$/g;

function fixLatexEscapesInMath(segment: string): string {
  return segment
    .replace(/\x08([a-zA-Z]+)/g, (_, rest: string) => `\\b${rest}`)
    .replace(/\x0c([a-zA-Z]+)/g, (_, rest: string) => `\\f${rest}`)
    .replace(/\x0d([a-zA-Z]+)/g, (_, rest: string) => `\\r${rest}`)
    .replace(/\x09([a-zA-Z]+)/g, (_, rest: string) => `\\t${rest}`)
    .replace(/\newline\b/g, "\\newline");
}

export function normalizeLatexInput(text: string): string {
  if (!text) return text;
  const globalFixed = text.replace(/\x08([a-zA-Z]+)/g, (_, rest: string) => `\\b${rest}`);
  return globalFixed.replace(MATH_SEGMENT_RE, (seg) => fixLatexEscapesInMath(seg));
}
