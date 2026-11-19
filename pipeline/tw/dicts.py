"""词典数据：词光（word-atlas，CC BY 4.0）和 ECDICT（MIT）。

ECDICT 有 77 万行，全量载入成 dict 太占内存：normalize 只要词表（set），
enrich 再按需要的词流式读一遍取整行。
"""
import csv
import json
from functools import lru_cache

from .paths import PIPELINE

VENDOR = PIPELINE / "vendor"
ECDICT_CSV = VENDOR / "ecdict" / "ecdict.csv"
LEMMA_TXT = VENDOR / "ecdict" / "lemma.en.txt"
ATLAS_JSON = VENDOR / "word-atlas" / "word-atlas.json"
ATLAS_INDEX_JSON = VENDOR / "word-atlas" / "atlas-index.json"

csv.field_size_limit(1 << 24)


UNRANKED = 10 ** 7
COMMON_RANK = 30000


@lru_cache(maxsize=None)
def ecdict_words():
    """小写词 -> 词频排名（BNC / 当代语料取较小的，越小越常用；都没有为 UNRANKED）。"""
    ranks = {}
    with open(ECDICT_CSV, encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        next(reader)
        for row in reader:
            if not row:
                continue
            rank = min((int(x) for x in (row[8], row[9]) if x and x != "0"), default=UNRANKED)
            key = row[0].lower()
            ranks[key] = min(rank, ranks.get(key, UNRANKED))
    return ranks


def rank(word):
    word = word.lower()
    if word in atlas_entries():
        return min(ecdict_words().get(word, UNRANKED), UNRANKED - 1)
    return ecdict_words().get(word, UNRANKED + 1)


def ecdict_rows(words):
    """只取 words（小写）里出现的行；同一个词有大小写多条时，优先完全小写的那条。"""
    words = set(words)
    found = {}
    with open(ECDICT_CSV, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            key = row["word"].lower()
            if key in words and (key not in found or row["word"] == key):
                found[key] = row
    return found


@lru_cache(maxsize=None)
def atlas_entries():
    with open(ATLAS_JSON, encoding="utf-8") as f:
        return {e["w"].lower(): e for e in json.load(f)}


@lru_cache(maxsize=None)
def atlas_media():
    """词光 id -> 媒体位标记：1 插画、2 英音、4 美音、8 例句朗读（以 public/atlas/index.json 为准）。"""
    with open(ATLAS_INDEX_JSON, encoding="utf-8") as f:
        return {row[0]: row[6] for row in json.load(f)["words"]}


@lru_cache(maxsize=None)
def lemmas():
    """变形 -> 原形，例如 has -> have。"""
    table = {}
    with open(LEMMA_TXT, encoding="utf-8") as f:
        for line in f:
            if line.startswith(";") or "->" not in line:
                continue
            base, forms = line.split("->")
            base = base.split("/")[0].strip().lower()
            for form in forms.split(","):
                form = form.strip().lower()
                if form and form not in table:
                    table[form] = base
    return table


# 词组里的占位词
PLACEHOLDERS = {"sth", "sb", "sp", "one's", "oneself", "sb's", "sth's", "somebody", "something", "doing", "do"}


def variants(word):
    """查词典时的候选写法：Mr. -> mr / mr.，e-mail -> email / e mail，P.E. -> pe。"""
    w = word.lower()
    out = [w, w.rstrip("."), w.replace(".", ""), w.replace("-", ""), w.replace("-", " "), w.replace(" ", "-"),
           w.replace(" ", "")]
    return list(dict.fromkeys(v for v in out if v))


def known(word):
    """词光收录、ECDICT 里有词频、或是某个词的屈折形式（are/has/based）。

    ECDICT 有大量无词频的杂条（如 afer），只出现在杂条里的不算；屈折形式在 ECDICT 里没有词频，要靠词形表。
    """
    for v in variants(word):
        if rank(v) < UNRANKED or v in PLACEHOLDERS:
            return True
        if v in lemmas() and rank(lemmas()[v]) < COMMON_RANK:  # 词形表也有杂条：afer -> af
            return True
    return False


def proper_noun(word):
    """首字母大写且 ECDICT 收了这个词（专名一般没有词频）：the Andes、Cusco。"""
    return word[:1].isupper() and word.lower() in ecdict_words()
