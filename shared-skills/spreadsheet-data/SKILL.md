---
name: spreadsheet-data
description: Interpret tables and Excel/CSV data—trends, comparisons, anomalies, rollups, and chart suggestions. When users upload spreadsheets, ask what data means, want summaries, or need conclusions visualized.
triggers:
  - spreadsheet
  - Excel
  - xlsx
  - interpret data
  - analyze data
  - trend
  - pivot
  - what does this column mean
  - look at these numbers
---

# Spreadsheet Data

## When to use

Before related work, call `skill_view{name: "spreadsheet-data"}` to load the full body.

Use when **drawing conclusions from tables**, e.g.:
- User uploads `.xlsx` / `.csv` or pastes a table
- "Look at this data", "what grew fastest", "any anomalies"
- Compare, rank, share, or describe trends
- Narrate trends or comparisons in prose

**Not for**: pure format conversion, Excel formulas, database ETL (unless user only wants interpretation).

## Workflow

1. **Get data**: user attachment, paste, or `read_file` on workspace CSV; Excel attachments are parsed to text in chat.
2. **Confirm columns**: if headers are unclear, state assumptions or `clarify` key fields.
3. **Summary before detail**: row/column count → key metrics → findings → recommendations.
4. **Numbers carefully**: compute only from visible data; note units and time range; do not invent missing columns.
5. **Visualization**: describe charts in words when asked; use `artifact_save` for deliverables (markdown table or notes).

## Default output structure

```markdown
## Data overview
(rows/columns, time range, granularity)

## Main findings
- ...

## Anomalies or watch items
- ...

## Recommendations (optional)
- further analysis / chart type suggestions
```

## Platform conventions

- Default: deliver in chat; `artifact_save` for large-table conclusions.
- Do not write one-off table conclusions to long-term memory (background review should not persist them either).
