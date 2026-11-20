"""真实 PDF 回归：每个版式一本书，数字都和书后字母序总表人工核对过。PDF 没下载时跳过。"""
import pytest

from tw.extract import extract_book
from tw.normalize import normalize_book
from tw.paths import PDF_DIR
from tw.qa import check_book

GOLDEN = {
    # book: (单元数, 词条数, 总表词数, 抽查词条)
    "ps-pep-3a": (6, 64, 64, ("Unit 4", "panda", "/ˈpændə/", "大熊猫")),
    "jh-pep-7a": (12, 433, 388, ("Unit 9", "Thursday", "/θɜː(r)zdeɪ/", "星期四")),
    "sh-pep-b1": (6, 364, 364, ("Welcome Unit", "exchange", "/ɪksˈtʃeɪndʒ/", "交换；交流")),
    # 外研高中：UNIT 大写、▫/* 标记、IPAPANNEW 音标
    "sh-wy-b1": (6, 411, 411, ("UNIT 1", "curious", "/ˈkjʊəriəs/", "好奇的")),
    # 冀教小学：全角字母、叠层标题、按课次号用总表补全
    "ps-jj-3a": (4, 164, 164, ("Unit 2", "window", "", "窗户")),
    # 北师大小学：扫描版，OCR
    "ps-bsd-6a": (6, 99, 40, ("Unit 2", "film", "", "电影")),
    # 沪教初中：中文字体映射损坏（释义丢弃，zh=None）、KK 音标、通栏标题切分双栏
    "jh-hj-7b": (8, 215, 215, ("Unit 2", "flag", "/flæɡ/", None)),
}


@pytest.mark.parametrize("book_id", GOLDEN)
def test_golden(book_id):
    pdf = PDF_DIR / f"{book_id}.pdf"
    if not pdf.exists():
        pytest.skip(f"{book_id} 未下载")
    units, entries, index, (unit, hw, ipa, zh) = GOLDEN[book_id]
    extracted = {"id": book_id, **extract_book(pdf)}
    normalized = normalize_book(extracted)
    assert len(normalized["units"]) == units
    assert sum(len(u["words"]) for u in normalized["units"]) == entries

    report = check_book(extracted, normalized)
    assert report["index"] == index
    assert report["missing"] == []

    [u] = [u for u in normalized["units"] if u["name"] == unit]
    [w] = [w for w in u["words"] if w["hw"] == hw]
    assert w["ipa"] == ipa
    if zh is None:
        assert w.get("zhBad") and not w["senses"]
    else:
        assert w["senses"][0]["zh"] == zh
