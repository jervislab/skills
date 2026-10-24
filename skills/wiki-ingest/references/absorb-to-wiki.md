# Absorb to Wiki

Read one source and absorb it into wiki knowledge pages. Complements absorb-to-reference and can run in parallel on the same source, building a traceable knowledge network through `[[wiki-link]]`.

## Principle

Wisdom is subtraction: extract transferable frameworks and mindsets. The wiki holds only the judgments and connections taken out of the source; the argument stays in sources/. Cases, analogies, worked numbers, and anecdotes in the source are the author's argument — write the rule they support, or drop them. Cases the user brings from their own experience during Discuss are user input and may stay.

## Three-layer architecture

sources/ (raw, source of truth) → wiki/ (agent-maintained processing layer) → AGENTS.md Wiki Layer (schema).

## Workflow

### 1. Assess

Read and examine the whole source; settle on the core thesis and its decomposition before choosing an absorption strategy.

Judge the knowledge delta: which facts, views, and methods does the source bring that the wiki does not yet cover? Does it correct, challenge, or reinforce claims on existing pages? Read `wiki/index.md` to locate the affected pages.

A self-consistent methodology gets its own concept page; scattered facts and insights fuse into existing pages. Keep a complete methodology architecturally whole.

### 2. Discuss

Discuss the key findings with the user to decide the direction and emphasis of absorption. Discuss sets priority, not inclusion — knowledge not emphasized in discussion still enters the summary page. Insights that emerge during discussion are part of the knowledge delta.

### 3. Extract

Extract the source's delta against pre-training common knowledge plus existing wiki knowledge. Mark each identified framework as a concept-page candidate.

### 4. Restructure

Rebuild the source's decomposition independently. Question every classification axis; the output should be a better decomposition.

Output has two layers. The summary page (`wiki/summaries/`) holds the source's framework — decomposition, core judgments, methodological skeleton — bound to a single source, linking back to it with `[[link]]` when phenomenon-level support is needed. Concept pages (`wiki/concepts/`) extract from the summary the invariant rules that transfer across domains. The two connect through `[[wiki-link]]` without restating each other: the summary links to concepts for cross-domain rules, the concept links to the summary for source context, and each writes only its own layer. People, products, and organizations in the source get entity pages (`wiki/entities/`); see `entity-bootstrap.md` for that flow.

### Source attribution

A summaries/ page binds to a single source and holds only that source's knowledge. Knowledge from outside sources/ (user plans, original judgments) gets its own concept page, linked via `[[wiki-link]]`, and stays out of the summary page.

### 5. Fuse

Insert new content at the relevant spot in existing pages, strengthening weaker statements in place. When a new source reveals that existing concepts share an underlying rule, connect them with `[[wiki-link]]`.

A new framework gets a new concept page; existing concept pages absorb new perspectives or corrections. When a new source contradicts an existing page, mark the disagreement explicitly on the affected page. Add new facts to existing entity pages; a new entity worth standing alone gets its own page.

Every new page has at least one inbound link. Find the places in existing pages that should link to the new page and add the `[[wiki-link]]`, and give the new page its outbound links.

### 6. Audit

Run the per-page lint (SKILL.md Lint Mode) on every page created or modified and fix what it reports. Then reread every insertion and modification for what the script cannot judge: knowledge accuracy, decomposition quality, contradiction marking, argument carried over from the source, and prose against the global AGENTS.md writing standards.

## Bookkeeping

### Page conventions

Frontmatter:

```
---
name: Page title, conclusion-first
description: One-line summary of mechanism or content, not repeating what name already says
source: sources/<file>
last_updated: YYYY-MM-DD
---
```

`name` is the human-readable title and carries the core conclusion at a glance; the filename is an English kebab-case slug, and the two need not correspond. The body carries no `# heading`.

`description` is the agent's retrieval hook: grepping frontmatter across the repo yields the knowledge map, so it states the mechanism or content in one line without repeating characters from name. `name: description` concatenated is the description column of `wiki/index.md`; the two share one source.

`source` points to the raw file path in sources/. Metadata such as url and author live only in the sources/ file. Knowledge from user conversation = `source: user input`.

When sources/ holds no original link (the source is a periodical excerpt, or lives outside sources/), append it: `source: xxx · https://xxx`. No separate `url` field, no markdown link.

Quote a YAML value as a whole when it starts with `[ { & * ! | > % @` or a quote mark.

Path as type: `concepts/`, `entities/`, `summaries/`.

Language: wiki pages follow the user's language; filenames are kebab-case.

Mixed-language text, for a wiki not written in English: keep the English when removing it loses information for the reader — technical terms (first occurrence as translated term (English term), the translation thereafter) and original quotations (translation first, original language in parentheses). Everything else in the wiki's language.

The first body section is always `## Overview`: one coherent paragraph stating the core thesis and conclusion. Cross-reference with `[[wiki-link]]` after that, written until globally unique: the basename when it is unique, otherwise the full path from the project root. Intermediate segments take no part in matching, so a partial path neither disambiguates nor raises an error.

Section naming: a section that only lists links is `## Related`; a section that explains in prose how the page differs from and complements adjacent concepts is `## Adjacent Concepts`. Use one or the other, never both.

### Index and Log

`wiki/index.md`: add the new page under its category (link + one-line description). Index only wiki-layer output (concepts/, summaries/, entities/), never sources/, scripts/, utils/, or other non-wiki content.

`wiki/log.md`: maintenance record, format `## [YYYY-MM-DD] ingest | Source title`, body naming the source path, pages created or updated, and key connections.
