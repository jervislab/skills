# Friction Inbox (Consolidate)

Goal: understand the user's goal, not remember the incident. Consolidation turns that goal into structure every later agent meets.

Root `inbox.md` is the friction ledger, unrelated to `sources/inbox.md` (the URL queue). The recording rule lives in project-root AGENTS.md so it holds without this skill loaded.

## Record

Friction is any point where the project made the agent guess a missing convention, fail while following the docs, meet two contradicting docs, repeat a manual step, or take the same correction twice. Fix on the spot what can be fixed; the rest enters the inbox for human consolidation, with skills and AGENTS.md left untouched. Corrections and conventions land in project files, never in the agent's private memory.

Write each entry as the goal it blocked: `- [YYYY-MM-DD] context: friction → candidate destination`. A recurrence appends `×N` to the original entry and keeps the first date.

## Consolidate

Trigger intent: turn accumulated friction into durable structure — consolidating the ledger, or absorbing with root `inbox.md` as the target.

1. Place each entry in the most deterministic layer that can hold it: script or hook; else the owning skill's Gotchas; else AGENTS.md when it must hit across skills or without a skill loaded. An insight rather than a rule becomes a wiki page. Discard what is fixed elsewhere, a one-off preference, or still ×1 after a cycle.
2. Present one row per entry: entry, count, destination, change.
3. Execute after human confirmation. Skill changes go through skill-creator; script changes come with one real run.
4. Remove the processed entries and update `last_updated`. The consolidated artifact is its own record; write no separate log.
