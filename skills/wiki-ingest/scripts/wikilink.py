"""判定一条 `[[wiki-link]]` 指向仓库里的哪个文件：给定链接文本与它所在的页面，返回目标路径。

规则同 Obsidian：整路径 → 相对来源页的路径 → 唯一同名 → 同名多个取离来源最近。

wiki-lint.py 与仓库里的双链图谱都 import 这一份，检查与图谱永远同一个答案。
"""

import json
import re
from collections import defaultdict
from pathlib import Path

# archive/archives 是已被取代的旧稿：留在图里会把过时的页面画成活节点，
# 还会让退役的链接继续参与枢纽计数
SKIP_DIRS = {".git", ".obsidian", "node_modules", ".venv", "venv", "__pycache__",
             ".trash", ".idea", ".vscode", "dist", "build", "archive", "archives",
             ".wrangler", ".next", ".cache"}

FENCE_RE = re.compile(r"```.*?```|~~~.*?~~~", re.S)
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
LINK_RE = re.compile(r"!?\[\[([^\[\]\n]+?)\]\]")

# 路由页只指路,没人链它是常态
ROUTING = {"index.md", "overview.md", "log.md"}
# 图片提示词是资产不是知识页,不进链接图
ASSET_DIRS = {"images"}


def walk_docs(root: Path, excludes, with_canvas: bool, skip_dirs=()):
    exts = ("*.md", "*.canvas") if with_canvas else ("*.md",)
    found = sorted(p for ext in exts for p in root.rglob(ext))
    skip = SKIP_DIRS | set(skip_dirs)
    real_root = root.resolve()
    for path in found:
        rel = path.relative_to(root)
        # 软链分身：目标在仓库内，本体会被自己扫到，分身再入图就是同一篇文档的两个节点。
        # 目标在仓库外的软链是唯一副本，照常保留
        real = path.resolve()
        if real != path.absolute() and real.is_relative_to(real_root):
            continue
        # 目录名匹配 parts，天然递归。--exclude 的 glob 是从右往左匹配的：
        # 'life-coach/*' 命中 life-coach/a.md，却漏掉 life-coach/sub/a.md ——
        # 要排掉一整棵子树，用 --skip-dir，别用 glob
        if any(part in skip for part in rel.parts):
            continue
        if any(rel.match(pattern) for pattern in excludes):
            continue
        yield path, rel

# only relative prefixes go ("./", "../", "/"): lstrip("./") also ate the dot of hidden folders, so [[.claude/...]]
# never resolved and fell back to an ambiguous basename
REL_PREFIX = re.compile(r"^(?:\.{1,2}/|/)+")

def drop_rel(path: str) -> str:
    return REL_PREFIX.sub("", path)

def extract_targets(text: str):
    """取出正文里的 wikilink 目标，跳过代码块——文档里讲语法的 [[concept]] 不是真链接。"""
    body = INLINE_CODE_RE.sub(" ", FENCE_RE.sub(" ", text))
    for raw in LINK_RE.findall(body):
        target = raw.split("|")[0].split("#")[0].split("^")[0].strip()
        target = drop_rel(target).strip()
        if target:
            yield target

def norm(key: str) -> str:
    key = key.replace("\\", "/").strip()
    return key[:-3] if key.lower().endswith(".md") else key

def rank(rel: str):
    """同名候选的末位取舍：md 优先于 canvas，再取路径最浅最短的。"""
    return (0 if rel.lower().endswith(".md") else 1, rel.count("/"), len(rel))

def nearness(source_rel: str):
    """同名候选按「离来源多近」排序——共享的目录层级越多越近，同目录 > 父目录 > 更远。

    这是 Obsidian 的规则，也是本仓库唯一正确的那个。sources/ 与 wiki/ 天然同名：
    wiki-ingest 按素材命名产出页面，于是每消费一篇素材就多一对。若按路径最浅取舍，
    sources/ 只有一层，永远赢——知识网络的边就全画进了原料层，而编辑器里看着一切正常。
    距离只在平手时才退回 rank()。"""
    src = Path(source_rel).parent.parts

    def score(rel: str):
        own = Path(rel).parent.parts
        shared = 0
        for a, b in zip(src, own):
            if a != b:
                break
            shared += 1
        return (-shared,) + rank(rel)

    return score

