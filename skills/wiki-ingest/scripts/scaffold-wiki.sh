#!/bin/bash
# Usage: scaffold-wiki.sh <base_path> <domain>
# Creates the LLM Wiki system structure, plus the root inbox.md friction ledger
# (agent-written, human-consolidated). Pages get frontmatter only: a page's
# purpose and format live in its description, so any body text is content
# someone wrote, and JERVIS's sync can tell a filled page from an empty one
# without knowing what the scaffold put there.

set -euo pipefail

BASE="${1:?Usage: scaffold-wiki.sh <base_path> <domain>}"
DOMAIN="${2:?Missing domain}"
DATE=$(date +%Y-%m-%d)

mkdir -p "$BASE"/{sources,wiki/{concepts,summaries,entities}}

# .claude/skills — skip if it already exists
if [ ! -d "$BASE/.claude/skills" ]; then
  mkdir -p "$BASE/.claude/skills"
fi

# index.md — sections appear as the first page of each kind lands
cat > "$BASE/wiki/index.md" << INDEXEOF
---
name: Wiki Index
description: Routing table agents use to locate knowledge pages; one section per kind (Concepts, Summaries, Entities), each a table of page link and description, updated after every ingest or new page
last_updated: $DATE
---
INDEXEOF

# log.md
cat > "$BASE/wiki/log.md" << LOGEOF
---
name: Wiki Log
description: "Append-only ingest / create / update stream recording each absorption's source path, output pages, and key links; entries as \`## [YYYY-MM-DD] action | Title\`, action one of ingest, query, lint, create, update"
last_updated: $DATE
---
LOGEOF

# overview.md
cat > "$BASE/wiki/overview.md" << OVERVIEWEOF
---
name: $DOMAIN Overview
description: To be filled — one line on which layers make up this system and what each carries
last_updated: $DATE
---
OVERVIEWEOF

# glossary.md — global glossary; establishes "define each custom term in one place"; skip if it already exists
if [ ! -f "$BASE/glossary.md" ]; then
cat > "$BASE/glossary.md" << GLOSSARYEOF
---
name: Global Glossary
description: "Defines each project-specific concept in one place, distinct from pre-training knowledge, one line each as \`- Precise concept name: concise definition\`; agents append any coined term not yet listed"
last_updated: $DATE
---
GLOSSARYEOF
fi

# inbox.md — friction ledger; skip if it already exists
if [ ! -f "$BASE/inbox.md" ]; then
cat > "$BASE/inbox.md" << INBOXEOF
---
name: Friction Inbox
description: "Agents log recurring friction during tasks, one line each appended as \`- [YYYY-MM-DD] scenario: friction → candidate destination\`, with a \`×N\` count added when it recurs; a human periodically consolidates it into skill Gotchas, AGENTS.md, or scripts (references/friction-inbox.md in wiki-ingest), deleting each entry once absorbed with no history kept"
last_updated: $DATE
---
INBOXEOF
fi

# .claude/settings.json — PostToolUse hook runs wiki-lint on every edit; skip if already wired
SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BASE_ABS="$(cd "$BASE" && pwd)"
# skill inside the project → path via $CLAUDE_PROJECT_DIR, survives clone; global install → absolute path
case "$SKILL_DIR/" in
  "$BASE_ABS"/*) SCRIPTS="\$CLAUDE_PROJECT_DIR/${SKILL_DIR#"$BASE_ABS"/}/scripts" ;;
  *)             SCRIPTS="$SKILL_DIR/scripts" ;;
esac
# wiki-lint checks every edit; sync.py reports structure to JERVIS and is a
# silent no-op until `sync.py connect` has run
python3 - "$BASE/.claude/settings.json" "$SCRIPTS" << 'HOOKEOF'
import json, sys
from pathlib import Path
path, scripts = Path(sys.argv[1]), sys.argv[2]
settings = json.loads(path.read_text()) if path.exists() else {}
wired = json.dumps(settings)
hooks = settings.setdefault("hooks", {}).setdefault("PostToolUse", [])
if "wiki-lint.py" not in wired:
    hooks.append({
        "matcher": "Write|Edit|MultiEdit",
        "hooks": [{"type": "command", "command": f'python3 "{scripts}/wiki-lint.py" --hook',
                   "statusMessage": "Checking wiki backlinks...", "timeout": 20}]})
# sync.py follows every tool that can change files, shell included, and
# every prompt, which brings in what the user changed in their editor
if "sync.py" not in wired:
    sync = [{"type": "command", "command": f'python3 "{scripts}/sync.py" --hook', "timeout": 10}]
    hooks.append({"matcher": "Write|Edit|MultiEdit|NotebookEdit|Bash", "hooks": sync})
    settings["hooks"].setdefault("UserPromptSubmit", []).append({"hooks": sync})
path.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n")
HOOKEOF

python3 "$SKILL_DIR/scripts/sync.py" push "$BASE" || true

echo "Scaffolded LLM Wiki at $BASE"
echo "Next: fill overview.md, create entity page, sort assets, ingest first source."
