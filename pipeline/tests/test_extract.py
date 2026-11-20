"""三种版式各一个样例，span 照真实 PDF 里取到的字体和文字构造。"""
from tw.extract import decode_ipa, parse_entry, starts_entry

IPA = "Ipa-samdUclphon1SILDoulos"


def span(text, font, flags=0):
    return {"text": text, "font": font, "flags": flags, "size": 12}


def pua(ascii_text):
    return "".join(chr(0xF000 + ord(c)) for c in ascii_text)


def test_decode_ipa():
    assert decode_ipa(pua('/"rU:l@(r)/')) == "/ˈrʊːlə(r)/"
    assert decode_ipa("kVl@(r)") == "kʌlə(r)"
    assert decode_ipa(pua('/%redZI"streISn/')) == "/ˌredʒɪˈstreɪʃn/"
    assert decode_ipa("'be!s;b0ː", "CBIPA") == "ˈbeɪsˌbɔː"  # 外研初中
    assert decode_ipa("/pəˈtenʃl/", "IPAPANNEW") == "/pəˈtenʃl/"  # 已经是 Unicode，不转换
    assert decode_ipa("/3dZFmRn/", "TimesKKPhoneticNewRoman") == "/ˈdʒɜmən/"  # 沪教：German
    assert decode_ipa("TeR(r)", "TimesKKPhoneticNewRoman") == "tʃeə(r)"  # 译林：chair


def test_primary_layout():
    # 小学 PEP：粗体词头 + 私用区音标 + 中文和页码在同一个 span
    line = [span("pencil box", "ComicSansMS-Bold"), span(pua('/"pensl "bQks/ '), IPA), span("铅笔盒 p.8", "FZKTJW--GB1-0")]
    e = parse_entry([line])
    assert e == {"hw": "pencil box", "ipa": "/ˈpensl ˈbɒks/", "senses": [{"pos": "", "zh": "铅笔盒"}],
                 "page": "p.8", "core": True}


def test_junior_layout_wrapped_with_page_ref_line():
    # 初中人教：斜杠在词头字体里，释义折行，页码单独一行；白体词头 = 非核心词
    lines = [
        [span("telephone /", "ArnoPro-Regular"), span("telIf@Un", IPA), span("/ ", "ArnoPro-Smbd")],
        [span("n.", "ArnoPro-Italic"), span("电话；电话机", "FZSSJW--GB1-0")],
        [span("p.4", "ArnoPro-Regular")],
    ]
    e = parse_entry(lines)
    assert e["hw"] == "telephone"
    assert e["ipa"] == "/telɪfəʊn/"
    assert e["senses"] == [{"pos": "n.", "zh": "电话；电话机"}]
    assert e["page"] == "p.4"
    assert e["core"] is False


def test_senior_layout_multi_sense_and_variant():
    # 高中人教：多义项分行，词性用 "&" 连接，NAmE 拼写变体
    lines = [
        [span("organise ", "DIN-Medium"), span("(", "DIN-Medium"), span("NAmE", "Times-Italic"),
         span(" -ize)", "DIN-Medium"), span(pua('/"O:g@naIz/'), IPA)],
        [span("vt. ", "Times-Italic"), span("&", "Times-Roman"), span(" vi.", "Times-Italic"), span("组织", "FZZDXJW")],
        [span("n. ", "Times-Italic"), span("组织者", "FZZDXJW")],
    ]
    e = parse_entry(lines)
    assert e["hw"] == "organise"
    assert e["variant"] == "NAmE -ize"
    assert e["ipa"] == "/ˈɔːgənaɪz/"
    assert e["senses"] == [{"pos": "vt. & vi.", "zh": "组织"}, {"pos": "n.", "zh": "组织者"}]


def test_ipa_with_american_variant():
    line = [span("attitude", "DIN-Medium"), span(pua('/"{tItju:d; '), IPA), span("NAmE", "Times-Italic"),
            span(pua(' "{tItu:d/'), IPA), span("n.", "Times-Italic"), span("态度", "FZZDXJW")]
    e = parse_entry([line])
    assert e["ipa"] == "/ˈætɪtjuːd; NAmE ˈætɪtuːd/"
    assert e["senses"] == [{"pos": "n.", "zh": "态度"}]


def test_starts_entry():
    assert starts_entry([span("ruler", "ComicSansMS-Bold")])
    assert not starts_entry([span("n.", "Times-Italic")])
    assert not starts_entry([span("p.S9", "ArnoPro-Regular")])
    assert not starts_entry([span("（美国）全国篮球协会", "FZSSJW")])
    # 标题字体画的装饰字母不是词条
    assert not starts_entry([span("pp", "Geometric706BT-BlackA")], families={"ComicSansMS"})
    assert starts_entry([span("plate", "ComicSansMS")], families={"ComicSansMS"})
    # 选学标记 * 单独一个 span
    assert starts_entry([span("* ", "Symbol"), span("hello", "Times-Bold")], families={"Times"})
