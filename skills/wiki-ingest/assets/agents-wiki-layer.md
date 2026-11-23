## gotchas

- Maintain one durable master document per proposal or stage deliverable, updating its state, decisions, essential evidence, and open questions as it grows toward delivery; resume from it across sessions.
- When a global concept is easy to confuse, confirm it with the user, then add it to glossary.md
- Retrieve first; wisdom accumulated in the wiki serves as reference
- Wiki Layer: durable source documents (sources/ or the owning project location) → wiki/ (knowledge output maintained by the agent) → AGENTS.md (schema).

### Ingest

Step 1: Persist — use the task's existing master document in its owning project location; use sources/ when it has no established home. Keep tool responses, repeated checks, and diffs in memory or temporary storage, and write decision-relevant results into the master document. Capture URL originals in sources/ when selected for absorption. Maintaining the manuscript does not itself trigger wiki ingestion.

Step 2: Triage — after reading the full text, judge signal density and destination:
- reference: contains a reusable principle / method; absorb into the target skill's references/. Follow `references/absorb-to-reference.md`.
- wiki: contains narrative, argument chains, or entity information; trigger the `wiki-ingest` skill to produce wiki pages.
- skill: contains a methodology that can be encoded as an agent capability; go through the skill-creator flow.
- discard: skip knowledge output when reusable signal is insufficient; retain active task manuscripts, deliverables, and referenced sources, removing only captures with no remaining use.

Paths can run in parallel on the same material (one article can yield both a reference and a wiki page).

### Query

Read `wiki/index.md` to locate → read the relevant pages, following `source:` to the canonical document when needed → synthesize the answer.

### Lint

Each wiki edit lints the edited page; fix what it reports in the same change. A full checkup and the judgment calls no script can make go through the wiki-ingest skill's Lint Mode.

### Page Conventions

Frontmatter has four fields in fixed order: `name` (title, conclusion-style preferred), `description` (one-line retrieval hook, not repeating name), `source` (canonical source document path or `user input`), `last_updated`. `index.md` and `overview.md` carry the first two plus `last_updated`.

The title lives only in frontmatter; the body has no `# heading`, and the first section is always `## Overview`. Directory path is the type (concepts/, entities/, summaries/). Language: wiki pages follow the user's language; filenames are English kebab-case. A section that only lists links is `## Related`; a section that explains in prose how a concept differs from and complements its neighbors is `## Adjacent Concepts`. Cross-reference with `[[wiki-link]]`. Project-specific terms are defined once in the root `glossary.md`; pages reference them without re-explaining. References run one way, wiki → skill; skills do not depend on the wiki, and the reference is cut after absorb.

Before writing or editing a page, read the wiki-ingest skill's `references/absorb-to-wiki.md`. It exclusively owns edge-case rulings such as url attribution, YAML quoting, and mixed CJK–Latin spacing; they are not repeated here.

## Friction Inbox

Fix friction on the spot when you can; otherwise append one line to the root `inbox.md` for a human to consolidate, and leave skills and AGENTS.md untouched. Corrections and conventions land in files inside the project, never in storage outside it such as Claude Code's auto memory. Recurring friction appends `×N` to the original entry. Format and consolidation flow live in the wiki-ingest skill's `references/friction-inbox.md`; an intent to consolidate triggers it.