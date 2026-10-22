#!/usr/bin/env python3
"""Report a vault's structure to a JERVIS Dashboard. Optional: until `connect`
runs, every command is a silent no-op and nothing leaves the machine.

What is sent: the vault's name and path, and its structure tree (file and
folder names, paths, and whether each is missing, a skeleton, or filled).
Page content is never read into the report, only used locally to judge
fill and orphans.

    python3 scripts/sync.py connect <endpoint> <token>   save credentials, report once
    python3 scripts/sync.py push [vault_dir]             report a vault (default: cwd)
    python3 scripts/sync.py --hook                       PostToolUse hook: report the edited vault

Credentials live in ~/.jervis/sync.json (mode 600). The hook never fails an
edit: network errors are swallowed, and a vault is reported at most once a
minute.
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# Orphans come from the same link resolver wiki-lint uses, so the Dashboard
# and the lint never disagree about which page nothing links to
sys.path.insert(0, str(Path(__file__).resolve().parent))
from wikilink import ROUTING, Index, link_map, walk_docs  # noqa: E402

CONFIG = Path.home() / ".jervis" / "sync.json"
STATE = Path.home() / ".jervis" / "last-push.json"
THROTTLE_SECONDS = 60
TIMEOUT_SECONDS = 5

# What wiki-ingest scaffolds, grouped by the milestone that tracks each slot:
# the harness, then the know-how, then tools. Must match the Dashboard's
# browser scan so both read the same states.
#   aliases     other paths that fill the slot when the expected one is absent;
#               a path, since listings skip hidden folders
#   repository  a git repository, filled once it holds a commit
#   expand      list everything inside, at every depth
#   shallow     list what is directly inside, each entry read as a whole
LAYOUT = [
    {"name": "AGENTS.md", "kind": "file", "aliases": ["CLAUDE.md"]},
    {"name": "glossary.md", "kind": "file"},
    {"name": "inbox.md", "kind": "file"},
    {"name": "refs", "kind": "directory"},
    {"name": ".git", "kind": "directory", "repository": True},
    {
        "name": "wiki",
        "kind": "directory",
        "expand": True,
        "children": [
            {"name": "concepts", "kind": "directory"},
            {"name": "entities", "kind": "directory"},
            {"name": "index.md", "kind": "file"},
            {"name": "log.md", "kind": "file"},
            {"name": "overview.md", "kind": "file"},
            {"name": "summaries", "kind": "directory"},
        ],
    },
    # The user's skills, where Claude Code reads them and other agents read
    # .agents/skills; one node per skill, marked own where the agent judged so
    {"name": ".claude/skills", "kind": "directory", "aliases": [".agents/skills"], "shallow": True},
    # Written by hand or imported, as a Claude Design export
    {"name": "DESIGN.md", "kind": "file", "aliases": ["design-system"]},
    {"name": "scripts", "kind": "directory"},
]

SKILLS_SLOT = ".claude/skills"

FRONTMATTER = re.compile(r"^---\r?\n[\s\S]*?\r?\n---(?:\r?\n|$)")


# A page is filled once it has a body: the scaffold writes frontmatter only, so
# any body text is content. Any other file is filled once it holds anything.
def file_state(path: Path) -> str:
    if path.suffix != ".md":
        return "filled" if path.stat().st_size > 0 else "skeleton"
    text = path.read_text(encoding="utf-8", errors="replace")
    return "filled" if FRONTMATTER.sub("", text, count=1).strip() else "skeleton"


# Filled once the repository holds a commit: HEAD names a commit or a branch
# that exists. A .git file is a worktree's pointer into a repository with history
def repository_state(entry: Path) -> str:
    if entry.is_file():
        return "filled"
    head = entry / "HEAD"
    if not head.is_file():
        return "skeleton"
    ref = head.read_text(encoding="utf-8").strip()
    if not ref.startswith("ref: "):
        return "filled"
    branch = ref[len("ref: "):]
    if (entry / branch).is_file():
        return "filled"
    packed = entry / "packed-refs"
    if packed.is_file() and any(
        line.endswith(" " + branch) for line in packed.read_text(encoding="utf-8").splitlines()
    ):
        return "filled"
    return "skeleton"


def visible(directory: Path):
    return [entry for entry in directory.iterdir() if not entry.name.startswith(".")]


# A directory is filled once anything inside it is
def holds_content(directory: Path) -> bool:
    for entry in visible(directory):
        if entry.is_file():
            if file_state(entry) == "filled":
                return True
        elif entry.is_dir() and holds_content(entry):
            return True
    return False


# A slot below a hidden folder is reached by its path, since listings skip
# hidden entries
def locate(directory, present, path):
    if "/" not in path and not path.startswith("."):
        return present.get(path)
    entry = directory / path if directory else None
    return entry if entry and entry.exists() else None


def scan_level(directory, expected, list_all, parent_id, root, descend=True):
    present = {entry.name: entry for entry in visible(directory)} if directory else {}
    specs = {spec["name"]: spec for spec in expected}
    if list_all:
        for name, entry in present.items():
            specs.setdefault(name, {"name": name, "kind": "directory" if entry.is_dir() else "file"})
    ordered = sorted(specs.values(), key=lambda spec: spec["name"]) if list_all else list(specs.values())

    nodes = []
    for spec in ordered:
        # A present alias stands in for an absent expected name, under its own
        location, entry = spec["name"], None
        for candidate in [spec["name"], *spec.get("aliases", [])]:
            entry = locate(directory, present, candidate)
            if entry:
                location = candidate
                break
        node_id = f"{parent_id}/{location}" if parent_id else location
        node = {"id": node_id, "name": location.split("/")[-1], "path": f"{root}/{node_id}"}
        if location != spec["name"]:
            node["slot"] = spec["name"]
        # What is found decides how it reads: a slot may be filled by a file or
        # by a folder, as a design system is
        if entry.is_dir() if entry else spec["kind"] == "directory":
            node["folder"] = True
        if entry is None:
            nodes.append({**node, "state": "missing"})
        elif spec.get("repository"):
            nodes.append({**node, "state": repository_state(entry)})
        elif entry.is_file():
            nodes.append({**node, "state": file_state(entry)})
        elif not (spec.get("expand") or spec.get("shallow") or (list_all and descend)):
            nodes.append({**node, "state": "filled" if holds_content(entry) else "skeleton"})
        else:
            children = scan_level(
                entry, spec.get("children", []), True, node_id, root, descend=not spec.get("shallow")
            )
            node["state"] = "filled" if any(c["state"] == "filled" for c in children) else "skeleton"
            if children:
                node["children"] = children
            nodes.append(node)
    return nodes


# A skill the user made with their agent says so in its SKILL.md frontmatter,
# written by the agent once it has judged where the skill came from:
#   metadata:
#     origin: own
# Anything unmarked, installed or not yet judged, is not the user's own.
OWN_MARK = re.compile(
    r"^metadata:[ \t]*(?:\n[ \t]+.*)*?\n[ \t]+origin:[ \t]*[\"']?own[\"']?[ \t]*$"
    r"|^metadata:[ \t]*\{[^}]*\borigin:[ \t]*[\"']?own\b",
    re.M,
)


def is_own(skill: Path) -> bool:
    manifest = skill / "SKILL.md"
    if not manifest.is_file():
        return False
    frontmatter = FRONTMATTER.match(manifest.read_text(encoding="utf-8", errors="replace"))
    return bool(frontmatter and OWN_MARK.search(frontmatter.group(0)))


def mark_own(nodes, vault: Path):
    for node in nodes:
        if node.get("slot", node["id"]) == SKILLS_SLOT:
            for skill in node.get("children", []):
                if is_own(vault / skill["id"]):
                    skill["own"] = True
    return nodes


# Wiki pages no other wiki page or wiki canvas links to, routing pages excepted:
# what wiki-lint reports as having no inbound link. A canvas only ever links
# out; it is never an orphan itself
def orphans_of(vault: Path) -> set:
    index = Index([rel.as_posix() for _, rel in walk_docs(vault, [], True)])
    links = link_map(vault, index)
    linked = {hit for source, hits in links.items() for hit in hits if hit != source}
    return {page for page in links
            if page.endswith(".md") and page not in linked and Path(page).name not in ROUTING}


def mark_orphans(nodes, orphans):
    for node in nodes:
        if node["id"] in orphans:
            node["orphan"] = True
        if "children" in node:
            mark_orphans(node["children"], orphans)
    return nodes


def display_path(vault: Path) -> str:
    try:
        return "~/" + str(vault.relative_to(Path.home()))
    except ValueError:
        return str(vault)


def scan(vault: Path):
    root = display_path(vault)
    nodes = mark_own(scan_level(vault, LAYOUT, False, "", root), vault)
    return root, mark_orphans(nodes, orphans_of(vault))


def load_config():
    try:
        return json.loads(CONFIG.read_text())
    except (OSError, ValueError):
        return None


def post(config: dict, body: dict | None):
    data = json.dumps(body).encode() if body else b""
    request = urllib.request.Request(
        config["endpoint"],
        data=data,
        method="POST",
        headers={"Authorization": f"Bearer {config['token']}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        return json.loads(response.read() or b"{}")


def push(vault: Path, config: dict) -> dict:
    root, tree = scan(vault)
    return post(config, {
        "vault": {"name": vault.name, "path": root, "absolutePath": str(vault)},
        "tree": tree,
    })


def connect(endpoint: str, token: str) -> int:
    config = {"endpoint": endpoint, "token": token}
    try:
        post(config, None)
    except urllib.error.HTTPError as error:
        print(f"JERVIS refused the token ({error.code}); get a fresh one from the Dashboard", file=sys.stderr)
        return 1
    except (urllib.error.URLError, TimeoutError) as error:
        print(f"Could not reach {endpoint}: {error}", file=sys.stderr)
        return 1
    CONFIG.parent.mkdir(mode=0o700, exist_ok=True)
    CONFIG.write_text(json.dumps(config, indent=2) + "\n")
    CONFIG.chmod(0o600)
    print(f"Connected to JERVIS. Saved to {CONFIG}")
    return 0


# The vault is the nearest ancestor holding wiki/, the scaffold's signature
def vault_of(path: Path) -> Path | None:
    for candidate in [path, *path.parents]:
        if (candidate / "wiki").is_dir():
            return candidate
    return None


def throttled(vault: Path) -> bool:
    try:
        last = json.loads(STATE.read_text())
    except (OSError, ValueError):
        last = {}
    now = time.time()
    if now - last.get(str(vault), 0) < THROTTLE_SECONDS:
        return True
    last[str(vault)] = now
    STATE.parent.mkdir(mode=0o700, exist_ok=True)
    STATE.write_text(json.dumps(last))
    return False


def hook(config: dict) -> int:
    try:
        payload = json.load(sys.stdin)
        edited = Path(payload.get("tool_input", {}).get("file_path", ""))
        vault = vault_of(edited.parent if edited.suffix else edited)
        if vault and not throttled(vault):
            push(vault, config)
    except Exception:
        pass  # Reporting is a side channel; it never blocks an edit
    return 0


def main(argv) -> int:
    if len(argv) == 3 and argv[0] == "connect":
        return connect(argv[1], argv[2])
    config = load_config()
    if argv[:1] == ["--hook"]:
        return hook(config) if config else 0
    if argv[:1] == ["push"]:
        if not config:
            return 0
        vault = Path(argv[1] if len(argv) > 1 else ".").resolve()
        try:
            result = push(vault, config)
        except (urllib.error.URLError, TimeoutError) as error:
            print(f"JERVIS sync failed: {error}", file=sys.stderr)
            return 1
        print(f"Reported {vault.name} to JERVIS ({result.get('vault_id')})")
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
