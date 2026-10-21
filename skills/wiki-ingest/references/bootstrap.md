# Bootstrap Wiki

Build an LLM Wiki from scratch.

An LLM Wiki is a two-layer system: the skill layer encodes capabilities the agent can execute, and the wiki layer encodes a knowledge network it can query. The two connect through `[[wiki-link]]`, rest on refs/ (immutable source material), and glossary.md keeps entropy in check.

## Phase 0: Ask

Collect four setup parameters in one AskUserQuestion round:

1. Purpose: what scenario does this LLM Wiki serve, and what problem does it solve?
2. Asset inventory: which existing assets can come in directly? [multi-select] (existing skills or prompt templates, existing documents, external captures, interview or meeting notes, starting from zero)
3. Core entity: who or what anchors the system? [free input] (usually the creator for a personal system; a product or organization for a team system)
4. Capability plan: which executable capabilities does the agent need? [free input] (each capability maps to one skill directory; with no clear plan yet, add them later)

## Phase 1: Scaffold

Run the script with the Ask results:

```bash
scripts/scaffold-wiki.sh <base_path> "<domain>" "<creator_name>"
```

The script creates the base structure:

```
<base_path>/
├── refs/                  # immutable source layer
├── wiki/
│   ├── concepts/          # reusable frameworks, decision models
│   ├── summaries/         # source summaries (each bound to one ref)
│   └── entities/          # people, products, organizations
├── wiki/index.md          # entry point for locating knowledge
├── wiki/log.md            # operation log
├── wiki/overview.md       # system overview (to be filled)
├── glossary.md            # global glossary: empty table with schema; sets the expectation, grows with each ingest
├── inbox.md               # friction ledger: agents write, humans consolidate, entries deleted once absorbed
└── .claude/settings.json  # PostToolUse hook: runs wiki-lint on every wiki edit; skipped if already wired
```

- The script creates no skill directories. The agent builds them in Phase 2 as the capability plan from Ask requires.
- The tool layer grows on demand, created with `mkdir -p` on first write: scripts start in `scripts/`, and templates and configs move into `utils/` only once there are enough to need grouping. Directories for the user's own habits (such as a personal drafts area) are theirs to create; the scaffold presets none.

## Phase 2: Seed

After the script finishes, the agent initializes the system:

1. Fill overview.md: write the system's purpose, core entity, layer relationships, and operating modes from the Ask results.

2. Create the anchor entity page: collect the entity's information through the `entity-bootstrap.md` flow and write the output to `wiki/entities/`. Update index.md.

3. Sort assets: scan the paths the user named in the asset inventory and route each asset by its nature:
   - Executable prompts, workflows, or SOPs → assess whether each deserves its own skill
   - Methodology and reference documents → copy to refs/
   - Executable scripts → scripts/; reusable templates and tool configs → utils/ (create on demand)
   - List a suggested ingest order (foundational, highly connected material first)

4. Initialize the capability layer: when Ask produced a clear capability plan, create a skeleton directory for each capability (SKILL.md frontmatter plus an empty references/). Content comes in later iterations.

Once Phase 2 is done, the system is ready to run. Material goes through the normal wiki-ingest flow; capabilities iterate with skill-creator.

## Schema Integration

Read the `assets/agents-wiki-layer.md` template and append it to the project-root AGENTS.md.
