"""05 补全：给所有书里出现的每个 wordId 生成一条词典词条。

查词顺序：词光直接命中 > ECDICT 直接命中 > 词光（原形）> ECDICT（原形）。
词光有例句、搭配、插画和录音（CC BY 4.0）；ECDICT（MIT）只补音标和中文释义。
课本自己的释义按书存在 books/<id>.json 里，不进这里——同一个词在不同教材里的释义可以不同。
"""
import json
import re

from . import dicts, forge
from .normalize import NORMALIZED_DIR
from .paths import OUT

ENRICHED = OUT / "enriched.json"

ECDICT_IPA = str.maketrans({"'": "ˈ", ",": "ˌ", "ә": "ə", ":": "ː", "^": "ɡ"})
ECDICT_POS_RE = re.compile(r"^([a-z]+\.(?:\s*&\s*[a-z]+\.)?)\s*(.*)$")
ECDICT_TAGS = ("zk", "gk", "cet4", "cet6", "ky", "toefl", "ielts", "gre")


def ecdict_ipa(phonetic):
    return f"/{phonetic.translate(ECDICT_IPA)}/" if phonetic else ""


def ecdict_senses(translation, limit=4):
    """ECDICT 的 translation 是多行「n. 午后, 下午」，[网络] 等来源不明的行丢掉。"""
    senses = []
    for line in translation.split("\\n"):
        line = line.strip()
        if not line or line.startswith("["):
            continue
        m = ECDICT_POS_RE.match(line)
        pos, zh = (m.group(1), m.group(2)) if m else ("", line)
        zh = re.sub(r"\s*,\s*", "；", zh).strip()
        if zh:
            senses.append({"pos": pos, "zh": zh})
    return senses[:limit]


def lookup_keys(hw):
    """课本短语的写法词典里查不到，再试几种简化：
    sign up (for sth) -> sign up；ask ... for -> ask sb for / ask for；even if/though -> even if
    """
    forms = [hw]
    base = re.sub(r"\s*\([^)]*\)", "", hw).strip()
    base = re.sub(r"(\w+)/\w+", r"\1", base)
    forms.append(base)
    if "..." in base:
        forms += [base.replace("...", x) for x in ("sth", "sb", "")]
    keys = []
    for f in forms:
        keys += dicts.variants(re.sub(r"\s+", " ", f).strip())
    return list(dict.fromkeys(keys))


def lookup(hw, atlas, ecdict):
    """返回 (atlas_entry, ecdict_row, lemma)。lemma 非空表示是按原形查到的。"""
    keys = lookup_keys(hw)
    a = next((atlas[k] for k in keys if k in atlas), None)
    e = next((dicts.pick_case(ecdict[k], hw) for k in keys if k in ecdict), None)
    if a or e:
        return a, e, ""
    base = next((dicts.lemmas()[k] for k in keys if k in dicts.lemmas()), "")
    if base:
        return atlas.get(base), dicts.pick_case(ecdict[base], base) if base in ecdict else None, base
    return None, None, ""


# 英美拼写：color/colour、center/centre、realize/realise……
SPELLING = [("our", "or"), ("or", "our"), ("ise", "ize"), ("ize", "ise"), ("yse", "yze"), ("yze", "yse"),
            ("tre", "ter"), ("ter", "tre"), ("ence", "ense"), ("ense", "ence"), ("ogue", "og"), ("og", "ogue")]
# ECDICT exchange 里的变化类型：可以直接用原形内容的（过去式、过去分词、第三人称、复数、比较级、最高级）
FORM_TYPES = {"p", "d", "pd", "dp", "3", "s", "s3", "r", "t"}


def atlas_spelling(hw, atlas):
    """英美拼写不同的同一个词，词光内容完全通用。"""
    w = hw.lower()
    for a, b in SPELLING:
        if w.endswith(a) and len(w) > len(a) + 2 and w[: -len(a)] + b in atlas:
            return atlas[w[: -len(a)] + b]
    return None


def atlas_base_form(row, atlas):
    """ECDICT 标明这个词是某个原形的变化形式（exchange 里的 0:原形、1:类型），且原形在词光里时，返回原形。

    -ing 形式常有自己的意思（boxing 拳击、saying 谚语），只有 ECDICT 释义本身就指向原形时才关联。
    """
    fields = dict(f.split(":", 1) for f in (row.get("exchange") or "").split("/") if ":" in f)
    base, kind = fields.get("0", ""), fields.get("1", "")
    if not base or base not in atlas or base == row["word"].lower():
        return None
    if kind in FORM_TYPES or (kind == "i" and base in row["translation"]):
        return base
    return None


