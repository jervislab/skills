# Health Audit

Some health questions need a page read: whether a claim still holds, whether a document is written for the agent that reads it. Only an agent with the vault in front of it can answer them, so the judgment is made here and written to the vault-root ledger `health-audit.md`. `sync.py` reads the ledger and reports rule, path, and date; it never judges. Findings never go into a page's frontmatter.

## Rules

- `rot`: a claim that newer material contradicts, a page that points at something that no longer exists, or a page that no longer matches how the user works now.
- `voice`: an agent-facing document, such as AGENTS.md, CLAUDE.md, or a SKILL.md, written for a human reader: narrative background, repetition, reasoning the agent cannot act on.

## Audit

1. Take the rule and scope from the request; without one, `rot` over `wiki/`.
2. Read each page in scope. For `rot`, compare it with the sources and pages newer than it. For `voice`, ask whether each paragraph changes what the agent does.
3. Fix what is clear. Ask the user where the judgment is theirs, such as whether an old practice still holds.
4. Write what stays open to the ledger, replacing that rule's previous section, then commit.

## Ledger

```markdown
# Health audit

## rot · 2026-10-25 · wiki/

- wiki/concepts/pricing.md · rot · 2026-10-25 · newer price in sources/price-2026.md

## voice · 2026-10-25 · AGENTS.md

- AGENTS.md · voice · 2026-10-25 · three paragraphs of background
```

- A section is one audit: `## <rule> · <YYYY-MM-DD> · <scope>`. Scope is a path or folder relative to the vault root.
- A line is one open finding: `- <path> · <rule> · <YYYY-MM-DD> · <note>`. The note is for the person reading the ledger and never leaves the machine.
- An audit with nothing open keeps its section with no lines, so its date still counts.
- Delete a line once its finding is fixed. The ledger holds the present; JERVIS keeps the history.
- A page edited after its finding's date reads as waiting for a recheck; the next audit of that rule settles it.
