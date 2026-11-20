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
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
ZH_OK_RE = re.compile(r"^[\u0020-\u024f\u2000-\u206f\u2190-\u22ff\u2460-\u24ff\u3000-\u303f\u4e00-\u9fff\uff00-\uffef…—·]*$")


def strip_english_definition(zh):
    """「英英释义 + 中文」只留中文：w. to fight somebody … 摔跤 -> 摔跤。开头只有一两个英文词的不动（(= colour)颜色）。"""
    m = CJK_RE.search(zh)
    if m and len(re.findall(r"[A-Za-z]+", zh[: m.start()])) >= 3:
        return zh[m.start():].strip()
    return zh


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


def repair_ocr_token(token):
    """扫描版 OCR 的错字：TOOK/COW 这类全大写的常用词改小写；查不到的词试一次编辑（替换、删除、插入一个字符），
    取最常用的候选（d0g -> dog、friena -> friend、wnat -> what）。"""
    if token.isupper() and (len(token) > 2 or token in CAPS_WORDS) and dicts.rank(token.lower()) < 5000:
        return token.lower()
    lower = token.lower()
    if token != lower and not dicts.known(token) and dicts.known(lower):
        return lower  # psyChologist
    own = dicts.rank(token)
    # 屈折形式（are/has）在 ECDICT 里没有词频（own 是 UNRANKED 以上），认得就不动
    if (dicts.known(token) and (own <= 10000 or own >= dicts.UNRANKED)) or dicts.proper_noun(token):
        return token
    # 认得但很生僻的词（ana）也可能是认错的常用词：候选要比它常用 20 倍以上才换
    best, best_rank = token, min(dicts.COMMON_RANK, own // 20) if dicts.known(token) else dicts.COMMON_RANK
    for i in range(len(lower) + 1):
        for ch in LETTERS:
            for cand in (lower[:i] + ch + lower[i + 1:], lower[:i] + ch + lower[i:]):
                r = dicts.rank(cand)
                if r < best_rank:
                    best, best_rank = cand, r
        if i < len(lower):
            cand = lower[:i] + lower[i + 1:]
            r = dicts.rank(cand)
            if r < best_rank:
                best, best_rank = cand, r
    return best


# OCR 里单独成行的词性，不是词条
OCR_POS = {"n", "v", "vt", "vi", "ad", "adj", "adv", "prep", "pron", "conj", "num", "art", "int", "interj", "abbr", "pl"}
# 两个字母的全大写词只改这些常见虚词，其余当缩写（OK、TV、PE）
CAPS_WORDS = {"IS", "IT", "IN", "ON", "AT", "TO", "NO", "MY", "ME", "HE", "WE", "DO", "GO", "SO", "UP", "AM", "AN", "BE",
              "BY", "IF", "OF", "OR"}


def trim_ocr_hw(hw):
    """扫描版常把没认出斜杠的音标粘在词头后面：beautiful rbju:tel add -> beautiful。
    整个词组词典里没有时，取最长的、本身认得的前缀；后面有像音标的（带 : ' ; ˈ /）或紧跟着不认得的词就截掉。"""
    tokens = hw.split()
    if len(tokens) < 2 or dicts.known(hw):
        return hw
    for n in range(len(tokens) - 1, 0, -1):
        prefix = " ".join(tokens[:n])
        rest = tokens[n:]
        phonetic = any(re.search(r"[:'；;ˈ/]", t) for t in rest)
        # 紧跟着一个不认得的小写词（pfulil）；省略号、大写专名（Lake Titicaca）不算
        garbage = re.fullmatch(r"[a-z]{3,}", rest[0]) and not dicts.known(rest[0])
        if dicts.known(prefix) and (phonetic or garbage):
            return prefix
    return hw


def repair_ocr(hw):
    hw = trim_ocr_hw(hw)
    return re.sub(r"[A-Za-z0-9]+", lambda m: repair_ocr_token(m.group()) if re.search(r"[A-Za-z]", m.group()) else m.group(),
                  hw)


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


def entry_id(hw, ocr=False):
    """词条原始词头 -> wordId（清洗、修复后），按单元表、总表、QA 都用它，保证两边对得上。"""
    return make_id((repair_ocr if ocr else repair)(clean_hw(hw)))


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
    have = {entry_id(e["hw"], e.get("ocr")) for _, e in entries}
    known_refs = sorted(ref_unit)
    units = [{**u, "entries": list(u["entries"])} for u in units]
    others = []
    for e in index:
        if entry_id(e["hw"], e.get("ocr")) in have:
            continue
        if not e.get("ref", "").isdigit():
            others.append({**e, "fromIndex": True, "star": True})
            have.add(entry_id(e["hw"], e.get("ocr")))
            continue
        ref = int(e["ref"])
        lower = [r for r in known_refs if r <= ref]
        ui = ref_unit[lower[-1] if lower else known_refs[0]]
        units[ui]["entries"].append({**e, "fromIndex": True})
        have.add(entry_id(e["hw"], e.get("ocr")))
    if others:
        units.append({"name": OTHERS_UNIT, "entries": others})
    return units


def units_from_index(index):
    """只有字母序总表的书：按每个词的单元号分单元（Unit 1、Unit 2……），没有单元号的放进「其他词汇」。"""
    by_ref = {}
    for e in index:
        ref = e.get("ref", "")
        key = int(ref) if ref.isdigit() else None
        by_ref.setdefault(key, []).append(e)
    units = [{"name": f"Unit {k}", "entries": by_ref[k]} for k in sorted(k for k in by_ref if k is not None)]
    if None in by_ref:
        units.append({"name": OTHERS_UNIT, "entries": [{**e, "star": True} for e in by_ref[None]]})
    return units


def normalize_book(extracted):
    """req：是否要求掌握。书后有字母序总表时以总表为准（总表不收的专名、缩写不要求），否则按 kind 判断。"""
    units, warnings = [], list(extracted.get("warnings", []))
    # 总表里带 △/* 的是不要求掌握的词（专名、超纲词），不算
    index = extracted.get("index", [])
    if not extracted.get("indexOnly") and len(index) < sum(len(u["entries"]) for u in extracted["units"]) * 0.15:
        index = []  # 太短的「总表」不是词汇表（沪教高中书后是 12 个语法术语），不用它判断是否要求掌握
    extracted = {**extracted, "index": index}
    index_ids = {entry_id(e["hw"], e.get("ocr")) for e in index if not e.get("star")}
    raw_units = extracted["units"]
    if extracted.get("indexOnly"):
        raw_units = units_from_index(extracted.get("index", []))
    for unit in fill_from_index(raw_units, extracted.get("index", [])):
        seen = set()
        words = []
        for e in unit["entries"]:
            hw, note = split_note(e["hw"])
            fixed = (repair_ocr if e.get("ocr") else repair)(hw)
            if e.get("ocr"):  # OCR 常把释义里的分号认成冒号
                e = {**e, "senses": [{**s, "zh": s["zh"].replace("：", "；")} for s in e["senses"]]}
            bad_zh = garbled(e["senses"])  # 先判断乱码，再筛：乱码释义里也没有汉字
            # 课本释义应当有中文；只有英文的是英英释义（沪教高中），丢掉，用词典释义
            e = {**e, "senses": [{**s, "zh": strip_english_definition(s["zh"])} for s in e["senses"]
                                 if CJK_RE.search(s["zh"]) or not s["zh"]]}
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
            if e.get("ocr") and (fixed.lower().rstrip(".&") in OCR_POS or
                                 (word["kind"] == "word" and not word["senses"] and not dicts.known(fixed))):
                warnings.append(f"{unit['name']}: OCR 杂条，丢弃 {fixed!r}")  # 单独一行的词性 ad/vi、认不出的音标
                continue
            if e.get("ocr") and not word["senses"] and word["kind"] == "phrase":
                warnings.append(f"{unit['name']}: OCR 无释义的词组，丢弃 {fixed!r}")  # 多半是认错的标题（Wora List）
                continue
            if word["kind"] == "phrase" and len(fixed.split()) >= 3 and not word["ipa"] and not bad_zh \
                    and not any(s["zh"] for s in word["senses"]) and not dicts.known(fixed):
                warnings.append(f"{unit['name']}: 没有释义的长词组，像是英文释义的折行，丢弃 {fixed!r}")
                continue
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
