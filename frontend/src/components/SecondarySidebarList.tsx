import type { KeyboardEvent, ReactNode } from "react";
import {
  secondarySidebarHeaderClass,
  secondarySidebarHeaderTitleRowClass,
  secondarySidebarRowActionsClass,
  secondarySidebarRowClass,
  secondarySidebarRowLabelClass,
  secondarySidebarTitleClass,
} from "@/components/secondary-sidebar-styles";

export function SecondarySidebarHeader({
  title,
  actions,
  search,
}: {
  title: string;
  actions?: ReactNode;
  search: ReactNode;
}) {
  return (
    <div className={secondarySidebarHeaderClass}>
      <div className={secondarySidebarHeaderTitleRowClass}>
        <span className={secondarySidebarTitleClass}>{title}</span>
        {actions}
      </div>
      {search}
    </div>
  );
}

export function SecondarySidebarListRow({
  active,
  label,
  title,
  onClick,
  actions,
}: {
  active: boolean;
  label: string;
  title?: string;
  onClick: () => void;
  actions?: ReactNode;
}) {
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== "Enter" && e.key !== " ") return;
    e.preventDefault();
    onClick();
  };

  return (
    <div
      className={secondarySidebarRowClass(active)}
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={onKeyDown}
    >
      <span className={secondarySidebarRowLabelClass} title={title ?? label}>
        {label}
      </span>
      {actions ? (
        <div
          className={secondarySidebarRowActionsClass}
          onClick={(e) => e.stopPropagation()}
        >
          {actions}
        </div>
      ) : null}
    </div>
  );
}
