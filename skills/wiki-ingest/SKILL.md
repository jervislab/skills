---
name: wiki-ingest
description: Ingest source material into the agent-maintained wiki layer. Single mode consumes one source with deep Discuss; Friction consolidates the root inbox.md friction ledger into skill Gotchas, AGENTS.md, or scripts; Lint checks link integrity and page conventions across the wiki.
---

## Gotchas

A wiki page's `source:` frontmatter points to its raw material in refs/, the source of truth. Before bootstrap or the first ingest, help the user inventory the material already on hand and gather it into refs/, then start producing pages. Pages produced without this step end up with broken source links or sources that must be tracked down again and again.

Skipping the summary page and jumping directly to concept pages is the most common failure. Every ref-source ingest produces a summary page. Concept pages extract frameworks from the summary; without it, concepts lose grounding.

Discussion insights need explicit capture. A reframing or connection the user surfaces during Discuss must land somewhere — usually a concept page linked from the summary.

A page's title lives only in the frontmatter `name`; the body opens with `## Overview` and carries no `# heading`. `description` and the index.md description column share one source — `name: description` concatenated is the index entry, so an edit to either must be mirrored in the other.

index.md only indexes wiki-layer output (concepts/, summaries/, entities/). Never add refs/, scripts/, utils/, or other non-wiki files to the index. Raw source provenance is already tracked by each wiki page's `source:` frontmatter.

The deep work of absorption — reading, judging, connecting — belongs to the human; the agent assists by structuring it and writing it to disk. Skipping Discuss and going straight to Execute outsources cognition to the agent and defeats the purpose of ingest.

## Principles

- Feed yourself: absorption works only through active engagement in reading, discussion, and output. Outsourcing cognition to the agent atrophies critical thinking.
- Wisdom is subtraction: the goal of absorption is to strip away surface phenomena and extract the invariant rules beneath, not to accumulate more knowledge nodes. More knowledge can confine; the wiki network grows wisdom by forging connections and discovering patterns.
- Let wisdom flow: think across disciplines and extract transferable frameworks and methods.

## Entry

Check `wiki/index.md` existence. If missing → `references/bootstrap.md` (Ask → scaffold → seed). If present → route to Single, Friction, or Lint mode. Any mode that writes wiki pages closes with a per-page lint on the pages it touched.

Entity page creation → `references/entity-bootstrap.md` (AskUserQuestion-guided collection, with person and organization branches). Anchor entities during Bootstrap, new entities surfaced in Single Mode, and pages the user asks for all take this path.

## Single Mode

Deep absorption of a single source.

### Phase 1: Assess (auto)

Read `wiki/index.md` in full. Read source material in full. Evaluate knowledge delta against wiki + pre-training. Present brief:

| Field | Content |
|-------|---------|
| Source | path or URL |
| Core thesis | one sentence |
| Knowledge delta | new vs wiki + pre-training |
| Affected pages | existing pages needing updates |
| Proposed outputs | pages to create, pages to modify |
| Strategy | standalone / fuse / mixed |
| Skill signal | flag when the source carries a methodology encodable as an agent capability; suggest the skill-creator flow |

Invite the user to read the source material themselves before continuing. If the source is long, highlight which sections carry the most signal.

### Phase 2: Discuss (human-led)

The primary absorption step. Agent facilitates, user drives.

Encourage the user to share: what struck them, what they disagree with, what connects to things they already know, what they want to remember. Probe with questions that deepen processing rather than summarize on the user's behalf. A reframing or connection the user surfaces here is knowledge the agent cannot generate alone.

If the user's takeaways diverge from the Assess brief, follow the user's reading. The brief is a proposal; the user's engagement is the ground truth.

Do NOT proceed to Execute without substantive user engagement. A bare "OK" is a gate pass, not a Discuss. When the user gives a minimal go-ahead, acknowledge it and proceed, but note that richer engagement produces richer wiki output.

### Phase 3: Execute (auto)

Run `references/absorb-to-wiki.md` steps 3-6 (Extract → Restructure → Fuse → Audit) + Bookkeeping as a continuous pass. Extract and Restructure require sustained reasoning across the full source. Weave in the user's Discuss insights as first-class knowledge — these often become concept pages or enrich existing ones beyond what the source alone provides.

## Friction Mode

Consumes the friction ledger agents append to during everyday tasks. Assign each entry a destination (Script / skill Gotchas / AGENTS.md / wiki / discard), execute after the Human Gate, and delete each entry once absorbed.

Recording criteria and the consolidation flow live in `references/friction-inbox.md`. The recording rule stays loaded through the project-root AGENTS.md, written there at scaffold time from `assets/agents-wiki-layer.md`.

## Lint Mode

Guards against wiki rot at edit time, not in a later cleanup. `scripts/wiki-lint.py` runs the quick mechanical pass; its docstring carries usage, and `scripts/scaffold-wiki.sh` wires it into a PostToolUse hook.

On invocation, run `--all` and fix what it reports. Then surface what no script can judge — stale claims, `[[concept]]` pages that should exist, fillable data gaps — as a list for the user to decide.

## JERVIS Sync

Optional. `scripts/sync.py` reports the vault's structure to a JERVIS Dashboard: the vault's name and path, and a tree of file and folder names with each one's fill state. Page content never leaves the machine. Until `sync.py connect <endpoint> <token>` has run, every sync command is a silent no-op.

Scaffold wires `sync.py --hook` into PostToolUse beside wiki-lint and reports once. A vault scaffolded before that has neither: once connected, add the same hook entry to its `.claude/settings.json` (the shape scaffold-wiki.sh writes), then run `sync.py push <vault>` once.

## Source Routing

| Input | First Step |
|-------|------------|
| refs/ path | Read directly |
| root `inbox.md` | Friction mode; never read it as source material |
| Other file path | Copy to refs/, then read |
| URL | Fetch → save to refs/, then read |
| Conversation text | Save to refs/ with descriptive filename, then read |

All sources land in refs/ before processing.