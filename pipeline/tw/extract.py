"""03 提取：从 PDF 书后的「按单元单词表」解析出词条。

按 span（字体/字号/斜体）而不是纯文本解析，因为几个关键信号只在字体里：
  - 音标用专门的音标字体，字符是 ASCII+0xF000 的私用区编码，可解码回 IPA
  - 词性是斜体
  - 黑体词头 = 要求掌握的词（core），白体 = 只要求听说/认读
一行以「非斜体、非音标字体的拉丁字母」开头就是新词条，否则是上一条的续行。
"""
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

import fitz

from . import ocr
from .paths import EXTRACT_DIR, OUT, PDF_DIR

IPA_FONT_RE = re.compile(r"ipa|phon|kingsoft|ksphon", re.I)
BOLD_FONT_RE = re.compile(r"bold|bd\b|smbd|semibold|medium|black|heavy|-bla", re.I)
ITALIC_FONT_RE = re.compile(r"italic|-it\b|oblique", re.I)

UNIT_RE = re.compile(
    r"^(Starter Unit \d+|Welcome Unit|Unit ?\d+|Unit (One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten)"
    r"|Module ?\d+|Starter|Lesson ?\d+|Project ?\d+|Recycle ?\d+)$",
    re.I,  # 外研高中是 UNIT 1
)
# 按单元表之后的段落（字母序总表、人名表、不规则动词表）
WORDLIST_TITLE_RE = re.compile(
    r"^(Word ?list|W ?ords and expressions( in each (unit|module))?|Vocabulary|Words in each (unit|module)"
    r"|单\s*词\s*表|词\s*汇\s*表)\b", re.I)
# 字母序总表的字母标题：A 或 Aa
LETTER_HEADING = "|".join(f"{c}{c.lower()}?" for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ")
STOP_RE = re.compile(
    rf"^(Vocabulary( Index)?|WORD LIST|Word List|Appendix [2-9]|词\s*汇\s*表|Name List|Irregular Verbs|Grammar reference|Glossary"
    rf"|{LETTER_HEADING})$"
)
# 字母序总表之后的段落
INDEX_END_RE = re.compile(
    r"^(Name List|Names( and places)?|Places|Irregular Verbs|Appendix [3-9]|Proper Nouns|Glossary|Consonants.*|Vowels.*"
    r"|Junior high school language knowledge overview|Daily expressions|专有名词|后\s*记|本册教科书.*)$", re.I
)
# 编者名单：Judy West( 英) Diana Pye( 英)——除了 英/美 没有别的汉字（区别于「华盛顿（美国首都）」这类释义）
CREDITS_RE = re.compile(r"[（(]\s*[英美]\s*[)）]")


def is_credits(text):
    return bool(CREDITS_RE.search(text)) and not re.search(r"[一-鿿]", re.sub(r"[英美]", "", text))
SKIP_RE = re.compile(
    r"^(\d+|Appendix \d+|Appendices|Words and Expressions in Each (Unit|Module)|Words in Each (Unit|Module)"
    r"|单\s*元\s*词\s*汇\s*表|（注：.*）|注：.*|Phrases"
    r"|Get(ting)? ready( [A-Z])?|Communication Workshop|Picture dictionary|Reading Club \d*)$",  # 北师大的栏目标题
    re.I,
)
PAGE_REF_RE = re.compile(r"[pP]\.\s?S?(?:\d+|[\dOIlS]{1,3}\b)")  # 扫描版会认成大写 P.35，数字认成字母 p.O
POS_RE = re.compile(
    r"^(n|v|vt|vi|adj|adv|pron|prep|conj|interj|art|num|abbr|aux|modal|pl|link)\b", re.I
)
# 音标中间夹着的非音标字体字符：斜杠、逗号、英美音标记，以及外研初中用日文字体排的长音符 ː
POS_LEAD_RE = re.compile(
    r"^((?:n|v|vt|vi|adj|adv|pron|prep|conj|interj|int|art|num|abbr|modal v|aux v)\.(?:\s*&\s*[a-z]+\.)*)\s*(.+)$")
IPA_GLUE_RE = re.compile(r"[\s/,;ːˈˌ]*((NAmE|BrE|AmE)[\s/,;ːˈˌ]*)?")
VARIANT_MARK_RE = re.compile(r"^(NAmE|BrE|AmE)\b")
VARIANT_RE = re.compile(r"\s*\(\s*((NAmE|BrE|AmE)[^)]*)\)\s*")
LIGATURE_RE = re.compile(r"([ﬀ-ﬆ])(?: (?=[a-z]))?")  # "ﬁ ve"：连字后的空格是字宽造成的，一并去掉
# 全角字母、数字和 ＝．＇－ 转半角；全角括号、分号等中文标点保留
FULLWIDTH = {c: c - 0xFEE0 for c in [*range(0xFF10, 0xFF1A), *range(0xFF21, 0xFF3B), *range(0xFF41, 0xFF5B),
                                      0xFF1D, 0xFF0E, 0xFF07, 0xFF0D]}
# 词条末尾的课次/单元号：（１）、(7)
# 词条末尾的课次/单元/页码号：（１）、(7)、扫描版的「什么 2」、沪教小学的「苹果 U3」
REF_TAIL_RE = re.compile(
    r"\s*(?:[（(]\s*(\d+|w)\s*[）)]|(?<=[\u4e00-\u9fff）)])\s+U?(\d{1,3}))\s*$")
STAR_MARKS = "*△▲▫"  # 词头前的标记：*△▲ 选学/不要求，▫ 外研高中的选择性必修词
CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\xad\ue000-\uf8ff]")
# 词头到哪里为止：第一个不是拉丁字母（Latin-1）、引号、破折号、省略号的字符。不能只看汉字：沪教的中文字体
# 映射坏了，释义变成阿拉伯文、泰文、č 之类，只看汉字会把它们当成词头的一部分
HW_END_RE = re.compile(r"[^\s\u0000-\u00ff\u2010-\u201f\u2026\u22ef\u25ab\u25b2\u25b3]")  # △▲ 是选学标记；\s 含全角空格
CJK_RE = re.compile(r"[　-〿一-鿿＀-￯]")

