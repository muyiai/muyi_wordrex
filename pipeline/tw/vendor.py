"""下载第三方词典数据到 vendor/。词光固定到一个提交，保证重跑结果一致。

--media：再下载课本用到的词光媒体（插画、缩略图、英美音、例句朗读）到 vendor/word-atlas/media/，
需要先跑过 enrich（按 out/enriched.json 里用到的词光词条取）。约 2 万个文件、340 MB。
"""
import concurrent.futures as cf
import json

import requests

from .dicts import VENDOR
from .paths import OUT

ATLAS_COMMIT = "0f1bae41fe5428f0f44781e60282525407b5ae46"
ATLAS_RAW = f"https://raw.githubusercontent.com/designfuchen/word-atlas/{ATLAS_COMMIT}/"
ECDICT_RAW = "https://raw.githubusercontent.com/skywind3000/ECDICT/master/"

FILES = {
    "word-atlas/word-atlas.json": ATLAS_RAW + "data/word-atlas.json",
    "word-atlas/atlas-index.json": ATLAS_RAW + "public/atlas/index.json",
    "word-atlas/CONTENT_LICENSE.md": ATLAS_RAW + "CONTENT_LICENSE.md",
    "word-atlas/LICENSE": ATLAS_RAW + "LICENSE",
    "ecdict/ecdict.csv": ECDICT_RAW + "ecdict.csv",
    "ecdict/lemma.en.txt": ECDICT_RAW + "lemma.en.txt",
    "ecdict/LICENSE": ECDICT_RAW + "LICENSE",
}


def fetch_media(workers=16):
    entries = json.loads((OUT / "enriched.json").read_text(encoding="utf-8"))
    aids = sorted({e["aid"] for e in entries.values() if e["src"] == "atlas"})
    dest = VENDOR / "word-atlas" / "media"
    jobs = [f"{folder}/{aid}.{ext}" for aid in aids
            for folder, ext in (("img", "webp"), ("thumb", "webp"), ("audio/uk", "mp3"), ("audio/us", "mp3"), ("audio/ex", "mp3"))
            if not (dest / f"{folder}/{aid}.{ext}").exists()]
    session = requests.Session()

    def get(rel):
        resp = session.get(ATLAS_RAW + "public/atlas/" + rel, timeout=60)
        if resp.status_code == 404:
            return False  # 这个词没有这种媒体
        resp.raise_for_status()
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(resp.content)
        return True

    with cf.ThreadPoolExecutor(workers) as pool:
        got = sum(pool.map(get, jobs))
    print(f"vendor: 词光媒体 {got} 个文件（{len(aids)} 个词）-> {dest}")


def main(refresh=False, media=False):
    session = requests.Session()
    for rel, url in FILES.items():
        dest = VENDOR / rel
        if dest.exists() and not refresh:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        resp = session.get(url, timeout=300)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
        print(f"vendor: {rel} {len(resp.content) / 1e6:.1f} MB")
    (VENDOR / "word-atlas" / "COMMIT").write_text(ATLAS_COMMIT + "\n")
    if media:
        fetch_media()
