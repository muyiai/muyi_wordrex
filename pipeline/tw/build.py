"""06 打包：生成小程序加载的数据。

  catalog.json        学段 -> 版本 -> 册 的目录树
  books/<bookId>.json      一册书：单元 -> 词（课本释义、是否要求掌握、是否本系列首次出现）
  books/<bookId>.dict.json 这册书用到的词典词条。小程序学一本书只下这一个文件
  dict/<n>.json            全部词条分块，n = fnv1a(wordId) % chunks（查单个词用；一本书的词散在所有块里，
                           所以学一本书不走这里）
"""
import json
import math
import shutil
import time

from .enrich import ENRICHED
from .normalize import NORMALIZED_DIR
from .paths import BUILD_DIR, OUT
from .qa import QA_DIR

STAGE_NAMES = {"ps": "小学", "jh": "初中", "sh": "高中"}
CHUNK_SIZE = 200
GRADE_NAMES = {3: "三年级", 4: "四年级", 5: "五年级", 6: "六年级", 7: "七年级", 8: "八年级", 9: "九年级"}


def fnv1a(text):
    """32 位 FNV-1a（UTF-8 字节）。miniprogram/lib/hash.ts 里有同样的实现，两边必须一致。"""
    h = 0x811C9DC5
    for byte in text.encode("utf-8"):
        h ^= byte
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h


def chunk_of(word_id, chunks):
    return fnv1a(word_id) % chunks


def book_word(w, is_new):
    out = {"id": w["id"], "hw": w["hw"], "senses": w["senses"], "req": w["req"]}
    if w["core"]:
        out["core"] = True
    if is_new:
        out["new"] = True
    if w.get("ipa"):
        out["ipa"] = w["ipa"]
    if w["kind"] != "word":
        out["kind"] = w["kind"]
    return out


def build_books(manifest, normalized):
    """按系列（学段+版本）、年级册次顺序走一遍，记下每个词在本系列里第一次出现的位置。"""
    books, seen = [], {}
    for meta in manifest:
        book = normalized.get(meta["id"])
        if not book:
            continue
        series = seen.setdefault((meta["stage"], meta["edition"]), set())
        units = []
        for unit in book["units"]:
            words = []
            for w in unit["words"]:
                words.append(book_word(w, w["id"] not in series))
                series.add(w["id"])
            units.append({"name": unit["name"], "words": words})
        books.append({
            "id": meta["id"], "stage": meta["stage"], "edition": meta["edition"],
            "editionName": meta["editionName"], "publisher": meta["publisher"],
            "grade": meta["grade"], "term": meta["term"], "volume": meta["volume"], "units": units,
        })
    return books


def build_catalog(books, qa, chunks, version):
    stages = {}
    for b in books:
        stage = stages.setdefault(b["stage"], {"code": b["stage"], "name": STAGE_NAMES[b["stage"]], "editions": {}})
        edition = stage["editions"].setdefault(b["edition"], {
            "code": b["edition"], "name": b["editionName"], "publisher": b["publisher"], "books": []})
        words = [w for u in b["units"] for w in u["words"]]
        edition["books"].append({
            "id": b["id"], "title": b["volume"], "grade": b["grade"], "units": len(b["units"]),
            "words": len(words), "req": sum(1 for w in words if w["req"]),
            "qa": qa.get(b["id"], {}).get("pass", False),
        })
    for stage in stages.values():
        stage["editions"] = list(stage["editions"].values())
    return {"version": version, "dictChunks": chunks, "stages": list(stages.values())}


def main():
    manifest = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    normalized = {f.stem: json.loads(f.read_text(encoding="utf-8")) for f in NORMALIZED_DIR.glob("*.json")}
    entries = json.loads(ENRICHED.read_text(encoding="utf-8"))
    qa_file = QA_DIR / "report.json"
    qa = {r["id"]: r for r in json.loads(qa_file.read_text(encoding="utf-8"))} if qa_file.exists() else {}

    books = build_books(manifest, normalized)
    chunks = max(1, math.ceil(len(entries) / CHUNK_SIZE))
    version = time.strftime("%Y%m%d%H%M")

    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    (BUILD_DIR / "books").mkdir(parents=True)
    (BUILD_DIR / "dict").mkdir()

    def write(path, data):
        (BUILD_DIR / path).write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    for b in books:
        write(f"books/{b['id']}.json", b)
        ids = {w["id"] for u in b["units"] for w in u["words"]}
        write(f"books/{b['id']}.dict.json", {wid: entries[wid] for wid in sorted(ids) if wid in entries})
    buckets = [{} for _ in range(chunks)]
    for wid, entry in entries.items():
        buckets[chunk_of(wid, chunks)][wid] = entry
    for n, bucket in enumerate(buckets):
        write(f"dict/{n}.json", bucket)
    write("catalog.json", build_catalog(books, qa, chunks, version))

    size = sum(f.stat().st_size for f in BUILD_DIR.rglob("*.json")) / 1e6
    print(f"build: {len(books)} 本书 {len(entries)} 词 {chunks} 块 {size:.1f} MB -> {BUILD_DIR}")