# 各家音标字体的编码。SIL 的 Ipa-samdUclphon（人教）是 SAMPA 记法；CBIPA（外研初中）的表是拿词光的
# IPA 逐字对齐统计出来的；IPAPANNEW 等直接是 Unicode IPA，不转换。
SAMPA_TO_IPA = {
    "@": "ə", "{": "æ", "A": "ɑ", "Q": "ɒ", "O": "ɔ", "U": "ʊ", "I": "ɪ", "V": "ʌ",
    "3": "ɜ", "S": "ʃ", "Z": "ʒ", "T": "θ", "D": "ð", "N": "ŋ", '"': "ˈ", "%": "ˌ", ":": "ː",
}
CBIPA_TO_IPA = {
    "!": "ɪ", "'": "ˈ", "2": "ə", "%": "ʊ", "=": "ɒ", "0": "ɔ", "1": "ʃ", "3": "ʒ", "7": "ʌ",
    "9": "ŋ", "8": "θ", ";": "ˌ", "4": "ɑ", "^": "ɜ", "*": "æ", "6": "ð", ":": "ː",
}
# TimesKKPhoneticNewRoman（沪教、译林）：同样是对齐统计出来的；T/J 是 tʃ/dʒ（chair /TeR(r)/、age /eIJ/）
KK_TO_IPA = {
    "I": "ɪ", "3": "ˈ", "9": "ˈ", "4": "ˌ", "0": "ˌ", "R": "ə", "W": "ʊ", "C": "æ", "B": "ɒ", "V": "ʌ",
    "G": "ɡ", "O": "ɔ", "N": "ŋ", "A": "ɑ", "S": "ʃ", "F": "ɜ", "P": "θ", "Q": "ð", "Z": "ʒ", "T": "tʃ",
    "J": "dʒ", ":": "ː",
}
IPA_TABLES = [
    (re.compile(r"samd|sil", re.I), SAMPA_TO_IPA),
    (re.compile(r"^CBIPA$"), CBIPA_TO_IPA),
    (re.compile(r"KKPhonetic"), KK_TO_IPA),
    (re.compile(r"Times-PhoneticIPA"), {":": "ː"}),  # 只排长音符，其余字符映射已损坏
]


