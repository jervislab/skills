#!/usr/bin/env python3
"""Report a vault's structure to a JERVIS Dashboard. Optional: until `connect`
runs, every command is a silent no-op and nothing leaves the machine.

What is sent: the vault's name and path, and its structure tree (file and
folder names, paths, and whether each is missing, a skeleton, or filled),
with each page's frontmatter `name` and `description` and the paths of the
pages it links to and from. With it go health counts: the repository's backup
state, the friction inbox's size, the size of what the agent loads every
session, the orphan and design-system readings the tree holds, and the
judgments the user's agent wrote to health-audit.md, as rule, path, and date
only. Page bodies are never read into the report, only used
locally to judge fill, orphans, links, and what changed since an audit.

    python3 scripts/sync.py connect <endpoint> <token>   save credentials, report once
    python3 scripts/sync.py push [vault_dir]             report a vault (default: cwd)
    python3 scripts/sync.py --hook                       hook: report the vault in the background

Credentials live in ~/.jervis/sync.json (mode 600). The hook never fails or
slows an edit: it hands the vault to a background flush and returns. The flush
waits until edits have paused for a few seconds, reports once, and reports
again if more edits landed meanwhile, so the last change always goes out;
a tree identical to the last one reported is not sent again.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import re
import subprocess
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
# Per vault: when it was last edited, a lock held by its one running flush,
# and the digest of the tree it last reported
PENDING = Path.home() / ".jervis" / "pending"
QUIET_SECONDS = 3
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
#   pages       list markdown pages only, at every depth below
LAYOUT = [
    {"name": "AGENTS.md", "kind": "file", "aliases": ["CLAUDE.md"]},
    {"name": "glossary.md", "kind": "file"},
    {"name": "inbox.md", "kind": "file"},
    {"name": "sources", "kind": "directory", "expand": True},
    {"name": ".git", "kind": "directory", "repository": True},
    {
        "name": "wiki",
        "kind": "directory",
        "expand": True,
        # The agent writes every wiki page as markdown; anything else here is an
        # attachment or misplaced, and would fill a folder that holds no page
        "pages": True,
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
# Build output and installed dependencies are no one's know-how, wherever they
# sit. Must match the Dashboard's browser scan.
CACHE_FOLDERS = {"__pycache__", "node_modules"}
CACHE_FILE = re.compile(r"\.pyc$", re.I)


def is_listed(entry: Path, pages: bool = False) -> bool:
    if entry.name.startswith("."):
        return False
    if entry.is_dir():
        return entry.name.lower() not in IMAGE_FOLDERS and entry.name not in CACHE_FOLDERS
    if pages:
        return entry.name.endswith(".md")
    return not (IMAGE_FILE.search(entry.name) or CACHE_FILE.search(entry.name))


def visible(directory: Path, pages: bool = False):
    return [entry for entry in directory.iterdir() if is_listed(entry, pages)]


# A directory is filled once anything inside it is
def holds_content(directory: Path, pages: bool = False) -> bool:
    for entry in visible(directory, pages):
        if entry.is_file():
            if file_state(entry) == "filled":
                return True
        elif entry.is_dir() and holds_content(entry, pages):
            return True
    return False


# A slot below a hidden folder is reached by its path, since listings skip
# hidden entries
def locate(directory, present, path):
    if "/" not in path and not path.startswith("."):
        return present.get(path)
    entry = directory / path if directory else None
    return entry if entry and entry.exists() else None


def scan_level(directory, expected, list_all, parent_id, root, descend=True, pages=False):
    present = {entry.name: entry for entry in visible(directory, pages)} if directory else {}
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
        pages_below = pages or spec.get("pages", False)
        if entry is None:
            if spec.get("candidate"):
                node["candidate"] = spec["candidate"]
            nodes.append({**node, "state": "missing"})
        elif spec.get("repository"):
            nodes.append({**node, "state": repository_state(entry)})
        elif entry.is_file():
            nodes.append({**node, "state": file_state(entry)})
        elif not (spec.get("expand") or spec.get("shallow") or (list_all and descend)):
            nodes.append({**node, "state": "filled" if holds_content(entry, pages_below) else "skeleton"})
        else:
            children = scan_level(
                entry,
                spec.get("children", []),
                True,
                node_id,
                root,
                descend=not spec.get("shallow"),
                pages=pages_below,
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
DESIGN_SKIP = {"node_modules", "sources", "wiki"}


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


# Health. What can be counted is counted here; what needs a page read, such
# as whether a page has rotted, is judged by the user's agent and written to
# health-audit.md, which this only reads. The Dashboard's Health applies the
# thresholds; this reports the numbers.

def git(vault: Path, *args) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(vault), *args],
            capture_output=True, text=True, timeout=TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


# Work that would be lost with the machine: nothing committed, nothing pushed
def backup_of(vault: Path) -> dict:
    if git(vault, "rev-parse", "--git-dir") is None:
        return {"repository": False}
    last = (git(vault, "log", "-1", "--format=%ct") or "").strip()
    # No upstream branch: nothing is tracked remotely, so nothing counts as pushed
    unpushed = git(vault, "rev-list", "--count", "@{upstream}..HEAD")
    status = git(vault, "status", "--porcelain") or ""
    return {
        "repository": True,
        "remote": bool((git(vault, "remote") or "").strip()),
        "unpushed": int(unpushed) if unpushed else None,
        "uncommitted": len(status.splitlines()),
        "lastCommitAt": int(last) if last else None,
    }


INBOX_ENTRY = re.compile(r"^- \[\d{4}-\d{2}-\d{2}\]")
INBOX_REPEAT = re.compile(r"×\s*(\d+)\s*$")


# Friction waiting to be consolidated, and how much of it has come back
def inbox_of(vault: Path) -> dict | None:
    inbox = vault / "inbox.md"
    if not inbox.is_file():
        return None
    entries = [line for line in inbox.read_text(encoding="utf-8", errors="replace").splitlines()
               if INBOX_ENTRY.match(line)]
    repeated = [line for line in entries
                if (count := INBOX_REPEAT.search(line)) and int(count.group(1)) >= 2]
    return {"open": len(entries), "repeated": len(repeated)}


# What the agent reads before every session: AGENTS.md and CLAUDE.md, with the
# files they pull in by @path, as Claude Code does, a few levels deep
RESIDENT = ["AGENTS.md", "CLAUDE.md"]
RESIDENT_IMPORT = re.compile(r"(?:^|\s)@([\w./-]+\.md)\b")
RESIDENT_DEPTH = 4
RESIDENT_FILE_BUDGET = 8_000
SKILL_BUDGET_LINES = 500


def resident_of(vault: Path) -> list[Path]:
    found, queue = [], [(vault / name, 0) for name in RESIDENT]
    while queue:
        page, depth = queue.pop(0)
        page = page.resolve()
        if page in found or not page.is_file() or vault.resolve() not in page.parents:
            continue
        found.append(page)
        if depth < RESIDENT_DEPTH:
            text = page.read_text(encoding="utf-8", errors="replace")
            queue += [(page.parent / match, depth + 1) for match in RESIDENT_IMPORT.findall(text)]
    return found


# The size of what loads every session, and the agent-facing pages past their
# budget: a resident file over its size, or a skill the user made over its
# length, since only the user's own skills are theirs to compress
def bloat_of(vault: Path, nodes) -> dict:
    root = vault.resolve()
    resident = resident_of(vault)
    over = [page.relative_to(root).as_posix() for page in resident
            if page.stat().st_size > RESIDENT_FILE_BUDGET]
    skills = next((node for node in nodes if node.get("slot", node["id"]) == SKILLS_SLOT), None)
    for skill in (skills or {}).get("children", []):
        page = vault / skill["id"] / "SKILL.md"
        if skill.get("own") and page.is_file():
            lines = page.read_text(encoding="utf-8", errors="replace").count("\n")
            if lines > SKILL_BUDGET_LINES:
                over.append(f"{skill['id']}/SKILL.md")
    return {
        "residentBytes": sum(page.stat().st_size for page in resident),
        "residentFiles": [page.relative_to(root).as_posix() for page in resident],
        "overBudget": over,
    }


# The audit ledger the user's agent keeps at the vault root. One section per
# audit, one line per open finding; the note after the date stays here:
#   ## rot · 2026-10-25 · wiki/
#   - wiki/concepts/pricing.md · rot · 2026-10-25 · note
AUDIT_FILE = "health-audit.md"
AUDIT_HEADING = re.compile(r"^## (rot|voice) · (\d{4}-\d{2}-\d{2}) · (.+?)\s*$")
AUDIT_FINDING = re.compile(r"^- (.+?) · (rot|voice) · (\d{4}-\d{2}-\d{2})(?: · .*)?$")


# Paths changed after a day: committed since, or not yet committed. Without a
# repository the file's own time stands in.
def changed_after(vault: Path, day: str, paths: list[str]) -> set:
    log = git(vault, "log", f"--since={day} 23:59:59", "--name-only", "--format=")
    if log is None:
        end = time.mktime(time.strptime(day, "%Y-%m-%d")) + 86400
        return {path for path in paths if (vault / path).exists() and (vault / path).stat().st_mtime >= end}
    status = git(vault, "status", "--porcelain") or ""
    uncommitted = {line[3:].strip().strip('"') for line in status.splitlines()}
    return {line.strip() for line in log.splitlines() if line.strip()} | uncommitted


def in_scope(path: str, scope: str) -> bool:
    scope = scope.strip().rstrip("/")
    return scope in ("", ".") or path == scope or path.startswith(scope + "/")


def audit_of(vault: Path) -> dict | None:
    ledger = vault / AUDIT_FILE
    if not ledger.is_file():
        return None
    audits, findings = [], []
    for line in ledger.read_text(encoding="utf-8", errors="replace").splitlines():
        if heading := AUDIT_HEADING.match(line):
            rule, day, scope = heading.groups()
            audits.append({"rule": rule, "date": day, "scope": scope})
        elif finding := AUDIT_FINDING.match(line):
            path, rule, day = finding.groups()
            findings.append({"path": path.strip(), "rule": rule, "date": day})
    pages = [rel.as_posix() for _, rel in walk_docs(vault, [], True)]
    for audit in audits:
        changed = changed_after(vault, audit["date"], pages)
        audit["changedSince"] = sum(
            1 for path in changed if path.endswith(".md") and in_scope(path, audit["scope"]))
    for finding in findings:
        finding["stale"] = finding["path"] in changed_after(vault, finding["date"], [finding["path"]])
    return {"audits": audits, "findings": findings}


# Readings the tree already holds, kept with the rest so each has a history
def structure_of(nodes) -> dict:
    def walk(list_):
        for node in list_:
            yield node
            yield from walk(node.get("children", []))

    flat = list(walk(nodes))
    design = next((node for node in nodes if node.get("slot", node["id"]) == DESIGN_SLOT), None)
    return {
        "orphans": sum(1 for node in flat if node.get("orphan")),
        "design": "present" if design and design["state"] != "missing"
        else "candidate" if design and design.get("candidate") else "missing",
    }


def health_of(vault: Path, nodes) -> dict:
    return {
        "backup": backup_of(vault),
        "inbox": inbox_of(vault),
        "bloat": bloat_of(vault, nodes),
        "audit": audit_of(vault),
        "structure": structure_of(nodes),
    }


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


def report_of(vault: Path) -> dict:
    root, tree = scan(vault)
    return {
        "vault": {"name": vault.name, "path": root, "absolutePath": str(vault)},
        "tree": tree,
        "health": health_of(vault, tree),
    }


def push(vault: Path, config: dict) -> dict:
    return post(config, report_of(vault))


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


def pending_of(vault: Path) -> Path:
    PENDING.mkdir(mode=0o700, parents=True, exist_ok=True)
    return PENDING / hashlib.sha1(str(vault).encode()).hexdigest()[:16]


def edited_at(pending: Path) -> float:
    try:
        return float(pending.with_suffix(".edited").read_text())
    except (OSError, ValueError):
        return 0.0


# Shell commands and prompts name no file, so the session's folder stands in;
# a prompt catches what the user changed in their editor since the last turn
def hook(config: dict) -> int:
    try:
        payload = json.load(sys.stdin)
        edited = payload.get("tool_input", {}).get("file_path")
        start = Path(edited) if edited else Path(payload.get("cwd", "."))
        vault = vault_of(start.parent if start.suffix else start)
        if vault and not is_worktree(vault):
            pending_of(vault).with_suffix(".edited").write_text(str(time.time()))
            subprocess.Popen(
                [sys.executable, __file__, "--flush", str(vault)],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, start_new_session=True,
            )
    except Exception:
        pass  # Reporting is a side channel; it never blocks an edit
    return 0


# Every hook starts a flush; all but the one holding the vault's lock exit at
# once. An edit landing after the holder's report is caught either by that
# holder, which checks again once it lets go, or by the flush the edit started
def flush(vault: Path, config: dict) -> int:
    pending = pending_of(vault)
    while True:
        with open(pending.with_suffix(".lock"), "w") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                return 0
            while (wait := edited_at(pending) + QUIET_SECONDS - time.time()) > 0:
                time.sleep(wait)
            started = time.time()
            try:
                report = report_of(vault)
                digest = hashlib.sha256(json.dumps(report, sort_keys=True).encode()).hexdigest()
                sent = pending.with_suffix(".sent")
                if not sent.exists() or sent.read_text() != digest:
                    post(config, report)
                    sent.write_text(digest)
            except Exception:
                pass
        if edited_at(pending) < started:
            return 0


def main(argv) -> int:
    if len(argv) == 3 and argv[0] == "connect":
        return connect(argv[1], argv[2])
    config = load_config()
    if argv[:1] == ["--hook"]:
        return hook(config) if config else 0
    if argv[:1] == ["--flush"] and len(argv) == 2:
        return flush(Path(argv[1]), config) if config else 0
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
