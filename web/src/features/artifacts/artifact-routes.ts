import type { ArtifactCategory } from "@/api/types";
import { withWorkspacePrefix } from "@/app/workspace-route";

export function defaultArtifactsPath(
  categories: ArtifactCategory[],
  workspaceId: string | null | undefined,
): string | null {
  if (categories.length === 0) return null;
  return withWorkspacePrefix(`/artifacts/c/${categories[0].id}`, workspaceId);
}