def decode_ipa(text, font="Ipa-samdUclphon1SILDoulos"):
    """音标字体文本 -> IPA。私用区字符先减 0xF000 还原成 ASCII，再按该字体的编码表映射。"""
    table = next((t for r, t in IPA_TABLES if r.search(font.split("+")[-1])), {})
    out = []
    for ch in text:
        code = ord(ch)
        if 0xF000 <= code <= 0xF0FF:
            ch = chr(code - 0xF000)
        out.append(table.get(ch, ch))
    return "".join(CONTROL_RE.sub("", c) for c in out)


def is_bold(span):
    return bool(span["flags"] & 16) or bool(BOLD_FONT_RE.search(span["font"]))


def is_italic(span):
    return bool(span["flags"] & 2) or bool(ITALIC_FONT_RE.search(span["font"]))


def is_ipa(span):
    return bool(IPA_FONT_RE.search(span["font"]))


def page_lines(page, ocr_observations=None):
    """页面上的非空行，每行是去掉空白 span 后的 span 列表。
    页面没有文字层、但有 OCR 结果时用 OCR 的行（见 ocr.py）。"""
    if ocr_observations is not None and not page.get_text().strip():
        raw = ocr.page_lines(ocr_observations, page.rect.width)
    else:
        raw = [line["spans"] for block in page.get_text("dict")["blocks"] for line in block.get("lines", [])]
    lines = []
    for line_spans in raw:
        spans = []
        for s in line_spans:
            if not s["text"].strip():
                continue
            if not is_ipa(s):  # 只拆连字 ﬁ/ﬂ、全角字母转半角；NFKC 会把全角标点也改掉，所以不能整段规范化
                text = LIGATURE_RE.sub(lambda m: unicodedata.normalize("NFKC", m.group(1)), s["text"])
                s = {**s, "text": CONTROL_RE.sub("", text.translate(FULLWIDTH))}  # 含私用区字符（Mrs\ue010）
            spans.append(s)
        if spans:
            lines.append(spans)
    return order_columns(lines)


def order_columns(lines):
    """双栏页按「先左栏、再右栏，栏内从上到下」重排。PDF 内容流的顺序有时是乱的（外研初中）。

    栏界不取页面中线，而是看词条起始 x 坐标聚成的两团：右团最左边再往左一点。
    人教小学左栏的页码引用（x≈216）就靠右，按中线切会被分到右栏。只有一团时保持原顺序。
    """
    # 只看自带释义/音标/页码的词条行：居中的字母标题、页标题不能参与分栏
    starts = sorted(head_span(l)["bbox"][0] for l in lines if index_like(l))
    if len(starts) < 6:
        return lines
    gap, right = max((b - a, b) for a, b in zip(starts, starts[1:]))
    left_n = sum(1 for x in starts if x < right)
    if gap < 100 or min(left_n, len(starts) - left_n) < 3:
        return lines
    boundary = right - 15  # 右栏的单元标题比词条略靠左（外研初中：269 对 277）

    def spanning(l):
        """总表之后的段落标题（Proper nouns、Glossary……）把页面切成上下几段，每段内再分栏。
        沪教：左栏 S–T、右栏 T–W 之后，Proper nouns 从左栏下方开始，按整栏读会先读到它。
        单元标题不能切：双栏的按单元表里单元标题就在栏内。"""
        return bool(INDEX_END_RE.match(line_text(l)))

    cuts = sorted(line_center(l) for l in lines if spanning(l))
    ordered = []
    for band in range(len(cuts) + 1):
        top = cuts[band - 1] if band else float("-inf")
        bottom = cuts[band] if band < len(cuts) else float("inf")
        band_lines = [l for l in lines if top <= line_center(l) < bottom]
        heads = sorted((l for l in band_lines if spanning(l)), key=line_center)
        rest = [l for l in band_lines if not spanning(l)]
        ordered += heads
        for col in (False, True):
            ordered += by_rows([l for l in rest if (l[0]["bbox"][0] >= boundary) == col])
    return ordered


