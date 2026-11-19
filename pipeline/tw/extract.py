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

import fitz

from .paths import EXTRACT_DIR, OUT, PDF_DIR

IPA_FONT_RE = re.compile(r"ipa|phon|kingsoft|ksphon", re.I)
BOLD_FONT_RE = re.compile(r"bold|bd\b|smbd|semibold|medium|black|heavy|-bla", re.I)
ITALIC_FONT_RE = re.compile(r"italic|-it\b|oblique", re.I)

UNIT_RE = re.compile(
    r"^(Starter Unit \d+|Welcome Unit|Unit \d+|Unit (One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten)"
    r"|Module \d+|Starter|Lesson \d+|Project \d+|Recycle \d+)$"
)
# 按单元表之后的段落（字母序总表、人名表、不规则动词表）
STOP_RE = re.compile(r"^(Vocabulary( Index)?|Appendix [2-9]|词\s*汇\s*表|Name List|Irregular Verbs|[A-Z])$")
# 字母序总表之后的段落
INDEX_END_RE = re.compile(r"^(Name List|Irregular Verbs|Appendix [3-9]|Proper Nouns|专有名词|后\s*记|本册教科书.*)$")
SKIP_RE = re.compile(
    r"^(\d+|Appendix \d+|Appendices|Words and Expressions in Each Unit|Words in each unit"
    r"|单\s*元\s*词\s*汇\s*表|（注：.*）)$"
)
PAGE_REF_RE = re.compile(r"p\.\s?S?\d+")
POS_RE = re.compile(
    r"^(n|v|vt|vi|adj|adv|pron|prep|conj|interj|art|num|abbr|aux|modal|pl|link)\b", re.I
)
IPA_GLUE_RE = re.compile(r"[\s/,;]*((NAmE|BrE|AmE)[\s/,;]*)?")
VARIANT_MARK_RE = re.compile(r"^(NAmE|BrE|AmE)\b")
VARIANT_RE = re.compile(r"\s*\(\s*((NAmE|BrE|AmE)[^)]*)\)\s*")
LIGATURE_RE = re.compile(r"([ﬀ-ﬆ])(?: (?=[a-z]))?")  # "ﬁ ve"：连字后的空格是字宽造成的，一并去掉
CJK_RE = re.compile(r"[　-〿一-鿿＀-￯]")

SAMPA_TO_IPA = {
    "@": "ə", "{": "æ", "A": "ɑ", "Q": "ɒ", "O": "ɔ", "U": "ʊ", "I": "ɪ", "V": "ʌ",
    "3": "ɜ", "S": "ʃ", "Z": "ʒ", "T": "θ", "D": "ð", "N": "ŋ", '"': "ˈ", "%": "ˌ", ":": "ː",
}


def decode_ipa(text):
    """音标字体文本 -> IPA。私用区字符先减 0xF000 还原成 ASCII，再按 SAMPA 映射。"""
    out = []
    for ch in text:
        code = ord(ch)
        if 0xF000 <= code <= 0xF0FF:
            ch = chr(code - 0xF000)
        out.append(SAMPA_TO_IPA.get(ch, ch))
    return "".join(out)


def is_bold(span):
    return bool(span["flags"] & 16) or bool(BOLD_FONT_RE.search(span["font"]))


def is_italic(span):
    return bool(span["flags"] & 2) or bool(ITALIC_FONT_RE.search(span["font"]))


def is_ipa(span):
    return bool(IPA_FONT_RE.search(span["font"]))


def page_lines(page):
    """页面上的非空行，每行是去掉空白 span 后的 span 列表。"""
    lines = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            spans = []
            for s in line["spans"]:
                if not s["text"].strip():
                    continue
                if not is_ipa(s):  # 只拆连字 ﬁ/ﬂ；NFKC 会把全角标点也改掉，所以不能整段规范化
                    s = {**s, "text": LIGATURE_RE.sub(lambda m: unicodedata.normalize("NFKC", m.group(1)), s["text"])}
                spans.append(s)
            if spans:
                lines.append(spans)
    return lines


def line_text(spans):
    return re.sub(r"\s+", " ", "".join(s["text"] for s in spans)).strip()


def font_family(font):
    """ABCDEF+ArnoPro-Smbd -> ArnoPro：去掉子集前缀和字重后缀，粗细体算同一族。"""
    return font.split("+")[-1].split("-")[0]


