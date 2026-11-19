"""04 清洗：词头修复（连字丢字）、分类（单词/短语/缩写/人名）、生成全局 wordId。"""
import json
import re

from . import dicts
from .paths import EXTRACT_DIR, OUT

NORMALIZED_DIR = OUT / "normalized"

NAME_RE = re.compile(r"[（(](男名|女名|姓|人名|名)[）)]")
ABBR_RE = re.compile(r"^([A-Z]{1,5}|([A-Za-z]\.){2,})$")
LETTERS = "abcdefghijklmnopqrstuvwxyz"


def clean_hw(hw):
    hw = re.sub(r"\s+", " ", hw).strip().replace("’", "'").replace("‘", "'")
    hw = hw.lstrip("*△▲•·")
    return hw.rstrip(",;:").strip()


def repair_token(token):
    """连字（ft/fi/Th…）的字形有时没有文字映射，提取出来少一个字母：afer -> after，Tursday -> Thursday。

    词典里查不到时，枚举「任意位置补一个字母」，取最常用的候选；候选必须足够常用（COMMON_RANK），
    免得把课本里的生僻词（人名、音译词）改成别的常用词。改过的词都在 raw 里留底，QA 报告逐条列出。
    """
    if dicts.known(token) or dicts.proper_noun(token):
        return token
    best, best_rank = token, dicts.COMMON_RANK
    for i in range(1, len(token) + 1):
        for ch in LETTERS:
            candidate = token[:i] + ch + token[i:]
            r = dicts.rank(candidate)
            if r < best_rank:
                best, best_rank = candidate, r
    return best


def repair(hw):
    if dicts.known(hw):
        return hw
    return re.sub(r"[A-Za-z]+", lambda m: repair_token(m.group()), hw)


def classify(hw, senses):
    zh = " ".join(s["zh"] for s in senses)
    pos = " ".join(s["pos"] for s in senses)
    if NAME_RE.search(zh):
        return "name"
    if "abbr" in pos or ABBR_RE.match(hw) or (hw.endswith(".") and " " not in hw):
        return "abbr"  # NBA、p.m.、Ms.
    if re.search(r"[!?…]|\.\.\.", hw) or hw.endswith("."):
        return "phrase"
    tokens = re.sub(r"^the ", "", hw).split()
    if not pos and all(t[:1].isupper() for t in tokens):
        return "proper"  # 没有词性、每个词都大写的专名：Peru、the Andes、Machu Picchu（ID card 不算）
    if " " in hw:
        return "phrase"
    return "word"


# 没有字母序总表的书，按类型判断是否要求掌握
REQUIRED_KINDS = {"word", "phrase"}


def make_id(hw):
    """全局 wordId：小写、去掉句末标点、空格换成下划线。不同教材里的同一个词共用一份学习进度。

    How old ...?…… -> how_old，Mr. -> mr，p.m. -> p.m
    """
    wid = hw.lower().replace("…", "...")
    wid = re.sub(r"[\s!?.]+$", "", wid)
    return re.sub(r"\s+", "_", wid)


def normalize_book(extracted):
    """req：是否要求掌握。书后有字母序总表时以总表为准（总表不收的专名、缩写不要求），否则按 kind 判断。"""
    units, warnings = [], list(extracted.get("warnings", []))
    index_ids = {make_id(repair(clean_hw(hw))) for hw in extracted.get("index", [])}
    for unit in extracted["units"]:
        seen = set()
        words = []
        for e in unit["entries"]:
            hw = clean_hw(e["hw"])
            fixed = repair(hw)
            word = {
                "id": make_id(fixed),
                "hw": fixed,
                "ipa": e["ipa"],
                "senses": e["senses"],
                "kind": classify(fixed, e["senses"]),
                "core": e["core"],
            }
            word["req"] = word["id"] in index_ids if index_ids else word["kind"] in REQUIRED_KINDS
            if fixed != hw:
                word["raw"] = hw
            if e.get("variant"):
                word["variant"] = e["variant"]
            if e.get("page"):
                word["page"] = e["page"]
            if word["id"] in seen:
                warnings.append(f"{unit['name']}: 单元内重复 {word['id']}")
                continue
            seen.add(word["id"])
            if word["kind"] == "word" and not dicts.known(fixed) and not dicts.proper_noun(fixed):
                warnings.append(f"{unit['name']}: 词典未收录 {fixed!r}")
            words.append(word)
        units.append({"name": unit["name"], "words": words})
    return {"id": extracted["id"], "units": units, "warnings": warnings}


def main(ids=None):
    files = sorted(EXTRACT_DIR.glob("*.json"))
    if ids:
        files = [f for f in files if f.stem in ids]
    NORMALIZED_DIR.mkdir(parents=True, exist_ok=True)
    for f in files:
        result = normalize_book(json.loads(f.read_text(encoding="utf-8")))
        (NORMALIZED_DIR / f.name).write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
        repaired = sum(1 for u in result["units"] for w in u["words"] if "raw" in w)
        n = sum(len(u["words"]) for u in result["units"])
        print(f"normalize: {result['id']} {n} 词 修复 {repaired} 警告 {len(result['warnings'])}")