def by_rows(lines):
    """栏内从上到下。同一视觉行的几段（词条和行尾的课次号「（2）」）上沿可能差一两个点，按行分组后再从左到右。"""
    rows = []
    for l in sorted(lines, key=line_center):
        if rows and rows[-1][0][0]["bbox"][1] <= line_center(l) <= rows[-1][0][0]["bbox"][3]:
            rows[-1].append(l)
        else:
            rows.append([l])
    return [l for row in rows for l in sorted(row, key=lambda l: l[0]["bbox"][0])]


def same_row(a, b):
    return a[0]["bbox"][1] <= line_center(b) <= a[0]["bbox"][3]


def line_center(spans):
    return (spans[0]["bbox"][1] + spans[0]["bbox"][3]) / 2


def line_text(spans):
    """行文字。叠了几层的标题（冀教 "Vocabulary Vocabulary"、沪教三层）合成一份，免得认不出标题。"""
    text = re.sub(r"\s+", " ", "".join(s["text"] for s in spans)).strip()
    m = re.fullmatch(r"(.+?)(?: \1)+", text)
    return m.group(1) if m and len(m.group(1)) > 2 else text


def font_family(font):
    """去掉子集前缀和字重，粗细体算同一族：ABCDEF+ArnoPro-Smbd -> ArnoPro，Arial-BoldMT / ArialMT -> Arial，
    GCFrutigerRoman / GCFrutigerBold -> GCFrutiger。"""
    name = font.split("+")[-1].split("-")[0]
    name = re.sub(r"(PS)?(MT)?$", "", name) or name
    return re.sub(r"(Roman|Bold|Light|Medium|Regular|Italic|Semibold|Black|Book|Heavy)+$", "", name) or name


def ocr_pos(text):
    """扫描版里认错的词性：Qd. 有自主权的。Mr. 先生 这类真缩写除外。"""
    m = re.match(r"([A-Za-z]{1,3})[.,，]\s*([\u4e00-\u9fff]|$)", text)
    return bool(m) and m.group(1).lower() not in {"mr", "mrs", "ms", "dr", "st", "no", "jr", "sr", "vs"}


def head_span(spans):
    """行首第一个有内容的 span；选学标记 * 有时单独一个 span（外研初中 "* " + "hello"）。"""
    return next((s for s in spans if s["text"].strip().strip(STAR_MARKS).strip()), spans[0])


def starts_entry(spans, families=None):
    """families 是本书词头的字体族；同一页上用标题字体画的装饰字母（如 pp）不算词条。"""
    first = head_span(spans)
    text = first["text"].lstrip().lstrip(STAR_MARKS).lstrip()
    return (
        not is_ipa(first)
        and not is_italic(first)
        and re.match(r"[A-Za-z]", text) is not None
        and not PAGE_REF_RE.match(text)
        and not POS_LEAD_RE.match(text)  # n. 名词…… 是上一条的义项（扫描版没有斜体可以区分）
        and not re.fullmatch(r"[A-Za-z]{1,4}[.,，]\s*", line_text(spans))  # 单独一行的词性：ad. 被认成 Qd.
        and not (first["font"] == "OCR" and ocr_pos(text))
        and (families is None or font_family(first["font"]) in families)
    )


def headword_families(lines, like=None):
    """词头字体族：占词条行 20% 以上的都算。一本书的词头可能混用两个字体族（外研初中 Times / TimesNewRoman）。"""
    like = like or (lambda l: starts_entry(l) and not UNIT_RE.match(line_text(l)))
    counts = Counter(font_family(head_span(l)["font"]) for l in lines if like(l))
    total = sum(counts.values())
    return {f for f, n in counts.items() if n >= total * 0.2}


def strong_marker(span):
    return is_ipa(span) or PAGE_REF_RE.fullmatch(span["text"].strip())


def entry_like(spans):
    """像词条的行：英文开头，同一行里还有中文释义。"""
    return starts_entry(spans) and any(CJK_RE.search(s["text"]) for s in spans)


