# JERVIS Skills

Agent skills from [JERVIS](https://jervislab.ai). Each skill is a folder under `skills/` that your coding agent loads on demand.

## wiki-ingest

Turns the material you read into a wiki your agent maintains and queries. Every source lands in `refs/` first, then gets absorbed into linked pages under `wiki/`: a summary per source, concept pages for the transferable rules, and entity pages for the people and organizations involved. You stay in the loop. Each ingest pauses for a discussion step, since the judgments you make while reading are the part an agent cannot produce alone.

```bash
npx skills add jervislab/skills --skill wiki-ingest
```

It has three modes:

- **Single** absorbs one source through Assess, Discuss, and Execute.
- **Friction** turns the friction your agents logged in `inbox.md` into scripts, skill gotchas, or `AGENTS.md` rules.
- **Lint** checks link integrity and page conventions across the wiki.

### What it touches

On first run in a project without `wiki/index.md`, the skill runs `scripts/scaffold-wiki.sh`, which creates:

```
refs/                  raw sources, read-only
wiki/concepts/         transferable frameworks
wiki/summaries/        one page per source
wiki/entities/         people, products, organizations
wiki/index.md          routing table
wiki/log.md            ingest log
wiki/overview.md       system overview
glossary.md            project terms (skipped if present)
inbox.md               friction ledger (skipped if present)
.claude/settings.json  adds a PostToolUse hook that runs wiki-lint on edits (skipped if already wired)
```

It also appends a Wiki Layer section to your project's `AGENTS.md`. The scripts need `python3` and make no network calls. Everything stays in your folder.

## License

[FSL-1.1-ALv2](LICENSE.md). This is source-available: you can use, modify, and redistribute it for any purpose except building a competing product. Each version converts to Apache 2.0 two years after release.
