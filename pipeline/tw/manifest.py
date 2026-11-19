"""01 教材清单：从 ChinaTextbook 文件树解析出白名单内的英语教材，每本书一条记录。"""
import json
import re
from collections import defaultdict

import requests

from .paths import CACHE, OUT, TREE_URL, load_editions

STAGES = {"小学": "ps", "初中": "jh", "高中": "sh"}
CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
TERMS = {"上册": "a", "下册": "b", "全一册": ""}

GRADE_RE = re.compile(r"([一二三四五六七八九])年级(上册|下册|全一册)")
SENIOR_RE = re.compile(r"(选择性必修|必修)\s*第([一二三四])册")
PART_RE = re.compile(r"\.pdf\.(\d+)$")


def parse_volume(filename):
    """从文件名解析册次，返回 (grade, term, vol_code, title) 或 None。

    初中/小学: 七年级上册 -> (7, 'a', '7a')；九年级全一册 -> (9, '', '9')
    高中: 必修 第一册 -> (10, 'b1', 'b1')；选择性必修 第二册 -> (11, 'x2', 'x2')
    高中的 grade 只是排序用的近似年级：必修归高一，选择性必修归高二。
    """
    m = SENIOR_RE.search(filename)
    if m:
        kind, n = m.groups()
        n = CN_NUM[n]
        if kind == "必修":
            return 10, f"b{n}", f"b{n}", f"必修 第{m.group(2)}册"
        return 11, f"x{n}", f"x{n}", f"选择性必修 第{m.group(2)}册"
    m = GRADE_RE.search(filename)
    if m:
        g, term = m.groups()
        grade = CN_NUM[g]
        code = TERMS[term]
        return grade, code, f"{grade}{code}", f"{g}年级{term}"
    return None


def parse_path(path):
    """把仓库里的一个文件路径拆成 (stage, edition_dir, book_file, part)。

    book_file 是还原后的 PDF 文件名；part 为分卷序号，未分卷为 0。
    两种分卷写法：
      X.pdf_merge_folder/X.pdf.1   和   X.pdf.1（与其它文件同目录）
    """
    segs = path.split("/")
    if len(segs) < 4 or segs[1] != "英语" or segs[0] not in STAGES:
        return None
    name = segs[-1]
    part = 0
    m = PART_RE.search(name)
    if m:
        part = int(m.group(1))
        name = name[: m.start()] + ".pdf"
    elif not name.endswith(".pdf"):
        return None
    return STAGES[segs[0]], segs[2], name, part


def build_manifest(tree, editions):
    by_dir = {(e["stage"], e["dir"]): e for e in editions}
    books = {}
    parts = defaultdict(list)
    for entry in tree:
        if entry["type"] != "blob":
            continue
        parsed = parse_path(entry["path"])
        if not parsed:
            continue
        stage, ed_dir, filename, part = parsed
        ed = by_dir.get((stage, ed_dir))
        if not ed:
            continue
        vol = parse_volume(filename)
        if not vol:
            raise ValueError(f"无法解析册次: {entry['path']}")
        grade, term, vol_code, vol_title = vol
        book_id = f"{stage}-{ed['code']}-{vol_code}"
        books.setdefault(book_id, {
            "id": book_id,
            "stage": stage,
            "edition": ed["code"],
            "editionName": ed["name"],
            "publisher": ed["publisher"],
            "grade": grade,
            "term": term,
            "volume": vol_title,
            "file": filename,
        })
        parts[book_id].append((part, entry["path"], entry["size"]))
    for book_id, ps in parts.items():
        ps.sort()
        nums = [p for p, _, _ in ps]
        if nums != [0] and nums != list(range(1, len(nums) + 1)):
            raise ValueError(f"{book_id} 分卷不连续: {nums}")
        books[book_id]["parts"] = [{"path": p, "size": s} for _, p, s in ps]
        books[book_id]["size"] = sum(s for _, _, s in ps)
    order = {"ps": 0, "jh": 1, "sh": 2}
    return sorted(books.values(), key=lambda b: (order[b["stage"]], b["edition"], b["grade"], b["term"]))


def fetch_tree(refresh=False):
    cached = CACHE / "tree.json"
    if refresh or not cached.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        resp = requests.get(TREE_URL, timeout=60)
        resp.raise_for_status()
        cached.write_bytes(resp.content)
    data = json.loads(cached.read_text(encoding="utf-8"))
    if data.get("truncated"):
        raise RuntimeError("GitHub 文件树被截断，需要改成按目录分别拉取")
    return data["tree"]


def main(refresh=False):
    books = build_manifest(fetch_tree(refresh), load_editions())
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "manifest.json").write_text(json.dumps(books, ensure_ascii=False, indent=1), encoding="utf-8")
    total = sum(b["size"] for b in books) / 1e9
    print(f"manifest: {len(books)} 本书, {total:.1f} GB -> {OUT / 'manifest.json'}")
    return books
