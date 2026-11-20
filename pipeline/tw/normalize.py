"""04 清洗：词头修复（连字丢字）、分类（单词/短语/缩写/人名）、生成全局 wordId。"""
import json
import re

from . import dicts
from .paths import EXTRACT_DIR, OUT

NORMALIZED_DIR = OUT / "normalized"

NAME_RE = re.compile(r"[（(](男名|女名|姓|人名|名)[）)]")
ABBR_RE = re.compile(r"^([A-Z]{1,5}|([A-Za-z]\.){2,})$")
LETTERS = "abcdefghijklmnopqrstuvwxyz"
# 释义里允许出现的字符：汉字、中日韩标点、全角、拉丁字母和常见符号。字体映射坏掉时会冒出格鲁吉亚文、
# 老挝文、泰卢固文等（沪教：Alex ჱ历克ຯ（ఴ名）），这样的课本释义丢掉，改用词典释义。
ZH_OK_RE = re.compile(r"^[\u0020-\u024f\u2000-\u206f\u2190-\u22ff\u2460-\u24ff\u3000-\u303f\u4e00-\u9fff\uff00-\uffef…—·]*$")


def garbled(senses):
    return any(not ZH_OK_RE.match(s["zh"]) for s in senses)


def split_note(hw):
    """词头里的说明拆出来：hello (hi) -> hello / hi，am (I'm = I am) -> am / I'm = I am，
    I'm = I am -> I'm / = I am，sign up (for sth) -> sign up / for sth。"""
    hw = re.sub(r"\s+", " ", hw).strip().replace("’", "'").replace("‘", "'")
    hw = hw.lstrip("*△▲▫•· ").rstrip(",;:“”\"").strip()
    if "(" in hw and ")" not in hw:  # 说明折到了下一行：show (、Thanksgiving (Thanksgiving
        hw, rest = hw.split("(", 1)
        return hw.strip(), rest.strip()
    m = re.match(r"^(.+?)\s*\(([^()]*)\)$", hw)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    m = re.match(r"^(.+?)\s*(=\s*.+)$", hw)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return hw, ""


def clean_hw(hw):
    return split_note(hw)[0]


def repair_token(token):
    """连字（ft/fi/Th…）的字形有时没有文字映射，提取出来少一个字母：afer -> after，Tursday -> Thursday。

    词典里查不到时，枚举「任意位置补一个字母」，取最常用的候选；候选必须足够常用（COMMON_RANK），
    免得把课本里的生僻词（人名、音译词）改成别的常用词。改过的词都在 raw 里留底，QA 报告逐条列出。
    """
    if dicts.known(token) or dicts.proper_noun(token):
        return token
    best, best_rank = token, dicts.COMMON_RANK
    for i in range(len(token) + 1):
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


OTHERS_UNIT = "其他词汇"


def fill_from_index(units, index):
    """有的书按单元表只列一部分词（冀教只列四会词），字母序总表才全，而且每个词带课次号。
    按单元表里的词也带课次号时，用它们建「课次 -> 单元」的对应，把总表独有的词补进对应单元。
    没出现在按单元表里的课次号，归到比它小的最近一个课次所在的单元。
    总表里没有课次号的词（冀教的故事词，字体也不一样）放进最后的「其他词汇」，不要求掌握。
    """
    ref_unit = {}
    entries = [(ui, e) for ui, u in enumerate(units) for e in u["entries"]]
    for ui, e in entries:
        if e.get("ref", "").isdigit():
            ref_unit.setdefault(int(e["ref"]), ui)
    if not entries or len(ref_unit) < 3 or sum(1 for _, e in entries if e.get("ref")) < len(entries) / 2:
        return units
    have = {make_id(repair(clean_hw(e["hw"]))) for _, e in entries}
    known_refs = sorted(ref_unit)
    units = [{**u, "entries": list(u["entries"])} for u in units]
    others = []
    for e in index:
        if make_id(repair(clean_hw(e["hw"]))) in have:
            continue
        if not e.get("ref", "").isdigit():
            others.append({**e, "fromIndex": True, "star": True})
            have.add(make_id(repair(clean_hw(e["hw"]))))
            continue
        ref = int(e["ref"])
        lower = [r for r in known_refs if r <= ref]
        ui = ref_unit[lower[-1] if lower else known_refs[0]]
        units[ui]["entries"].append({**e, "fromIndex": True})
        have.add(make_id(repair(clean_hw(e["hw"]))))
    if others:
        units.append({"name": OTHERS_UNIT, "entries": others})
    return units


def normalize_book(extracted):
    """req：是否要求掌握。书后有字母序总表时以总表为准（总表不收的专名、缩写不要求），否则按 kind 判断。"""
    units, warnings = [], list(extracted.get("warnings", []))
    # 总表里带 △/* 的是不要求掌握的词（专名、超纲词），不算
    index_ids = {make_id(repair(clean_hw(e["hw"]))) for e in extracted.get("index", []) if not e.get("star")}
    for unit in fill_from_index(extracted["units"], extracted.get("index", [])):
        seen = set()
        words = []
        for e in unit["entries"]:
            hw, note = split_note(e["hw"])
            fixed = repair(hw)
            bad_zh = garbled(e["senses"])
            word = {
                "id": make_id(fixed),
                "hw": fixed,
                "ipa": e["ipa"],
                "senses": [] if bad_zh else e["senses"],
                "kind": classify(fixed, e["senses"]),
                "core": e["core"],
            }
            word["req"] = word["id"] in index_ids if index_ids else word["kind"] in REQUIRED_KINDS
            if e.get("star"):
                word["req"] = False  # * 标的是选学词
            if fixed != hw:
                word["raw"] = hw
            if e.get("variant"):
                word["variant"] = e["variant"]
            if note:
                word["note"] = note
            if e.get("ref"):
                word["ref"] = e["ref"]
            if e.get("fromIndex"):
                word["fromIndex"] = True
            if bad_zh:
                word["zhBad"] = True
            if e.get("elective"):
                word["elective"] = True  # 外研高中 ▫：选择性必修词
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
