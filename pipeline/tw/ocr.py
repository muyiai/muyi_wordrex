"""扫描版教材的 OCR：没有文字层的书，把书后几十页渲染成图片，用 macOS Vision（tools/ocr）识别，
结果缓存到 out/ocr/<bookId>.json。extract 读到缓存时，用识别出的行代替 PDF 文字层，后面的规则照常用。

Vision 把同一行的英文和中文识别成两段（family | 家庭），这里按「同一水平带、水平间距不大」合成一行；
双栏页两栏之间的间距大，不会被合到一起。
"""
import json
import re
import subprocess
import tempfile
from pathlib import Path

import fitz

from .paths import OCR_DIR, OUT, PDF_DIR, PIPELINE

TOOL = PIPELINE / "tools" / "ocr"
DPI = 300
BACK_PAGES = 40  # 书后单词表一般在最后 10~25 页
BATCH = 20
ROW_GAP = 0.12  # 同一行两段之间的最大水平间距（页宽的比例）
REF_GAP = 0.40  # 单元号可以离得更远
# 单元标题里的数字常被认成字母：Unit s -> Unit 5
HEADING_DIGIT = str.maketrans({"s": "5", "S": "5", "l": "1", "I": "1", "o": "0", "O": "0", "z": "2", "Z": "2"})
REF_RE = re.compile(r"^U\d{1,2}$")  # 沪教小学总表的单元号 U3：接在词条行末尾
HEADING_RE = re.compile(r"^(Unit|Module|Lesson) ([sSlIoOzZ\d]{1,2})$")


def pages_to_ocr(doc):
    """书后 BACK_PAGES 页里没有文字层的页。整本扫描的书就是全部；有文字层的书里偶尔也有一页是图片
    （外研初中七上的预备篇词表第 4 页）。"""
    return [i for i in range(max(0, len(doc) - BACK_PAGES), len(doc)) if len(doc[i].get_text().strip()) < 20]


def cache_path(book_id):
    return OCR_DIR / f"{book_id}.json"


def run_book(book_id):
    """识别一本书后面没有文字层的页，缓存每页的识别行（坐标换算成 PDF 的点）。已有缓存就跳过。"""
    out = cache_path(book_id)
    if out.exists():
        return json.loads(out.read_text(encoding="utf-8"))
    doc = fitz.open(PDF_DIR / f"{book_id}.pdf")
    pages = pages_to_ocr(doc)
    result = {}
    with tempfile.TemporaryDirectory() as tmp:
        images = {}
        for i in pages:
            path = Path(tmp) / f"{i}.png"
            doc[i].get_pixmap(dpi=DPI, colorspace=fitz.csGRAY).save(path)
            images[str(path)] = i
        paths = list(images)
        for k in range(0, len(paths), BATCH):
            proc = subprocess.run([str(TOOL), *paths[k:k + BATCH]], capture_output=True, text=True, check=True)
            for line in proc.stdout.splitlines():
                r = json.loads(line)
                scale = 72 / DPI
                result[images[r["image"]]] = [
                    {"text": l["text"], "conf": l["conf"],
                     "bbox": [l["x"] * scale, l["y"] * scale, (l["x"] + l["w"]) * scale, (l["y"] + l["h"]) * scale]}
                    for l in r.get("lines", [])
                ]
    OCR_DIR.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return {str(k): v for k, v in result.items()}


def load(book_id):
    """{页号: [识别行]}，没有缓存时返回空 dict。"""
    path = cache_path(book_id)
    if not path.exists():
        return {}
    return {int(k): v for k, v in json.loads(path.read_text(encoding="utf-8")).items()}


def page_lines(observations, page_width):
    """识别行 -> 与 PDF 文字层同样结构的行（span 列表）。

    先按垂直方向分成水平带（同一视觉行），带内从左到右，再在这些地方断开成几行：
    间距太大（双栏的两栏之间）；或者一段英文接在中文/页码后面（右栏的下一个词条）。
    单元号 U3 离词条远（沪教小学），而且常常比词条高一两个点，单独放宽。
    """
    bands = []
    for o in sorted(observations, key=center):
        if bands and bands[-1][0]["bbox"][1] <= center(o) <= bands[-1][0]["bbox"][3]:
            bands[-1].append(o)
        else:
            bands.append([o])
    rows = []
    for band in bands:
        row = []
        for o in sorted(band, key=lambda o: o["bbox"][0]):
            text = o["text"].strip()
            gap = o["bbox"][0] - row[-1]["bbox"][2] if row else 0
            is_ref = bool(REF_RE.match(text))
            too_far = gap > page_width * (REF_GAP if is_ref else ROW_GAP)
            new_entry = (re.match(r"[A-Za-z*]", text) and not is_ref
                         and any(re.search(r"[\u4e00-\u9fff]|[\d）)]\s*$", r["text"]) for r in row))
            if row and (too_far or new_entry):
                rows.append(row)
                row = []
            row.append(o)
        rows.append(row)
    lines = []
    for row in sorted(rows, key=lambda r: (center(r[0]), r[0]["bbox"][0])):
        spans = []
        for o in row:
            text = o["text"].strip()
            m = HEADING_RE.match(text)
            if m:
                text = f"{m.group(1)} {m.group(2).translate(HEADING_DIGIT)}"
            spans.append({"text": text + " ", "font": "OCR", "flags": 0, "size": o["bbox"][3] - o["bbox"][1],
                          "bbox": tuple(o["bbox"])})
        lines.append(spans)
    return lines


def center(o):
    return (o["bbox"][1] + o["bbox"][3]) / 2


def main(ids=None):
    books = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    if ids:
        books = [b for b in books if b["id"] in ids]
    for b in books:
        pdf = PDF_DIR / f"{b['id']}.pdf"
        if not pdf.exists() or cache_path(b["id"]).exists():
            continue
        if not pages_to_ocr(fitz.open(pdf)):
            continue
        pages = run_book(b["id"])
        print(f"ocr: {b['id']} {len(pages)} 页 {sum(len(v) for v in pages.values())} 行")
