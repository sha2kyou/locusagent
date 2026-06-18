/** GFM autolink 会把紧跟 URL 的 CJK/全角字符吞进 href；在裸链接后接这些字符时用尖括号限定边界。 */

const CODE_SEGMENT_RE = /(```[\s\S]*?```|`[^`\n]+`)/g;

const BARE_URL_RE =
  /(?:https?:\/\/[A-Za-z0-9\-._~:/?#[\]@!$&'()*+,;=%]+|www\.[A-Za-z0-9\-._~:/?#[\]@!$&'()*+,;=%]+)/g;

const CJK_OR_FULLWIDTH = /[\u3000-\u303f\uFF00-\uFFEF\u4E00-\u9FFF\u3400-\u4DBF]/;

function wrapBareUrlBeforeCjk(segment: string): string {
  return segment.replace(BARE_URL_RE, (match, offset, whole) => {
    const before = whole[offset - 1];
    if (before === "<" || before === "(" || before === "]") return match;
    const after = whole[offset + match.length];
    if (after && CJK_OR_FULLWIDTH.test(after)) return `<${match}>`;
    return match;
  });
}

/** 在 Markdown 解析前修正裸 URL 边界（跳过代码块与行内代码）。 */
export function normalizeBareAutolinks(text: string): string {
  return text
    .split(CODE_SEGMENT_RE)
    .map((segment, index) => (index % 2 === 1 ? segment : wrapBareUrlBeforeCjk(segment)))
    .join("");
}
