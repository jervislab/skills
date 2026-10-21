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
.claude/settings.json  PostToolUse hooks: wiki-lint and JERVIS sync on edits (each skipped if already wired)
```

It also appends a Wiki Layer section to your project's `AGENTS.md`. The scripts need `python3`.

### JERVIS sync (optional)

`scripts/sync.py` reports your vault's structure to a [JERVIS](https://jervislab.ai) Dashboard. It is off until you run `sync.py connect <endpoint> <token>` with a token from your Dashboard; before that, no script makes a network call.

Once connected, it sends the vault's name and path and a tree of file and folder names, each marked missing, skeleton, or filled. It never sends page content. Credentials live in `~/.jervis/sync.json`. Delete that file to disconnect.

## License

[FSL-1.1-ALv2](LICENSE.md). This is source-available: you can use, modify, and redistribute it for any purpose except building a competing product. Each version converts to Apache 2.0 two years after release.
