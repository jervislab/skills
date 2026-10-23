#!/usr/bin/env python3
"""Report a vault's structure to a JERVIS Dashboard. Optional: until `connect`
runs, every command is a silent no-op and nothing leaves the machine.

What is sent: the vault's name and path, and its structure tree (file and
folder names, paths, and whether each is missing, a skeleton, or filled),
with each page's frontmatter `name` and `description` and the paths of the
pages it links to and from. Page bodies are never read into the report, only
used locally to judge fill, orphans, and links.

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
from wikilink import (  # noqa: E402
    ROUTING,
    Index,
    canvas_targets,
    extract_targets,
    link_map,
    walk_docs,
    wiki_docs,
)

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
#   candidate   where an unmarked design system may sit, reported on the
#               missing slot
LAYOUT = [
    {"name": "AGENTS.md", "kind": "file", "aliases": ["CLAUDE.md"]},
    {"name": "glossary.md", "kind": "file"},
    {"name": "inbox.md", "kind": "file"},
    {"name": "refs", "kind": "directory", "expand": True},
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
    # One node per script; a folder inside is read whole, since a tool's
    # dependencies, such as node_modules, would bury the scripts
    {"name": "scripts", "kind": "directory", "shallow": True},
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


# Images carry nothing an agent reads, and a folder of clippings' images would
# outnumber the pages they illustrate: neither becomes a node or fills a slot.
# Must match the Dashboard's browser scan.
IMAGE_FOLDERS = {"image", "images"}
IMAGE_FILE = re.compile(r"\.(?:png|jpe?g|gif|webp|avif|heic|bmp|ico|tiff?|svgz?)$", re.I)


def is_listed(entry: Path) -> bool:
    if entry.name.startswith("."):
        return False
    if entry.is_dir():
        return entry.name.lower() not in IMAGE_FOLDERS
    return not IMAGE_FILE.search(entry.name)


def visible(directory: Path):
    return [entry for entry in directory.iterdir() if is_listed(entry)]


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
            if spec.get("candidate"):
                node["candidate"] = spec["candidate"]
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


# A judgment the agent records in a page's frontmatter, as `key: value` under
# metadata, block or flow style
def metadata_mark(key: str, value: str):
    return re.compile(
        rf"^metadata:[ \t]*(?:\n[ \t]+.*)*?\n[ \t]+{key}:[ \t]*[\"']?{value}[\"']?[ \t]*$"
        rf"|^metadata:[ \t]*\{{[^}}]*\b{key}:[ \t]*[\"']?{value}\b",
        re.M,
    )


def carries_mark(page: Path, mark) -> bool:
    if not page.is_file():
        return False
    frontmatter = FRONTMATTER.match(page.read_text(encoding="utf-8", errors="replace"))
    return bool(frontmatter and mark.search(frontmatter.group(0)))


# A skill the user made with their agent says so in its SKILL.md frontmatter,
# written by the agent once it has judged where the skill came from:
#   metadata:
#     origin: own
# Anything unmarked, installed or not yet judged, is not the user's own.
OWN_MARK = metadata_mark("origin", "own")


def is_own(skill: Path) -> bool:
    return carries_mark(skill / "SKILL.md", OWN_MARK)


# Skills a registry installed, by the names the vault's skills-lock.json lists
def registry_skills(vault: Path) -> set:
    try:
        return set(json.loads((vault / "skills-lock.json").read_text()).get("skills", {}))
    except (OSError, ValueError, AttributeError):
        return set()


def mark_skills(nodes, vault: Path):
    registry = registry_skills(vault)
    for node in nodes:
        if node.get("slot", node["id"]) == SKILLS_SLOT:
            for skill in node.get("children", []):
                if is_own(vault / skill["id"]):
                    skill["own"] = True
                if skill["name"] in registry:
                    skill["registry"] = True
    return nodes


# A design system kept below the root, or imported under another name, says so
# in its frontmatter, written by the agent once it has judged the page to be one:
#   metadata:
#     role: design-system
DESIGN_SLOT = "DESIGN.md"
DESIGN_MARK = metadata_mark("role", "design-system")
DESIGN_DEPTH = 2
# Folders that hold sources or know-how, never the design system itself
DESIGN_SKIP = {"node_modules", "refs", "wiki"}


# The marked page nearest the root, by name within a level, so this sync and
# the Dashboard's scan pick the same one
def find_design_mark(vault: Path) -> str | None:
    level = [vault]
    for _ in range(DESIGN_DEPTH + 1):
        following = []
        for directory in level:
            for entry in sorted(visible(directory), key=lambda entry: entry.name):
                if entry.is_dir():
                    if entry.name not in DESIGN_SKIP:
                        following.append(entry)
                elif entry.suffix == ".md" and carries_mark(entry, DESIGN_MARK):
                    return entry.relative_to(vault).as_posix()
        level = following
    return None


# A folder shaped like a design system: named as one, or laid out as a Claude
# Design export, its token sheet beside an entry page
def looks_like_design(directory: Path) -> bool:
    if "design-system" in directory.name.lower():
        return True
    names = {entry.name for entry in visible(directory)}
    return "colors_and_type.css" in names and bool({"SKILL.md", "README.md"} & names)


# The candidate nearest the root, by name within a level, as the mark is found
def find_design_candidate(vault: Path) -> str | None:
    level = [vault]
    for _ in range(DESIGN_DEPTH):
        following = []
        for directory in level:
            for entry in sorted(visible(directory), key=lambda entry: entry.name):
                if not entry.is_dir() or entry.name in DESIGN_SKIP:
                    continue
                if looks_like_design(entry):
                    return entry.relative_to(vault).as_posix()
                following.append(entry)
        level = following
    return None


# The scaffold's design slot needs no mark; only without it does the scan look
# deeper, and the marked page fills the slot as an alias. Without a mark, a
# folder shaped like a design system is named on the empty slot instead.
def layout_of(vault: Path):
    design = next(spec for spec in LAYOUT if spec["name"] == DESIGN_SLOT)
    names = [design["name"], *design.get("aliases", [])]
    if any((vault / name).exists() for name in names):
        return LAYOUT
    marked = find_design_mark(vault)
    if marked:
        found = {"aliases": [*names[1:], marked]}
    else:
        candidate = find_design_candidate(vault)
        if not candidate:
            return LAYOUT
        found = {"candidate": candidate}
    return [{**spec, **found} if spec is design else spec for spec in LAYOUT]


# Wiki pages no other wiki page or wiki canvas links to, routing pages excepted:
# what wiki-lint reports as having no inbound link. A canvas only ever links
# out; it is never an orphan itself
def orphans_of(vault: Path) -> set:
    index = Index([rel.as_posix() for _, rel in walk_docs(vault, [], True)])
    links = link_map(vault, index)
    linked = {hit for source, hits in links.items() for hit in hits if hit != source}
    return {page for page in links
            if page.endswith(".md") and page not in linked and Path(page).name not in ROUTING}


def front_matter(text: str) -> dict:
    """A page's own account of itself: frontmatter `name` and `description`, as
    plexus.py reads them. A block scalar gives its first line with content;
    quotes come off. Must match frontMatter in the Dashboard's wikilink.ts."""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    found = {}
    lines = text[3:end].splitlines()
    for i, line in enumerate(lines):
        for key in ("name", "description"):
            if key in found or not line.startswith(key + ":"):
                continue
            value = line[len(key) + 1:].strip()
            if value in ("|", ">", "|-", ">-"):
                value = next((l.strip() for l in lines[i + 1:] if l[:1] in (" ", "\t") and l.strip()), "")
            if len(value) > 1 and value[0] in ('"', "'") and value[-1] == value[0]:
                value = value[1:-1]
            if value:
                found[key] = value
    return {
        **({"title": found["name"]} if "name" in found else {}),
        **({"description": found["description"]} if "description" in found else {}),
    }


