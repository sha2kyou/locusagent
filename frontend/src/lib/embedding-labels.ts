import type { BadgeProps } from "@/components/ui/badge";

type EmbeddingState = "pending" | "ready" | "failed";

export const EMBEDDING_LABEL: Record<
  EmbeddingState,
  { text: string; variant: NonNullable<BadgeProps["variant"]> }
> = {
  pending: { text: "排队中", variant: "warning" },
  ready: { text: "已索引", variant: "success" },
  failed: { text: "仅关键词", variant: "neutral" },
};
