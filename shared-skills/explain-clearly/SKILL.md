---
name: explain-clearly
description: Explain complex concepts, processes, or debated topics in clear, layered language matched to the audience (layperson / business / technical). Use for "what is this", "explain simply", "explain to a child/boss/client".
triggers:
  - explain
  - plain language
  - simply
  - what does it mean
  - make it clear
  - primer
  - beginner
  - ELI5
  - how to say it clearly
---

# Explain Clearly

## When to use

Before related work, call `skill_view{name: "explain-clearly"}` to load the full body.

Use for **understanding** tasks, e.g.:
- Explain terms, principles, policies, product features
- Rewrite specialist content for a target audience
- Answer "why" and "how it works"
- Tutoring: step through a concept (not doing homework for the user)

**Not for**: research needing fresh facts (use research-brief / web_search first); removing AI writing tone (humanizer).

## Principles

1. **Match the audience**: layperson / business decision-maker / learner with basics—sets metaphor depth and jargon.
2. **Structure**: one-sentence definition → why it matters → how it works (steps or analogy) → common misconceptions → recap.
3. **Analogies must be accurate**: help intuition, then note limits of the analogy.
4. **Avoid false precision**: mark uncertain claims as "generally thought…"; do not invent data.
5. **Length fits the scene**: short for briefings; headings for self-study.

## Output modes

**Default**
- Core definition (1–2 sentences)
- Bullet explanation
- One everyday example
- "One line to remember"

**Compare** (user asks difference between A and B)
- Similarities → key differences → when to use each

**Ladder** (user wants zero to understanding)
- Level 1 intuition → Level 2 mechanism → Level 3 detail (stop when user says stop)

## Platform conventions

- Deliver in chat; use `artifact_save` if user wants a card or handout.
- For medical, legal, financial explanations add "Not professional advice; consult a licensed expert for important decisions."
