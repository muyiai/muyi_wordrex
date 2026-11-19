"""下载第三方词典数据到 vendor/。词光固定到一个提交，保证重跑结果一致。"""
import requests

from .dicts import VENDOR

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


def main(refresh=False):
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
