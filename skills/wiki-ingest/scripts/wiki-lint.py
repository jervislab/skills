#!/usr/bin/env python3
"""检查 wiki 页面的双链完整性:断链、路径不符、路径已失效、歧义、无人引用、index.md 未收录、
frontmatter 残缺。

链接活着不等于链接对。页面链接的匹配只看最后一段,中间路径从不校验,同名多个时靠排序挑;
文件指针连解析器都不进,路径写错也无人管。三种都不算断链,却都指向别处 —— 单列成检查项。

两种触发:absorb-to-wiki 的 Audit 显式跑,任何 agent 都能执行;项目若装了
PostToolUse hook(scaffold-wiki.sh 写入),每次编辑 wiki/ 下的文档自动跑一次。
问题写到 stderr 并以 exit 2 交回 agent —— 编辑当场补链,比事后 lint 便宜得多。

链接解析不自己写一份:import 同目录的 wikilink.py,图谱与检查永远同一个答案。
项目根取页面(或 cwd)往上第一个含 wiki/ 的目录,脚本装在哪都不影响。

    python3 scripts/wiki-lint.py wiki/concepts/foo.md ...  逐页,有问题 → exit 2
    python3 scripts/wiki-lint.py --all                     全量体检,给人看 → exit 0
    python3 scripts/wiki-lint.py --hook                    读 stdin 的 hook payload
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wikilink import SKIP_DIRS, Index, extract_targets, norm, walk_docs  # noqa: E402

# main() 定位项目根后赋值
ROOT = WIKI = None
# 路由页只指路,没人链它是常态;它们的 frontmatter 也少一个 source
ROUTING = {"index.md", "overview.md", "log.md"}
# 图片提示词是资产不是知识页,不按页面规范要求它
ASSET_DIRS = {"images"}
FIELDS = ("name", "description", "source", "last_updated")
ROUTING_FIELDS = ("name", "description", "last_updated")

KEY_RE = re.compile(r"^([A-Za-z_][\w-]*):", re.M)


def front_keys(text: str) -> set:
    if not text.startswith("---"):
        return set()
    end = text.find("\n---", 3)
    return set(KEY_RE.findall(text[3:end] if end > 0 else ""))


def build_index() -> Index:
    return Index([rel.as_posix() for _, rel in walk_docs(ROOT, [], True)])


def non_page_targets():
    """wiki → skill 是单向引用,目标是目录;`[[plexus.py]]` 一类指向具体文件。
    两者都解析不成页面,却都是约定内的写法 —— 既非页面又非文件/目录的才是断链。

    分两套返回。这类目标不进解析器,写出来的路径没有任何东西会去核对它,文件一搬家
    旧路径就静默留着 —— 所以整路径单独存一份,写了路径的按整路径校验,只写名字的才靠裸名放行。"""
    paths, names = set(), set()
    for path in ROOT.rglob("*"):
        rel = path.relative_to(ROOT)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        paths.add(rel.as_posix().lower())
        names.add(path.name.lower())
        if path.is_file():
            names.add(path.stem.lower())
    return paths, names


def wiki_pages():
    return sorted(p for p in WIKI.rglob("*.md")
                  if not set(p.relative_to(WIKI).parts[:-1]) & ASSET_DIRS)


def inbound_map(index: Index) -> dict:
    """谁链向谁。一次读完整个 wiki,单页检查也用它 —— 97 篇小文件,比反复 grep 快。"""
    links = {}
    for page in wiki_pages():
        src = page.relative_to(ROOT).as_posix()
        text = page.read_text(encoding="utf-8")
        hit = set()
        for target in extract_targets(text):
            resolved = index.resolve(target, src)
            if resolved:
                hit.add(resolved)
        links[src] = hit
    return links


def front_value(text: str, key: str) -> str:
    m = re.search(rf"^{key}:[ \t]*(.*)$", text.split("\n---", 1)[0], re.M)
    return m.group(1).strip().strip("\"'") if m else ""


CELL_SPLIT = re.compile(r"(?<!\\)\|")


def indexed_pages(index: Index) -> dict:
    """被 index.md 收录的页面 → 它那一行的描述列。描述列是 frontmatter 的派生物,
    只认「链接 | 描述」两列的行;skill 路由表三列,不受这条约束,记为 None。"""
    idx = WIKI / "index.md"
    if not idx.exists():
        return {}
    listed = {}
    for line in idx.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in CELL_SPLIT.split(line.strip().strip("|"))]
        for t in extract_targets(line):
            r = index.resolve(t, "wiki/index.md")
            if r:
                own_row = len(cells) == 2 and cells[0] == f"[[{t}]]"
                listed.setdefault(r, cells[1] if own_row else None)
                if own_row:
                    listed[r] = cells[1]
    return listed


def link_shape(target: str, hit: str, index: Index, rel: str) -> list:
    """链接解析成功之后仍要问两件事,因为解析器对两者都保持沉默。

    一、答案是排序挑的吗。同名候选多于一个时 rank() 取最浅最短,Obsidian 取离来源最近,
    同一条链接在图谱和编辑器里可以指向不同文件。
    二、写出来的路径是真的吗。匹配只用最后一段,中间层级从不校验,所以
    `[[design-system/SKILL]]` 会静默落到 intake/SKILL.md —— 读的人以为自己看懂了。

    两种都只有一个修法:写成 index.shortest_form() 给的形态。"""
    issues = []
    want = index.shortest_form(hit)
    rivals = index.rivals(target, rel)
    if rivals:
        # 不替作者选一个:平手时谁赢由最浅最短决定,与他想说的是哪一篇无关。
        opts = " / ".join(f"[[{norm(c)}]]" for c in rivals)
        issues.append(f"歧义 [[{target}]] —— {len(rivals)} 个同名文件离这里一样远,"
                      f"当前硬凑给了 {hit};写全你要的那个:{opts}")
    else:
        probe = norm(target).lower().strip("/")
        whole = norm(hit).lower()
        if "/" in probe and whole != probe and not whole.endswith("/" + probe):
            issues.append(f"路径不符 [[{target}]] —— 实际命中 {hit};"
                          f"中间层级不参与匹配,写全 [[{want}]] 或只写 [[{Path(want).name}]]")
    return issues


def check(page: Path, index: Index, links: dict, listed: set, others: tuple) -> list:
    rel = page.relative_to(ROOT).as_posix()
    text = page.read_text(encoding="utf-8")
    issues = []
    file_paths, file_names = others

    for target in dict.fromkeys(extract_targets(text)):
        hit = index.resolve(target, rel)
        if hit:
            issues += link_shape(target, hit, index, rel)
            continue
        probe = target.replace("\\", "/").lower().lstrip("./")
        if probe in file_paths:
            continue                      # 指向 skill 目录或具体文件,路径核对无误
        if Path(probe).name in file_names:
            if "/" in probe:
                issues.append(f"路径已失效 [[{target}]] —— 仓库里没有这条路径,"
                              f"只有同名文件;文件搬过就改引用,别留一条读着可信的死路径")
            continue                      # 只写名字,没有路径可校验
        issues.append(f"断链 [[{target}]] —— 仓库里没有这个目标,改名了就改引用,没写就先别引")

    if page.name not in ROUTING:
        sources = [s for s, hit in links.items() if s != rel and rel in hit]
        prose = [s for s in sources if Path(s).name not in ROUTING]
        if not prose:
            issues.append("无入链 —— 从最相邻的那个概念引一次,孤岛页面等于没写"
                          if not sources else
                          "只有路由页链它 —— 索引是目录不是关系,正文之间还欠一条边")
        if rel not in listed:
            issues.append("wiki/index.md 未收录 —— 补一行,描述列取 `name: description`")
        elif listed[rel] is not None:
            want = f"{front_value(text, 'name')}: {front_value(text, 'description')}"
            if listed[rel] != want:
                issues.append("index 描述列与 frontmatter 不符 —— 改成 `name: description`,"
                              "页面是源,index 只派生")

    want = ROUTING_FIELDS if page.name in ROUTING else FIELDS
    missing = [f for f in want if f not in front_keys(text)]
    if missing:
        issues.append("frontmatter 缺 " + "、".join(missing))

    return issues


def locate(start: Path):
    """往上第一个含 wiki/ 的目录即项目根;找不到返回 None。"""
    for d in (start, *start.parents):
        if (d / "wiki").is_dir():
            return d
    return None


def hook_target() -> list:
    """PostToolUse payload 里被编辑的文件;解析不了就当没有。"""
    try:
        path = json.load(sys.stdin).get("tool_input", {}).get("file_path")
    except (ValueError, AttributeError):
        return []
    return [path] if path else []


def main() -> None:
    global ROOT, WIKI
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)

    if args[0] == "--all":
        ROOT = locate(Path.cwd().resolve())
        if ROOT is None:
            sys.exit("wiki-lint: 当前目录及其上级都没有 wiki/")
        WIKI = ROOT / "wiki"
        pages = None
    else:
        paths = hook_target() if args[0] == "--hook" else args
        pages = [Path(a) if Path(a).is_absolute() else Path.cwd() / a for a in paths]
        # hook 会把每一次编辑都送进来,不在 wiki 里的、已删的,静默放过
        pages = [p.resolve() for p in pages if p.exists() and p.suffix == ".md"]
        ROOT = locate(pages[0].parent) if pages else None
        if ROOT is None:
            return
        WIKI = ROOT / "wiki"
        pages = [p for p in pages if WIKI in p.parents
                 and not set(p.relative_to(WIKI).parts[:-1]) & ASSET_DIRS]
        if not pages:
            return

    index = build_index()
    links = inbound_map(index)
    listed = indexed_pages(index)
    others = non_page_targets()

    if pages is None:
        total = 0
        for page in wiki_pages():
            issues = check(page, index, links, listed, others)
            if issues:
                total += 1
                print(page.relative_to(ROOT).as_posix())
                for issue in issues:
                    print("  ✗ " + issue)
        print(f"\n{len(wiki_pages())} 篇,{total} 篇有待补" if total
              else f"{len(wiki_pages())} 篇,双链完整")
        return

    failed = False
    for page in pages:
        issues = check(page, index, links, listed, others)
        if not issues:
            continue
        failed = True
        print(f"wiki-lint {page.relative_to(ROOT).as_posix()}", file=sys.stderr)
        for issue in issues:
            print("  ✗ " + issue, file=sys.stderr)
    if failed:
        sys.exit(2)


if __name__ == "__main__":
    main()
