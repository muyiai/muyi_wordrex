from pathlib import Path

import yaml

PIPELINE = Path(__file__).resolve().parent.parent
CONFIG = PIPELINE / "config"
OUT = PIPELINE / "out"
CACHE = OUT / "cache"
PDF_DIR = OUT / "pdf"
EXTRACT_DIR = OUT / "extract"
BUILD_DIR = OUT / "build"

REPO = "TapXWorld/ChinaTextbook"
BRANCH = "master"
TREE_URL = f"https://api.github.com/repos/{REPO}/git/trees/{BRANCH}?recursive=1"
RAW_BASE = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/"


def load_editions():
    with open(CONFIG / "editions.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)["editions"]