def stem_of(rel: str) -> str:
    return re.sub(r"\.(md|canvas)$", "", Path(rel).name, flags=re.I)


def pages_of(vault: Path):
    """Each page's and canvas's frontmatter and wiki-links out and in, read
    wherever the page is, as readLinkGraph in the Dashboard's wikilink.ts reads
    them. A linked page is named by its stem, prefixed with its folder where
    another page shares the stem."""
    indexed = [rel.as_posix() for _, rel in walk_docs(vault, [], True)]
    index = Index(indexed)
    wiki = vault / "wiki"
    under_wiki = [doc.relative_to(vault).as_posix()
                  for doc in wiki_docs(wiki, "*.md") + wiki_docs(wiki, "*.canvas")]
    sources = sorted(set(indexed) | set(under_wiki))
    meta, outgoing = {}, {}
    for rel in sources:
        text = (vault / rel).read_text(encoding="utf-8", errors="replace")
        is_canvas = rel.endswith(".canvas")
        if not is_canvas and (own := front_matter(text)):
            meta[rel] = own
        targets = canvas_targets(text) if is_canvas else extract_targets(text)
        outgoing[rel] = {hit for t in targets if (hit := index.resolve(t, rel)) and hit != rel}
    stems = {}
    for rel in sources:
        stems[stem_of(rel)] = stems.get(stem_of(rel), 0) + 1

    def ref(rel):
        folder = Path(rel).parent.name
        stem = stem_of(rel)
        return {"path": rel, "label": f"{folder}/{stem}" if stems[stem] > 1 and folder else stem}

    incoming = {}
    for source, targets in outgoing.items():
        for target in targets:
            incoming.setdefault(target, []).append(source)
    links = {rel: {"out": [ref(t) for t in sorted(outgoing[rel])],
                   "in": [ref(s) for s in sorted(incoming.get(rel, []))]}
             for rel in sources}
    return meta, links


def mark_pages(nodes, orphans, meta, links):
    """What the link graph knows of each node: orphan, frontmatter, links. A
    node's id is its vault-relative path, the graph's key."""
    for node in nodes:
        if node["id"] in orphans:
            node["orphan"] = True
        node.update(meta.get(node["id"], {}))
        if node["id"] in links:
            node["links"] = links[node["id"]]
        if "children" in node:
            mark_pages(node["children"], orphans, meta, links)
    return nodes


def display_path(vault: Path) -> str:
    try:
        return "~/" + str(vault.relative_to(Path.home()))
    except ValueError:
        return str(vault)


def scan(vault: Path):
    root = display_path(vault)
    nodes = mark_skills(scan_level(vault, layout_of(vault), False, "", root), vault)
    return root, mark_pages(nodes, orphans_of(vault), *pages_of(vault))


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


# A linked worktree is a branch of a vault checked out beside it, its .git a
# file pointing home: reported under its own folder name it would read as a
# second vault, and under the vault's it would overwrite the main checkout
def is_worktree(vault: Path) -> bool:
    return (vault / ".git").is_file()


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
        if vault and not is_worktree(vault) and not throttled(vault):
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
        if is_worktree(vault):
            print(f"{vault.name} is a git worktree; JERVIS tracks the main checkout", file=sys.stderr)
            return 0
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
