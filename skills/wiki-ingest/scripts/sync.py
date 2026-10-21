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

CONFIG = Path.home() / ".jervis" / "sync.json"
STATE = Path.home() / ".jervis" / "last-push.json"
THROTTLE_SECONDS = 60
TIMEOUT_SECONDS = 5

# What wiki-ingest scaffolds plus scripts/, in the vault's reading order. Must
# match the Dashboard's browser scan so both read the same states.
LAYOUT = [
    {"name": "AGENTS.md", "kind": "file", "aliases": ["CLAUDE.md"]},
    {"name": "glossary.md", "kind": "file"},
    {"name": "inbox.md", "kind": "file"},
    {"name": "scripts", "kind": "directory"},
    {"name": "refs", "kind": "directory"},
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
]

FRONTMATTER = re.compile(r"^---\r?\n[\s\S]*?\r?\n---(?:\r?\n|$)")
LINK = re.compile(r"\[\[([^\]|#]+)")
HUBS = {"wiki/index.md", "wiki/log.md", "wiki/overview.md"}


def file_state(path: Path, pages: dict, node_id: str) -> str:
    if path.suffix != ".md":
        return "filled" if path.stat().st_size > 0 else "skeleton"
    text = path.read_text(encoding="utf-8", errors="replace")
    if node_id.startswith("wiki/"):
        pages[node_id] = text
    return "filled" if FRONTMATTER.sub("", text, count=1).strip() else "skeleton"


def visible(directory: Path):
    return [entry for entry in directory.iterdir() if not entry.name.startswith(".")]


# A directory is filled once anything inside it is
def holds_content(directory: Path) -> bool:
    for entry in visible(directory):
        if entry.is_file():
            if file_state(entry, {}, "") == "filled":
                return True
        elif entry.is_dir() and holds_content(entry):
            return True
    return False


def scan_level(directory, expected, list_all, parent_id, root, pages):
    present = {entry.name: entry for entry in visible(directory)} if directory else {}
    specs = {spec["name"]: spec for spec in expected}
    if list_all:
        for name, entry in present.items():
            specs.setdefault(name, {"name": name, "kind": "directory" if entry.is_dir() else "file"})
    ordered = sorted(specs.values(), key=lambda spec: spec["name"]) if list_all else list(specs.values())

    nodes = []
    for spec in ordered:
        if spec["name"] not in present:
            alias = next((name for name in spec.get("aliases", []) if name in present), None)
            if alias:
                spec = {**spec, "name": alias}
        node_id = f"{parent_id}/{spec['name']}" if parent_id else spec["name"]
        node = {"id": node_id, "name": spec["name"], "path": f"{root}/{node_id}"}
        entry = present.get(spec["name"])
        kind_matches = entry is not None and (entry.is_dir() if spec["kind"] == "directory" else entry.is_file())
        if not kind_matches:
            nodes.append({**node, "state": "missing"})
        elif entry.is_file():
            nodes.append({**node, "state": file_state(entry, pages, node_id)})
        elif not (spec.get("expand") or list_all):
            nodes.append({**node, "state": "filled" if holds_content(entry) else "skeleton"})
        else:
            children = scan_level(entry, spec.get("children", []), True, node_id, root, pages)
            node["state"] = "filled" if any(c["state"] == "filled" for c in children) else "skeleton"
            if children:
                node["children"] = children
            nodes.append(node)
    return nodes


# Wiki pages no other page links to with [[name]], hubs excepted
def orphans_of(pages: dict) -> set:
    by_name = {node_id.rsplit("/", 1)[-1].removesuffix(".md").lower(): node_id for node_id in pages}
    linked = set()
    for source, text in pages.items():
        for match in LINK.finditer(text):
            name = match.group(1).strip().rsplit("/", 1)[-1].removesuffix(".md").lower()
            target = by_name.get(name)
            if target and target != source:
                linked.add(target)
    return {node_id for node_id in pages if node_id not in linked and node_id not in HUBS}


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
    pages: dict = {}
    nodes = scan_level(vault, LAYOUT, False, "", root, pages)
    return root, mark_orphans(nodes, orphans_of(pages))


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
