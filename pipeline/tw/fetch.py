"""02 下载：按清单拉取 PDF，分卷按序拼接，校验 %PDF 文件头。已下载的跳过。"""
import json
from urllib.parse import quote

import requests

from .paths import OUT, PDF_DIR, RAW_BASE


def raw_url(path):
    return RAW_BASE + quote(path)


def fetch_book(book, session=None):
    session = session or requests.Session()
    dest = PDF_DIR / f"{book['id']}.pdf"
    if dest.exists() and dest.stat().st_size == book["size"]:
        return dest
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    with open(tmp, "wb") as out:
        for part in book["parts"]:
            with session.get(raw_url(part["path"]), stream=True, timeout=120) as resp:
                resp.raise_for_status()
                for chunk in resp.iter_content(1 << 20):
                    out.write(chunk)
    with open(tmp, "rb") as f:
        if f.read(5) != b"%PDF-":
            raise ValueError(f"{book['id']} 不是 PDF（分卷顺序或下载有误）")
    if tmp.stat().st_size != book["size"]:
        raise ValueError(f"{book['id']} 大小不符: {tmp.stat().st_size} != {book['size']}")
    tmp.rename(dest)
    return dest


def main(ids=None):
    books = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    if ids:
        books = [b for b in books if b["id"] in ids]
    session = requests.Session()
    for b in books:
        path = fetch_book(b, session)
        print(f"fetch: {b['id']} {b['size'] / 1e6:.0f} MB -> {path.name}")
