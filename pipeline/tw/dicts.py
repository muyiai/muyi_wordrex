"""词典数据：词光（word-atlas，CC BY 4.0）和 ECDICT（MIT）。

ECDICT 有 77 万行，全量载入成 dict 太占内存：normalize 只要词表（set），
enrich 再按需要的词流式读一遍取整行。
"""
import csv
import json
import re
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
    """只取 words（小写）里出现的行：小写词 -> 这个词所有大小写写法的行（Ms / MS、Mum / mum 是不同的词条）。"""
    words = set(words)
    found = {}
    with open(ECDICT_CSV, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            key = row["word"].lower()
            if key in words:
                found.setdefault(key, []).append(row)
    return found


def pick_case(rows, hw):
    """同一个小写词的几条里挑一条：先要和课本写法大小写完全一致的（Ms. -> Ms，不要 MS 微软），再要全小写的。"""
    forms = {hw, hw.rstrip("."), hw.replace(".", "")}
    return (next((r for r in rows if r["word"] in forms), None)
            or next((r for r in rows if r["word"] == r["word"].lower()), None) or rows[0])


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
    if re.fullmatch(r"[A-Za-z]+'(s|re|m|ve|ll|d|t)", word):  # 缩约形式：she's、can't、you're
        word = re.sub(r"(n't|'\w+)$", "", word) or word
    for v in variants(word):
        if rank(v) < UNRANKED or v in PLACEHOLDERS:
            return True
        if v in lemmas() and rank(lemmas()[v]) < COMMON_RANK:  # 词形表也有杂条：afer -> af
            return True
    return False


def legit(word):
    """像个正常的词：认识的、每一段都认识的连字符词（sit-up、real-life），或者 ECDICT 收了但没有词频的
    罕见词（earmuff、paragliding）。生成词条时用它排除 OCR 杂条。"""
    if known(word) or word.lower() in ecdict_words():
        return True
    parts = [p for p in word.split("-") if p]
    return len(parts) > 1 and all(known(p) for p in parts)


# 切分粘连短语时允许的短词：两个字母的只认这些；三个字母的还要很常用（免得 triathlete 被切成 tri athlete）
SHORT_WORDS = {"a", "i", "an", "as", "at", "be", "by", "do", "go", "he", "if", "in", "is", "it", "me", "my", "no",
               "of", "on", "or", "so", "to", "up", "us", "we", "sb", "sth", "the", "and", "for", "not", "one", "out",
               "off", "but", "you", "all", "can", "how", "our", "who", "get", "put", "use", "way", "own", "too",
               "are", "was", "has", "had", "did", "got", "ran", "won", "met", "saw", "his", "her", "him", "its"}


def segment(token):
    """空格丢了的短语切回去：boildownto -> boil down to，callonsbtodosth -> call on sb to do sth。
    只切 ECDICT 根本没收的串（cannot、schoolbag 是真词）；词越少越好，同样多时越常用越好。"""
    t = token.lower()
    if not t.isalpha() or len(t) < 5 or t in ecdict_words():
        return None
    best = [None] * (len(t) + 1)
    best[0] = (0.0, [])
    for i in range(len(t)):
        if best[i] is None:
            continue
        for j in range(i + 1, min(len(t), i + 20) + 1):
            w = t[i:j]
            if w in ("sb", "sth"):
                cost = 0.0  # 课本词组的占位词：put sth in place 要赢过 puts thin place
            elif w in SHORT_WORDS or (len(w) == 3 and rank(w) < 3000) or (len(w) > 3 and known(w)):
                # 屈折形式没有自己的词频，按原形算：strikes and 不能输给 strike sand
                r = rank(w) if rank(w) < UNRANKED else rank(lemmas().get(w, w))
                cost = 1.0 + min(r, COMMON_RANK) / COMMON_RANK
            else:
                continue
            cand = (best[i][0] + cost, best[i][1] + [w])
            if best[j] is None or cand[0] < best[j][0]:
                best[j] = cand
    words = best[len(t)][1] if best[len(t)] else []
    return " ".join(words) if len(words) > 1 else None


def proper_noun(word):
    """首字母大写且 ECDICT 收了这个词（专名一般没有词频）：the Andes、Cusco。"""
    return word[:1].isupper() and word.lower() in ecdict_words()
