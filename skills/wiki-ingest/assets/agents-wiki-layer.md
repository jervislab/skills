## gotchas

- Write every intermediate artifact as a local md file
- When a global concept is easy to confuse, confirm it with the user, then add it to glossary.md
- Retrieve first; wisdom accumulated in the wiki serves as reference
- Wiki Layer: sources/ (raw, read-only) → wiki/ (knowledge output maintained by the agent) → AGENTS.md (schema).

### Ingest

Land all external material in sources/ before triage; skip no step.

Step 1: Fetch — capture as md and save to sources/. sources/ is the read-only raw layer.

Step 2: Triage — after reading the full text, judge signal density and destination:
- → reference: contains a reusable principle / method; absorb into the target skill's references/. Follow `references/absorb-to-reference.md`.
- → wiki: contains narrative, argument chains, or entity information; trigger the `wiki-ingest` skill to produce wiki pages.
- → skill: contains a methodology that can be encoded as an agent capability; go through the skill-creator flow.
- → discard: signal density too low; delete from sources/.

Paths can run in parallel on the same material (one article can yield both a reference and a wiki page).

### Query

Read `wiki/index.md` to locate → read the relevant pages, tracing back to sources/ when needed → synthesize the answer.

### Lint

Each wiki edit lints the edited page; fix what it reports in the same change. A full checkup and the judgment calls no script can make go through the wiki-ingest skill's Lint Mode.

### Page Conventions

Frontmatter has four fields in fixed order: `name` (title, conclusion-style preferred), `description` (one-line retrieval hook, not repeating name), `source` (sources/ path or `user input`), `last_updated`. `index.md`, `overview.md`, and `log.md` carry the first two plus `last_updated`.

The title lives only in frontmatter; the body has no `# heading`, and the first section is always `## Overview`. Directory path is the type (concepts/, entities/, summaries/). Language: wiki pages follow the user's language; filenames are English kebab-case. A section that only lists links is `## Related`; a section that explains in prose how a concept differs from and complements its neighbors is `## Adjacent Concepts`. Cross-reference with `[[wiki-link]]`. Project-specific terms are defined once in the root `glossary.md`; pages reference them without re-explaining. References run one way, wiki → skill; skills do not depend on the wiki, and the reference is cut after absorb.

Before writing or editing a page, read the wiki-ingest skill's `references/absorb-to-wiki.md`. It exclusively owns edge-case rulings such as url attribution, YAML quoting, and mixed CJK–Latin spacing; they are not repeated here.

## Friction Inbox

Fix friction on the spot when you can; otherwise append one line to the root `inbox.md` for a human to consolidate, and leave skills and AGENTS.md untouched. Corrections and conventions land in files inside the project, never in storage outside it such as Claude Code's auto memory. Recurring friction appends `×N` to the original entry. Format and consolidation flow live in the wiki-ingest skill's `references/friction-inbox.md`; an intent to consolidate triggers it. Unrelated to `sources/inbox.md` (the URL queue).
