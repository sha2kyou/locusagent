import i18n from "../i18n/index.ts";
import type { BadgeProps } from "@/components/ui/badge";

type EmbeddingState = "pending" | "ready" | "failed";

export function embeddingLabel(state: EmbeddingState): {
  text: string;
  variant: NonNullable<BadgeProps["variant"]>;
} {
  const variants: Record<EmbeddingState, NonNullable<BadgeProps["variant"]>> = {
    pending: "warning",
    ready: "success",
    failed: "neutral",
  };
  return {
    text: i18n.t(`embedding.status.${state}`),
    variant: variants[state],
  };
}

/** @deprecated use embeddingLabel() */
export const EMBEDDING_LABEL = {
  pending: { get text() { return embeddingLabel("pending").text; }, variant: "warning" as const },
  ready: { get text() { return embeddingLabel("ready").text; }, variant: "success" as const },
  failed: { get text() { return embeddingLabel("failed").text; }, variant: "neutral" as const },
};
