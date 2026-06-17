import { test } from "node:test";
import assert from "node:assert/strict";
import { buildFileTree, collectDirPaths } from "./skill-file-tree.ts";

test("buildFileTree groups nested paths", () => {
  const tree = buildFileTree([
    { path: "SKILL.md", is_dir: false, size: 10 },
    { path: "references", is_dir: true, size: null },
    { path: "references/guide.md", is_dir: false, size: 5 },
    { path: "scripts/run.sh", is_dir: false, size: 3 },
  ]);

  assert.equal(tree.length, 3);
  const refs = tree.find((node) => node.name === "references");
  assert.ok(refs?.isDir);
  assert.equal(refs?.children.length, 1);
  assert.equal(refs?.children[0]?.name, "guide.md");
});

test("collectDirPaths returns all expandable directories", () => {
  const tree = buildFileTree([
    { path: "references/guide.md", is_dir: false, size: 1 },
    { path: "scripts/run.sh", is_dir: false, size: 1 },
  ]);
  const paths = collectDirPaths(tree);
  assert.deepEqual([...paths].sort(), ["references", "scripts"]);
});