def starts_entry(spans, family=None):
    """family 是本书词头的字体族；同一页上用标题字体画的装饰字母（如 pp）不算词条。"""
    first = spans[0]
    text = first["text"].lstrip()
    return (
        not is_ipa(first)
        and not is_italic(first)
        and re.match(r"[A-Za-z]", text) is not None
        and not PAGE_REF_RE.match(text)
        and (family is None or font_family(first["font"]) == family)
    )


def headword_family(lines):
    """单词表首页上最常见的词头字体族。"""
    counts = Counter(font_family(l[0]["font"]) for l in lines if starts_entry(l) and not UNIT_RE.match(line_text(l)))
    return counts.most_common(1)[0][0] if counts else None


def find_start_page(doc):
    """单词表起始页：书的后半部分里，第一张既有单元标题、又有至少 5 处音标或页码引用的页面。"""
    for i in range(len(doc) // 2, len(doc)):
        lines = page_lines(doc[i])
        units = sum(1 for l in lines if UNIT_RE.match(line_text(l)))
        markers = sum(1 for l in lines for s in l if is_ipa(s) or PAGE_REF_RE.fullmatch(s["text"].strip()))
        if units and markers >= 5:
            return i
    return None


def parse_entry(lines):
    """把一个词条的若干行 span 解析成 {hw, ipa, senses, page, core}。"""
    spans = [s for l in lines for s in l]
    hw_parts, ipa_parts, senses, pages = [], [], [], []
    core = is_bold(spans[0])
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
            ipa_parts.append(decode_ipa(text))
            continue
        if phase == "hw" and is_italic(s) and VARIANT_MARK_RE.match(text.strip()):
            hw_parts.append(text)  # organise (NAmE -ize)：拼写变体标记，拆进 variant
            continue
        if phase == "ipa" and is_italic(s) and IPA_GLUE_RE.fullmatch(text):
            ipa_parts.append(text)  # /ˈætɪtjuːd; NAmE ˈætɪtuːd/
            continue
        if phase == "hw" and not is_italic(s):
            cjk = CJK_RE.search(text)
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
    for sense in senses:
        sense["zh"] = re.sub(r"\s+", " ", sense["zh"]).strip()
    senses = [s for s in senses if s["pos"] or s["zh"]]
    entry = {"hw": hw, "ipa": ipa, "senses": senses, "page": pages[0] if pages else "", "core": core}
    if variant:
        entry["variant"] = variant
    return entry


def extract_book(pdf_path):
    doc = fitz.open(pdf_path)
    start = find_start_page(doc)
    if start is None:
        return {"units": [], "warnings": ["未找到按单元单词表"]}
    units, warnings = [], []
    current = None
    entry_lines = []
    family = headword_family(page_lines(doc[start]))

    def flush():
        if entry_lines and current is not None:
            entry = parse_entry(entry_lines)
            if not entry["hw"]:
                warnings.append(f"{current['name']}: 空词头 {line_text(entry_lines[0])!r}")
            else:
                current["entries"].append(entry)
        entry_lines.clear()

    lines = ((i, spans) for i in range(start, len(doc)) for spans in page_lines(doc[i]))
    for i, spans in lines:
        text = line_text(spans)
        if SKIP_RE.match(text):
            continue
        if STOP_RE.match(text):
            flush()
            index = extract_index(lines, family)
            return {"pages": [start, i], "units": units, "index": index, "warnings": warnings}
        if UNIT_RE.match(text):
            flush()
            current = {"name": text, "entries": []}
            units.append(current)
            continue
        if current is None:
            continue
        if starts_entry(spans, family):
            flush()
            entry_lines.append(spans)
        elif entry_lines:
            entry_lines.append(spans)
        else:
            warnings.append(f"{current['name']}: 孤立续行 {text!r}")
    flush()
    warnings.append("没遇到结束标记，单词表可能延伸到书末")
    return {"pages": [start, len(doc) - 1], "units": units, "index": [], "warnings": warnings}


def extract_index(lines, family):
    """按单元表之后的字母序总表，只取词头，供 QA 和按单元表互相核对。"""
    words, entry_lines = [], []

    def flush():
        if entry_lines:
            hw = parse_entry(entry_lines)["hw"]
            if hw:
                words.append(hw)
        entry_lines.clear()

    for _, spans in lines:
        text = line_text(spans)
        if INDEX_END_RE.match(text):
            break
        if SKIP_RE.match(text) or STOP_RE.match(text):
            continue
        if starts_entry(spans, family):
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
