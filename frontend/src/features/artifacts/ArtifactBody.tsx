import type { ArtifactEntry } from "@/api/types";
import { ProseMarkdown } from "@/features/chat/Markdown";

export function ArtifactBody({ artifact }: { artifact: ArtifactEntry }) {
  if (artifact.type === "text")
    return (
      <pre className="whitespace-pre-wrap wrap-break-word font-mono text-[13px] leading-relaxed">
        {artifact.content}
      </pre>
    );
  if (artifact.type === "latex" || artifact.type === "markdown") {
    return <ProseMarkdown text={artifact.content} enableMath />;
  }
  return (
    <pre className="whitespace-pre-wrap wrap-break-word font-mono text-[13px] leading-relaxed">
      {artifact.content}
    </pre>
  );
}
