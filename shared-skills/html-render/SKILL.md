---
name: html-render
description: Produce self-contained HTML for in-chat rendering via [HTML_RENDER] markers in an isolated iframe. Use for charts (pie, bar, line, trend, ratio, radar — ECharts by default), dashboards, interactive cards/widgets, or when the user asks to render HTML or visualize results in chat.
triggers:
  - visualize
  - chart
  - dashboard
  - interactive card
  - HTML render
---

# HTML Render Skill

## Goal

Output runnable HTML that follows a fixed marker protocol so the frontend can render it safely inside an isolated iframe.

## When to use

Call `skill_view{name: "html-render"}` to load the full body before executing a related task.

Use this skill when the user asks to:
- show HTML visualizations in chat
- use ECharts or other browser chart libraries
- generate interactive cards or widgets
- explicitly render HTML in the conversation
- use the special marker protocol for HTML output

## Output protocol (required)

When outputting renderable HTML, wrap one complete block with these markers:

[HTML_RENDER]
<!doctype html>
<html>...</html>
[/HTML_RENDER]

Rules:
- Output only one `[HTML_RENDER]...[/HTML_RENDER]` block unless the user explicitly asks for multiple.
- HTML must be complete and self-contained (include `<!doctype html>`, `<html>`, `<head>`, `<body>`).
- Total HTML inside the `[HTML_RENDER]` block must be <= 6000 characters (hard limit).
- Do not wrap the block in Markdown code fences.
- Explanatory text must appear outside the marker block.

If over the limit:
- Trim styles, copy, and data points first to stay within 6000 characters.
- If needed, ship a minimal core visualization and note outside the block that it was trimmed to meet the limit.

Platform convention: `[HTML_RENDER]` output is for in-chat display only. Do not call `artifact_save` unless the user explicitly asks to save, export, or archive the HTML.

## Default technical spec

### 1) Prefer self-contained output
- Inline CSS and minimal JS when possible.
- Do not depend on project-local static assets unless the user explicitly requires it.
- Prefer pinned-version CDNs for external libraries.
- Background must be solid white (`#ffffff`); no dark or transparent backgrounds.

### 2) Charts default to ECharts

When the user requests a chart and does not specify another library, use ECharts.

Default CDN:
- `https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js`

Chart container conventions:
- Minimum height `>= 320px`
- Width `100%`
- Initialize after DOM ready
- Listen for window resize and call `chart.resize()`

### 3) Data organization
- Small datasets: inline as JS constants.
- Medium/large datasets: separate `data` and `option` with clear structure.
- Incomplete data: sample data is OK, but state "sample data" outside the block.

## Safety boundaries

Generated HTML must not include by default:
- `fetch` calls to private or internal APIs
- Access tokens, cookies, `localStorage`, or parent-window objects
- Hard-coded secrets (API keys, passwords, tokens)
- Auto-triggered destructive actions (auto-submit, delete, purchase, etc.)

If external network requests are truly required, state assumptions outside the marker block.

## Frontend integration (for implementation tasks)

When the user asks you to implement frontend rendering logic, use the minimal approach:

1. Parse marker blocks with a multiline non-greedy regex:
- `/\[HTML_RENDER\]([\s\S]*?)\[\/HTML_RENDER\]/`

2. Extract HTML into an isolated iframe:
- `iframe.srcdoc = extractedHtml`
- Recommended sandbox: `sandbox="allow-scripts"`
- Do not add `allow-same-origin` unless explicitly needed

3. Fallback:
- No marker match or parse failure: render as normal Markdown
- iframe render failure: show a short error message

4. Layout and styling:
- Avoid layout shift
- Keep container styling neutral; work in both light and dark chat themes

## Reply template

When the user requests a visualization:

1) Brief note outside the block:
- What is being shown
- What assumptions were used

2) The render block:

[HTML_RENDER]
<!doctype html>
<html>
  <head>...</head>
  <body>...</body>
</html>
[/HTML_RENDER]

3) Optional frontend integration notes outside the block if needed.

## Quality checklist

Before finishing, confirm:
- Marker protocol is correct.
- HTML is complete and runs standalone.
- ECharts uses the pinned version when used.
- No secrets or unsafe behavior.
- Readable at narrow chat widths.
