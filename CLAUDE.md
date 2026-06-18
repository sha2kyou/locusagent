# Locus Agent — Agent 协作说明

## 设置持久化（必须遵守）

**所有「设置」界面里的参数都必须写入 `~/.locusagent/settings.json`（Windows：`%USERPROFILE%\.locusagent\settings.json`）。**

- **禁止**为设置项单独新建其它 JSON/配置文件（例如 ~~`desktop.prefs.json`~~）。
- 按功能分区，使用 `settings.json` 中的 section 字段，例如：
  - `app` — 时区、语言
  - `llm` / `tools` / `embedding` / `terminal` / `developer` — 应用与 Agent 配置
  - `desktop` — 桌面壳：菜单栏后台、开机自启、快捷对话快捷键、快捷窗位置等
  - `secrets` — 密钥（导出/备份时包含，勿硬编码）
- **Python**：在 `shared/src/locus_shared/settings_store.py` 的 `SettingsDocument` 中声明 section，通过 `load_settings_document` / `save_settings_document` 读写。
- **Rust 桌面壳**：只 merge 更新对应 section（如 `desktop`），不得覆盖 `settings.json` 其它字段。
- **导出/导入**：设置页的 settings.json 导出应包含全部 section；新增设置项时同步更新 schema 与导出逻辑。

新增或修改设置项时，先确认应归属哪个 section，再实现读写；不要引入第二套持久化路径。

## 版本别名（Release Codename）

发版时为 **minor / 重大版本** 取一个别名，主题锚定 **西安及周边景点**（含咸阳、渭南等）。GitHub Release 为英文正文，别名格式为 **英文（中文）**。

### 格式

- Release 标题：`v{semver} — {English Codename}（{中文景点名}）`
- Release 正文首行：`## v{semver} — {English Codename}（{中文景点名}）`
- 示例：`v0.2.0 — Bell Tower（钟楼）`
- 使用 em dash `—`；patch 版一般不加别名，除非用户明确要求

### 英文（中文）写法

别名在 GitHub Release **标题与正文首行**中须写成 **英文在前、中文景点名紧跟其后、置于全角括号内**：

```text
{English Codename}（{中文景点名}）
```

- **英文**：对外展示用 codename，1–2 个词、首字母大写（如 `Bell Tower`、`Giant Wild Goose Pagoda`）
- **中文**：对应西安及周边真实景点名，写在 **全角括号 `（）`** 内（如 `（钟楼）`、`（大雁塔）`）
- **顺序固定**：先英文、后中文；不要反过来，不要拆成两行，不要省略中文
- **Release 正文**其余段落保持英文；仅标题与首行标题行携带 `英文（中文）` 别名
- **已用记录表**「别名（Release 展示）」列与 Release 上字符串保持一致

反例（禁止）：

- `钟楼 — Bell Tower`（中文在前）
- `Bell Tower`（缺中文括号）
- `Bell Tower (钟楼)`（半角括号）

### 命名原则

- 优先选与当次里程碑气质相符的景点（如 rebranding、大功能可用「锚点/中心」类地标）
- 别名 1–2 个英文词，首字母大写；不强制 emoji
- 别名池见下方「候选景点」；已用过的记入「已用记录」，**不可重复**

### 已用记录

| 版本 | 别名（Release 展示） | 备注 |
|------|----------------------|------|
| v0.2.0 | Bell Tower（钟楼） | 西安城中心，与 Locus「锚点」语义一致；AgentPod → Locus Agent rebranding |

### 候选景点（西安及周边，未用尽前可从中选取）

**西安城区：** 大雁塔、小雁塔、城墙、碑林、大唐芙蓉园、大明宫、汉长安城、曲江池、永兴坊  
**西安近郊：** 兵马俑、华清池、骊山、终南山、楼观台  
**渭南：** 华山、少华山、司马迁祠、洽川  
**咸阳：** 乾陵、茂陵、汉阳陵、法门寺（宝鸡界，常归「西线」）

发新版前：查表避免重复 → 选定别名 → 更新 Release 标题/正文 → 在本表追加一行。