def find_start_page(doc, lines_of=None):
    """单词表起始页：书的后半部分里，第一张有单元标题、且像单词表的页面。

    像单词表 = 至少 5 处音标或页码引用，并且至少 5 行「英文 + 中文」的词条行。只看前者会撞上课文里的
    语音练习页（沪教：/aW/ /w/ /j/ 和页码），只看后者会撞上课文注释、译文页。都找不到时依次放宽：
    小学词表常常没有音标（只看词条行），极少数词表没有中文（只看音标/页码）。
    """
    lines_of = lines_of or (lambda i: page_lines(doc[i]))
    pages = [(i, lines_of(i)) for i in range(len(doc) // 2, len(doc))]
    pages = [(i, lines) for i, lines in pages if any(UNIT_RE.match(line_text(l)) for l in lines)]

    def strong(lines):
        return sum(1 for l in lines for s in l if strong_marker(s)) >= 5

    def entries(lines):
        return sum(1 for l in lines if entry_like(l)) >= 5

    def titled(lines):  # 页上有单词表的标题（译林初中七上的 Wordlist 只有词性、页码，没有中文）
        return any(WORDLIST_TITLE_RE.match(line_text(l)) for l in lines) and (strong(lines) or entries(lines))

    for test in (titled, lambda l: strong(l) and entries(l), entries, strong):
        for i, lines in pages:
            if test(lines):
                return i
    return None


def parse_entry(lines):
    """把一个词条的若干行 span 解析成 {hw, ipa, senses, page, core}。"""
    spans = [s for l in lines for s in l]
    hw_parts, ipa_parts, senses, pages = [], [], [], []
    core = is_bold(head_span(spans))
    phase = "hw"
    for s in spans:
        text = s["text"]
        for ref in PAGE_REF_RE.findall(text):
            pages.append(ref.replace(" ", ""))
        text = PAGE_REF_RE.sub("", text)
        if not text.strip():
            continue
        if is_ipa(s):
            phase = "ipa"
            ipa_parts.append(decode_ipa(text, s["font"]))
            continue
        if phase == "hw" and is_italic(s) and VARIANT_MARK_RE.match(text.strip()):
            hw_parts.append(text)  # organise (NAmE -ize)：拼写变体标记，拆进 variant
            continue
        if phase == "ipa" and is_italic(s) and IPA_GLUE_RE.fullmatch(text):
            ipa_parts.append(text)  # /ˈætɪtjuːd; NAmE ˈætɪtuːd/
            continue
        if phase == "hw" and not is_italic(s):
            # 正文字体里的「空格 + 斜杠」开始音标：外研初中有的音标直接用正文字体排 Unicode IPA（jeans /dʒiːnz/）。
            # 斜杠前没有空格的是词头本身（telephone/phone number）
            slash = re.search(r"(?:^|\s)/", text)
            cjk = HW_END_RE.search(text)
            if slash and (not cjk or slash.start() < cjk.start()):
                hw_parts.append(text[: slash.start()])
                text = text[slash.start():].lstrip()
                phase = "ipa"
        if phase == "ipa" and not is_italic(s):
            joined = "".join(ipa_parts)
            opening = not joined and text.startswith("/")
            if opening or joined.count("/") % 2 == 1:  # 音标的斜杠还没闭合：到下一个斜杠为止都是音标
                close = text.find("/", 1 if opening else 0)
                if close == -1:
                    ipa_parts.append(text)
                    continue
                ipa_parts.append(text[: close + 1])
                text = text[close + 1:]
                if not text.strip():
                    continue
        if phase == "hw" and not is_italic(s):
            cjk = HW_END_RE.search(text)
            if cjk:
                hw_parts.append(text[: cjk.start()])
                text = text[cjk.start():]
                phase = "body"
            else:
                hw_parts.append(text)
                continue
        if phase == "ipa" and not is_italic(s) and not CJK_RE.search(text) and IPA_GLUE_RE.fullmatch(text):
            ipa_parts.append(text)  # 音标两侧的斜杠/逗号、英美音标记 NAmE 有时用正文字体
            continue
        phase = "body"
        word = text.strip()
        open_pos = senses and senses[-1]["pos"] and not senses[-1]["zh"]
        if open_pos and (is_italic(s) or word == "&"):
            senses[-1]["pos"] += " " + word  # "adj." "&" "n." 分在几个 span 里
        elif is_italic(s) and POS_RE.match(word):
            senses.append({"pos": word, "zh": ""})
        else:
            if not senses:
                senses.append({"pos": "", "zh": ""})
            senses[-1]["zh"] += text

    hw = re.sub(r"\s+", " ", "".join(hw_parts)).strip()
    hw = re.sub(r"\s*/\s*$", "", hw)  # 去掉连在词头字体里的音标左斜杠
    from_ocr = bool(spans) and spans[0]["font"] == "OCR"
    if from_ocr and "/" in hw:
        hw = hw.split("/", 1)[0].strip()  # 扫描版的音标认不准，常跟词头粘在一起：advocate/"aedvakert
    variant = ""
    m = VARIANT_RE.search(hw)
    if m:
        variant = re.sub(r"\s+", " ", m.group(1)).strip()
        hw = (hw[: m.start()] + " " + hw[m.end():]).strip()
    ipa = re.sub(r"\s+", " ", "".join(ipa_parts)).strip()
    if ipa and not ipa.startswith("/"):
        ipa = "/" + ipa
    if ipa and not ipa.endswith("/"):
        ipa += "/"
    ipa = re.sub(r"/\s*,\s*/", "/, /", ipa)
    ref = ""
    for sense in senses:
        sense["zh"] = re.sub(r"\s+", " ", sense["zh"]).strip()
        m = POS_LEAD_RE.match(sense["zh"])
        if m and not sense["pos"]:  # 词性没用斜体排时混在释义开头：n. 比萨饼、int.你好
            sense["pos"], sense["zh"] = m.group(1), m.group(2)
    if senses:
        m = REF_TAIL_RE.search(senses[-1]["zh"])
        if m:
            ref = m.group(1) or m.group(2)
            senses[-1]["zh"] = senses[-1]["zh"][: m.start()]
    senses = [s for s in senses if s["pos"] or s["zh"]]
    marks = hw[: len(hw) - len(hw.lstrip(STAR_MARKS + " "))]
    star = any(m in marks for m in "*△▲")
    hw = hw.lstrip(STAR_MARKS + " ").strip()
    entry = {"hw": hw, "ipa": ipa, "senses": senses, "page": pages[0] if pages else "", "core": core}
    if star:
        entry["star"] = True
    if "▫" in marks:
        entry["elective"] = True
    if from_ocr:
        entry["ocr"] = True
    if variant:
        entry["variant"] = variant
    if ref:
        entry["ref"] = ref
    return entry


def open_paren(entry_lines):
    """词头的英文括号没闭合，下一行就是续行，哪怕它以英文开头：Thanksgiving (Thanksgiving / Day)。
    只看只有一行的词条的词头部分；释义、备注里没闭合的括号不算，否则会把后面的词条都吞掉。"""
    if len(entry_lines) != 1:
        return False
    head = HW_END_RE.split(line_text(entry_lines[0]), 1)[0]
    return head.count("(") > head.count(")")


def extract_book(pdf_path):
    doc = fitz.open(pdf_path)
    ocr_pages = ocr.load(Path(pdf_path).stem)

    def lines_of(i):
        return page_lines(doc[i], ocr_pages.get(i))

    result = extract_lines(doc, lines_of)
    entries = [e for u in result["units"] for e in u["entries"]] or result.get("index", [])
    if entries and sum(1 for e in entries if e.get("ocr")) > len(entries) / 2:
        result["ocr"] = True  # 大部分词条来自 OCR 才算扫描版；有文字层的书里偶尔一页图片不算
    return result


def find_index_page(doc, lines_of):
    """没有按单元表时找字母序总表：后半本里第一张有字母标题（A / Aa）、且至少 15 行英文+中文词条的页。"""
    for i in range(len(doc) // 2, len(doc)):
        lines = lines_of(i)
        letters = sum(1 for l in lines if re.fullmatch(LETTER_HEADING, line_text(l)))
        if letters and sum(1 for l in lines if index_like(l)) >= 15:
            return i
    return None


def extract_lines(doc, lines_of):
    start = find_start_page(doc, lines_of)
    if start is None:
        # 只有字母序总表的书（沪教小学三年级）：单元靠总表里每个词的单元号（U3）在 normalize 里重建
        index_start = find_index_page(doc, lines_of)
        if index_start is None:
            return {"units": [], "warnings": ["未找到按单元单词表"]}
        families = headword_families(lines_of(index_start), index_like)
        lines = ((i, spans) for i in range(index_start, len(doc)) for spans in lines_of(i))
        return {"pages": [index_start, index_start], "units": [], "index": extract_index(lines, families),
                "indexOnly": True, "warnings": ["没有按单元表，按总表的单元号分单元"]}
    units, warnings = [], []
    current = None
    entry_lines = []
    # 词头字体族逐页统计、取前 8 页的并集：外研初中七上的预备篇和正文用的是两种 Times
    families = set().union(*(headword_families(lines_of(i)) for i in range(start, min(start + 8, len(doc)))))
    section = 0

    def flush():
        if entry_lines and current is not None:
            entry = parse_entry(entry_lines)
            if not entry["hw"]:
                warnings.append(f"{current['name']}: 空词头 {line_text(entry_lines[0])!r}")
            else:
                current["entries"].append(entry)
        entry_lines.clear()

    lines = ((i, spans) for i in range(start, len(doc)) for spans in lines_of(i))
    prev = None
    for i, spans in lines:
        text = line_text(spans)
        last, prev = prev, spans
        if SKIP_RE.match(text):
            continue
        # 字母标题自成一行；和上一行在同一视觉行上的单个字母是释义的一部分（X-ray … n. X光 的「X」）
        letter_in_row = len(text) <= 2 and last is not None and same_row(last, spans)
        if STOP_RE.match(text) and units and not letter_in_row:  # 第一个单元之前的 Vocabulary 是词表自己的标题
            flush()
            index = extract_index(lines, families)
            return {"pages": [start, i], "units": finish_units(units), "index": index, "warnings": warnings}
        if units and WORDLIST_TITLE_RE.match(text) and current and current["entries"]:
            section += 1  # 又一张词表开始了（外研初中七上：预备篇 Module 1–4 之后是正文 Module 1–10）
        if UNIT_RE.match(text) and spans[0]["bbox"][3] < 35:
            continue  # 页眉里的 Starter / Unit 3 不是单元标题
        if UNIT_RE.match(text):
            flush()
            # 同一个单元标题可能画了两遍（全角 Ｕｎｉｔ１ 上再叠一层 Unit 1），而且叠加层排在整页内容之后：
            # 同一张词表里重复的标题切回已有单元，不新开空单元
            key = (section, text.replace(" ", "").lower())
            current = next((u for u in units if u["key"] == key), None)
            if current is None:
                current = {"name": text, "key": key, "entries": []}
                units.append(current)
            continue
        if current is None:
            continue
        if starts_entry(spans, families) and not open_paren(entry_lines):
            flush()
            entry_lines.append(spans)
        elif entry_lines:
            entry_lines.append(spans)
        else:
            warnings.append(f"{current['name']}: 孤立续行 {text!r}")
    flush()
    warnings.append("没遇到结束标记，单词表可能延伸到书末")
    return {"pages": [start, len(doc) - 1], "units": finish_units(units), "index": [], "warnings": warnings}


def finish_units(units):
    """去掉内部用的 key；前一张词表里和后面重名的单元加上 Starter 前缀（外研初中七上的预备篇）。"""
    later = {}
    for u in units:
        later.setdefault(u["key"][1], []).append(u["key"][0])
    out = []
    for u in units:
        name = u["name"]
        if u["key"][0] < max(later[u["key"][1]]):
            name = f"Starter {name}"
        out.append({"name": name, "entries": u["entries"]})
    return out


def index_like(spans):
    """总表词条的开头行：英文开头，这一行自带中文释义、音标或页码。"""
    return starts_entry(spans) and any(strong_marker(s) or CJK_RE.search(s["text"]) for s in spans)


def extract_index(lines, families):
    """按单元表之后的字母序总表，供 QA 核对；带课次/单元号的总表还用来补全按单元表（见 normalize）。

    总表后面常接着练习页、课堂用语、编者名单，这些行没有中文释义/音标/页码，不算词条；
    再遇到单元标题说明进了另一个按单元的附录（如 Useful expressions），总表到此为止。

    字母序「从头开始」时（见 restarted）先挂起、不收词，直到首字母回到挂起前的位置再继续：
    冀教左栏 W 部之后插了一张人名地名表（Benny、Mary……），W 部剩下的词在右栏。
    只在挂起的那一页内恢复，翻页还没恢复就结束：外研小学总表后的第二张词表、沪教初中总表后的
    初中词汇总表都是从 a 重新排起。
    """
    words, entry_lines = [], []
    lines = list(lines)
    # 总表的黑体词头可能和按单元表不是一个字体族（冀教）：再加上总表开头一段的词头字体族。
    # 总表后面的不规则动词表等用的是别的字体，不会混进来。
    families = families | headword_families([l for _, l in lines[:80]], index_like)

    def flush():
        spans = [s for l in entry_lines for s in l]
        if spans and any(strong_marker(s) or CJK_RE.search(s["text"]) for s in spans):
            entry = parse_entry(entry_lines)
            if entry["hw"]:
                words.append(entry)
        entry_lines.clear()

    def head_tokens(spans):
        head = CJK_RE.split(line_text(spans).lstrip(STAR_MARKS), 1)[0]
        return [t.lower() for t in re.findall(r"[A-Za-z]+", head)]

    def restarted(spans):
        """字母序往回跳：总表结束了，或者中间插了别的表。"""
        if not words or not starts_entry(spans, families):
            return False
        prev = words[-1]["hw"][:1].lower()
        tokens = head_tokens(spans)
        # 词组子条目不算：responsibility 下面的 be responsible for 含有首字母相同的词
        # 往回跳了两个字母以上（z 之后的 Goldilocks 故事页、W 部中间插的人名表）
        return bool(tokens) and ord(tokens[0][0]) <= ord(prev) - 2 and not any(t[0] == prev for t in tokens)

    suspended = None  # 挂起时所在的页

    for page, spans in lines:
        text = line_text(spans)
        if INDEX_END_RE.match(text) or UNIT_RE.match(text) or is_credits(text):
            break
        if SKIP_RE.match(text) or STOP_RE.match(text):  # 要在 restarted 之前：页眉 Appendices 也是词头字体
            continue
        if suspended is not None:
            if page != suspended:
                break
            tokens = head_tokens(spans) if index_like(spans) else []
            if not tokens or tokens[0][0] < words[-1]["hw"][:1].lower():
                continue
            suspended = None
        if restarted(spans):
            flush()
            if restarted(spans):
                suspended = page
                continue
        if starts_entry(spans, families):
            flush()
            entry_lines.append(spans)
        elif entry_lines:
            entry_lines.append(spans)
    flush()
    return words


def main(ids=None):
    books = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    if ids:
        books = [b for b in books if b["id"] in ids]
    EXTRACT_DIR.mkdir(parents=True, exist_ok=True)
    missing = [b["id"] for b in books if not (PDF_DIR / f"{b['id']}.pdf").exists()]
    if missing:
        print(f"extract: 跳过 {len(missing)} 本未下载的书")
    for b in books:
        pdf = PDF_DIR / f"{b['id']}.pdf"
        if not pdf.exists():
            continue
        result = {"id": b["id"], **extract_book(pdf)}
        (EXTRACT_DIR / f"{b['id']}.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        n = sum(len(u["entries"]) for u in result["units"])
        print(f"extract: {b['id']} {len(result['units'])} 单元 {n} 词条 {len(result['warnings'])} 警告")