def build_entry(wid, occ, atlas, ecdict, forged=None):
    """occ：这个词在各书里的第一次出现（normalize 后的 word），用来取展示词头、课本音标和兜底释义。

    音标优先级：词光（带重音）> 课本 > ECDICT（老式记法，如 /faiv/）。
    人名不查词典：ECDICT 的人名释义常有错（Gina -> 吉娜（男子名））。
    """
    a, e, lemma = lookup(occ["hw"], atlas, ecdict) if occ["kind"] != "name" else (None, None, "")
    if not a and occ["kind"] == "word":
        a = atlas_spelling(occ["hw"], atlas)
    base = atlas_base_form(e, atlas) if e and not a and occ["kind"] == "word" else None
    entry = {"id": wid, "w": occ["hw"], "kind": occ["kind"]}
    g = (forged or {}).get(wid)
    if g and not a and not base:
        # 词光没有、按词光的做法生成的词条（tw/forge.py）
        entry.update({
            "uk": g.get("uk", ""), "us": g.get("us", ""), "senses": g["senses"], "ex": g["ex"], "col": g.get("col", []),
            "fam": g.get("fam", []), "syn": g.get("syn", []), "ant": g.get("ant", []), "tip": g.get("tip", ""),
            "cefr": g.get("cefr", ""), "topic": g.get("topic", ""), "aid": g["aid"], "m": g["m"], "src": "gen",
        })
    elif base:
        # 变化形式（wore -> wear）：例句、搭配、插画用原形的；释义先放这个词形自己的（wear 的过去式）；
        # 音标和发音不能用原形的
        b = atlas[base]
        entry.update({
            "uk": occ.get("ipa") or ecdict_ipa(e["phonetic"]), "senses": ecdict_senses(e["translation"])[:1] + b["senses"],
            "ex": b["ex"], "col": b["col"], "fam": b["fam"], "syn": b["syn"], "ant": b["ant"], "tip": b["tip"],
            "cefr": b["cefr"], "topic": b["topic"], "aid": b["id"], "m": dicts.atlas_media().get(b["id"], 0) & (1 | 8),
            "src": "atlas",
        })
        lemma = base
    elif a:
        entry.update({
            "uk": a["uk"], "us": a["us"], "senses": a["senses"], "ex": a["ex"], "col": a["col"],
            "fam": a["fam"], "syn": a["syn"], "ant": a["ant"], "tip": a["tip"], "cefr": a["cefr"],
            "topic": a["topic"], "aid": a["id"], "m": dicts.atlas_media().get(a["id"], 0), "src": "atlas",
        })
    elif e:
        entry.update({"uk": occ.get("ipa") or ecdict_ipa(e["phonetic"]), "senses": ecdict_senses(e["translation"]),
                      "src": "ecdict"})
        if occ["senses"] and (occ["hw"][:1].isupper() or occ["kind"] in ("abbr", "proper", "name")):
            # 大写词、缩写在 ECDICT 里常查到同形的别的词（Mum -> 菊花），课本有释义就用课本的
            entry.update({"senses": occ["senses"], "src": "textbook"})
    else:
        entry.update({"senses": occ["senses"], "src": "textbook"})
    if not entry.get("uk") and occ.get("ipa"):
        entry["uk"] = occ["ipa"]
    if not entry["senses"]:
        entry["senses"] = occ["senses"]
    if e and e.get("tag"):
        tags = [t for t in e["tag"].split() if t in ECDICT_TAGS]
        if tags:
            entry["tags"] = tags
    if lemma:
        entry["lemma"] = lemma
    return entry


def collect_words():
    """所有书里出现过的 wordId -> 第一次出现时的 normalize 结果。"""
    words = {}
    for f in sorted(NORMALIZED_DIR.glob("*.json")):
        book = json.loads(f.read_text(encoding="utf-8"))
        for unit in book["units"]:
            for w in unit["words"]:
                first = words.setdefault(w["id"], dict(w))
                if not first.get("ipa") and w.get("ipa"):
                    first["ipa"] = w["ipa"]  # 第一次出现没有音标（如短语表、扫描版），用后面书里的
                if not first["senses"] and w["senses"]:
                    first["senses"] = w["senses"]  # 释义同理
    return words


def main():
    words = collect_words()
    atlas = dicts.atlas_entries()
    wanted = {k for w in words.values() for k in lookup_keys(w["hw"])}
    wanted |= {dicts.lemmas()[v] for v in wanted if v in dicts.lemmas()}
    ecdict = dicts.ecdict_rows(wanted)
    forged = forge.load_by_id()
    entries = {wid: build_entry(wid, occ, atlas, ecdict, forged) for wid, occ in words.items()}
    ENRICHED.write_text(json.dumps(entries, ensure_ascii=False, indent=1), encoding="utf-8")
    by_src = {}
    for e in entries.values():
        by_src[e["src"]] = by_src.get(e["src"], 0) + 1
    print(f"enrich: {len(entries)} 词 {by_src} -> {ENRICHED}")
    return entries
