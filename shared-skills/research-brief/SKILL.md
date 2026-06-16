---
name: research-brief
description: Research and structured summary around a question—integrate known facts, list items to verify, separate opinion from evidence. For non-coding info tasks like "look this up", "research", "compare options", "background".
triggers:
  - research
  - look up
  - help me understand
  - background
  - compare
  - study
  - compile info
  - summarize sources
  - research brief
---

# Research Brief

## When to use

Before related work, call `skill_view{name: "research-brief"}` to load the full body.

Use when **scattered information must become readable conclusions**, e.g.:
- Background on a product, policy, industry, or person
- Compare options, services, or approaches
- Fact base for writing, decisions, or meetings
- User gives links or attachments and asks for key points

**Not for**: polishing when the user already gave a full answer (humanizer); live web retrieval—use `web_search` / `web_extract` first, then this skill to organize.

## Workflow

1. **Clarify the question**: one sentence on what the user really wants; use `clarify` if scope is fuzzy.
2. **Gather**: conversation, `web_search`, `read_file`, user attachments; state gaps—do not fabricate.
3. **Separate layers**: fact / reasonable inference / unverified claim / your recommendation.
4. **Cite sources** where possible; mark unverified as "to confirm".
5. **Action-oriented**: end with 2–4 "if you go deeper…" or "decide after confirming…".

## Default output structure

```markdown
## Question
(restate the research question)

## Executive summary
(3–5 sentences, answer direction first)

## Key points
- ...

## Comparison / pros & cons (if applicable)
| Dimension | A | B |
|-----------|---|---|

## Uncertainty & gaps
- ...

## Suggested next steps
- ...
```

Long research may be split; for "brief only" keep executive summary + key points.

## Platform conventions

- Default: deliver in chat; `artifact_save` when user explicitly asks to save.
- Not legal, medical, or investment advice—add a boundary line for those topics.
