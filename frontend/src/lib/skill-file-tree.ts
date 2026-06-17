import type { SkillFileEntry } from "@/api/types";

export interface FileTreeNode {
  name: string;
  path: string;
  isDir: boolean;
  children: FileTreeNode[];
}

function sortTree(node: FileTreeNode) {
  node.children.sort((a, b) => {
    if (a.isDir !== b.isDir) return a.isDir ? -1 : 1;
    return a.name.localeCompare(b.name);
  });
  for (const child of node.children) {
    if (child.isDir) sortTree(child);
  }
}

export function buildFileTree(entries: SkillFileEntry[]): FileTreeNode[] {
  const root: FileTreeNode = { name: "", path: "", isDir: true, children: [] };

  for (const entry of [...entries].sort((a, b) => a.path.localeCompare(b.path))) {
    const parts = entry.path.split("/").filter(Boolean);
    let current = root;
    for (let i = 0; i < parts.length; i++) {
      const part = parts[i]!;
      const path = parts.slice(0, i + 1).join("/");
      const isLast = i === parts.length - 1;
      let child = current.children.find((node) => node.name === part);
      if (!child) {
        child = {
          name: part,
          path,
          isDir: !isLast || entry.is_dir,
          children: [],
        };
        current.children.push(child);
      } else if (isLast) {
        child.isDir = entry.is_dir;
      }
      current = child;
    }
  }

  sortTree(root);
  return root.children;
}

export function collectDirPaths(nodes: FileTreeNode[]): Set<string> {
  const paths = new Set<string>();
  const walk = (list: FileTreeNode[]) => {
    for (const node of list) {
      if (node.isDir && node.children.length > 0) {
        paths.add(node.path);
        walk(node.children);
      }
    }
  };
  walk(nodes);
  return paths;
}
