import { ChevronRight, FileText, Folder } from "lucide-react";
import { cn } from "@/lib/utils";
import type { FileTreeNode } from "@/lib/skill-file-tree";

export function FileTree({
  nodes,
  selectedPath,
  expandedPaths,
  onToggleDir,
  onSelectFile,
  className,
}: {
  nodes: FileTreeNode[];
  selectedPath: string | null;
  expandedPaths: Set<string>;
  onToggleDir: (path: string) => void;
  onSelectFile: (path: string) => void;
  className?: string;
}) {
  return (
    <div className={cn("text-sm", className)}>
      {nodes.map((node) => (
        <FileTreeNodeRow
          key={node.path}
          node={node}
          depth={0}
          selectedPath={selectedPath}
          expandedPaths={expandedPaths}
          onToggleDir={onToggleDir}
          onSelectFile={onSelectFile}
        />
      ))}
    </div>
  );
}

function FileTreeNodeRow({
  node,
  depth,
  selectedPath,
  expandedPaths,
  onToggleDir,
  onSelectFile,
}: {
  node: FileTreeNode;
  depth: number;
  selectedPath: string | null;
  expandedPaths: Set<string>;
  onToggleDir: (path: string) => void;
  onSelectFile: (path: string) => void;
}) {
  const isDir = node.isDir;
  const expandable = isDir && node.children.length > 0;
  const expanded = expandable && expandedPaths.has(node.path);
  const selected = !isDir && selectedPath === node.path;

  if (isDir) {
    return (
      <div>
        <button
          type="button"
          onClick={expandable ? () => onToggleDir(node.path) : undefined}
          disabled={!expandable}
          className={cn(
            "flex w-full items-center gap-1.5 rounded-md px-2 py-1.5 text-left",
            expandable && "hover:bg-secondary/80",
            "font-medium text-foreground",
            !expandable && "cursor-default opacity-80",
          )}
          style={{ paddingLeft: `${depth * 12 + 8}px` }}
        >
          <ChevronRight
            className={cn(
              "size-3.5 shrink-0 text-muted-foreground transition-transform",
              expandable && expanded && "rotate-90",
              !expandable && "opacity-0",
            )}
          />
          <Folder className="size-3.5 shrink-0 text-muted-foreground" />
          <span className="truncate">{node.name}</span>
        </button>
        {expandable &&
          expanded &&
          node.children.map((child) => (
            <FileTreeNodeRow
              key={child.path}
              node={child}
              depth={depth + 1}
              selectedPath={selectedPath}
              expandedPaths={expandedPaths}
              onToggleDir={onToggleDir}
              onSelectFile={onSelectFile}
            />
          ))}
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={() => onSelectFile(node.path)}
      className={cn(
        "flex w-full items-center gap-1.5 rounded-md px-2 py-1.5 text-left hover:bg-secondary/80",
        selected ? "bg-secondary text-foreground" : "text-muted-foreground hover:text-foreground",
      )}
      style={{ paddingLeft: `${depth * 12 + 8 + 14}px` }}
    >
      <FileText className="size-3.5 shrink-0" />
      <span className="truncate font-mono text-xs">{node.name}</span>
    </button>
  );
}