class Index:
    """Obsidian 式解析：整路径优先，其次相对来源的路径，再次唯一同名，
    同名多个时取离来源最近的（见 nearness），平手才退回 rank()。"""

    def __init__(self, rels):
        self.by_path = {}
        self.by_stem = defaultdict(list)
        for rel in rels:
            key = norm(rel)
            self.by_path[key.lower()] = rel
            self.by_stem[Path(key).name.lower()].append(rel)
            if Path(rel).suffix.lower() != ".md":   # [[foo]] 也能落到 foo.canvas
                self.by_stem[Path(rel).stem.lower()].append(rel)

    def resolve(self, target: str, source_rel: str):
        key = norm(target).lower()
        if key in self.by_path:
            return self.by_path[key]
        here = drop_rel(norm(str(Path(source_rel).parent / key)).lower())
        if here in self.by_path:
            return self.by_path[here]
        candidates = self.by_stem.get(Path(key).name, [])
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]
        return min(candidates, key=nearness(source_rel))

    def rivals(self, target: str, source_rel: str):
        """resolve() 给了答案之后,再答一句:这答案是距离定的,还是硬凑的。

        并列最近的候选多于一个时返回它们 —— 那时谁赢由 rank() 的最浅最短决定,与作者
        意图无关,只有人能选。有唯一最近者就返回空表:答案由距离定,Obsidian 会得出同一个,
        没有可修的东西,报它只是噪声。"""
        key = norm(target).lower()
        if key in self.by_path:
            return []
        here = drop_rel(norm(str(Path(source_rel).parent / key)).lower())
        if here in self.by_path:
            return []
        candidates = self.by_stem.get(Path(key).name, [])
        if len(candidates) < 2:
            return []
        score = nearness(source_rel)
        top = min(score(c)[0] for c in candidates)
        tied = [c for c in candidates if score(c)[0] == top]
        return tied if len(tied) > 1 else []

    def shortest_form(self, rel: str) -> str:
        """稳定命中 rel 的最短写法。basename 全局唯一就用 basename,否则只有从仓库根
        算起的完整路径管用 —— 中间层级不参与匹配,`[[entities/jervis]]` 和 `[[jervis]]`
        走的是同一条兜底,补一半路径既没消歧也没报错。"""
        key = norm(rel)
        name = Path(key).name
        return name if len(self.by_stem.get(name.lower(), [])) < 2 else key
        


def wiki_docs(wiki: Path, pattern: str):
    return sorted(p for p in wiki.rglob(pattern)
                  if not set(p.relative_to(wiki).parts[:-1]) & ASSET_DIRS)


def wiki_pages(wiki: Path):
    """链接图里的页面：wiki/ 下的 md，资产目录除外。标准件、代码、多媒体都不在图里，
    谈不上孤儿与否。"""
    return wiki_docs(wiki, "*.md")


def canvas_targets(text: str):
    """canvas 是 JSON：文本节点里的 [[链接]] 与文件节点指向的路径，都是它链出去的边。
    读不成 JSON 的 canvas 没有边。"""
    try:
        nodes = json.loads(text).get("nodes", [])
    except (ValueError, AttributeError):
        return
    for node in nodes:
        if node.get("type") == "text":
            yield from extract_targets(node.get("text", ""))
        elif node.get("type") == "file" and node.get("file"):
            yield drop_rel(node["file"])


def link_map(root: Path, index: Index) -> dict:
    """谁链向谁：来源 → 它解析得到的目标集合。来源是 wiki 页面，加上 wiki/ 下的 canvas ——
    只被 canvas 引用的页面也有入链。孤儿只在页面里判定，canvas 只当来源。
    wiki-lint、sync.py 与 Dashboard 的浏览器扫描用同一套规则，孤儿永远同一个答案。"""
    links = {}
    wiki = root / "wiki"
    for doc in wiki_docs(wiki, "*.md") + wiki_docs(wiki, "*.canvas"):
        src = doc.relative_to(root).as_posix()
        text = doc.read_text(encoding="utf-8", errors="replace")
        targets = canvas_targets(text) if doc.suffix == ".canvas" else extract_targets(text)
        links[src] = {hit for t in targets if (hit := index.resolve(t, src))}
    return links
