import type { ArtifactEntry } from "@/api/types";
import { HtmlRender, Markdown } from "@/features/chat/Markdown";

export function ArtifactBody({ artifact }: { artifact: ArtifactEntry }) {
  if (artifact.type === "html") return <HtmlRender html={artifact.content} />;
  if (artifact.type === "text")
    return (
      <pre className="whitespace-pre-wrap wrap-break-word font-mono text-[13px] leading-relaxed">
        {artifact.content}
      </pre>
    );
  return <Markdown text={artifact.content} />;
}
