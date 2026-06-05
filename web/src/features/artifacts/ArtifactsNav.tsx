import { NavLink, useLocation } from "react-router-dom";
import { Package } from "lucide-react";
import {
  sidebarNavIconClass,
  sidebarNavIconSlotClass,
  sidebarNavLabelClass,
  sidebarNavRowClass,
} from "@/app/sidebar-nav-styles";

export function ArtifactsNav({
  basePrefix,
  expanded,
  onNavigate,
}: {
  basePrefix: string;
  expanded: boolean;
  onNavigate: () => void;
}) {
  const location = useLocation();
  const artifactsActive = location.pathname.includes("/artifacts");

  return (
    <NavLink
      to={`${basePrefix}/artifacts`}
      title="产物"
      onClick={onNavigate}
      className={sidebarNavRowClass(artifactsActive, expanded)}
    >
      <span className={sidebarNavIconSlotClass} aria-hidden>
        <Package className={sidebarNavIconClass} strokeWidth={1.75} />
      </span>
      <span className={sidebarNavLabelClass(expanded)}>产物</span>
    </NavLink>
  );
}
