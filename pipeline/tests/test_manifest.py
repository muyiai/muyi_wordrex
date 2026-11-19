import pytest

from tw.manifest import build_manifest, parse_path, parse_volume


@pytest.mark.parametrize("name, expected", [
    ("义务教育教科书·英语七年级上册.pdf", (7, "a", "7a", "七年级上册")),
    ("义务教育教科书·英语九年级全一册.pdf", (9, "", "9", "九年级全一册")),
    ("义务教育教科书·英语（PEP）（三年级起点）三年级上册.pdf", (3, "a", "3a", "三年级上册")),
    ("普通高中教科书·英语必修 第一册.pdf", (10, "b1", "b1", "必修 第一册")),
    ("普通高中教科书·英语选择性必修 第四册.pdf", (11, "x4", "x4", "选择性必修 第四册")),
    ("说明.pdf", None),
])
def test_parse_volume(name, expected):
    assert parse_volume(name) == expected


def test_parse_path_split_parts():
    # 两种分卷写法都还原成同一个 PDF 文件名
    merge = "初中/英语/译林版-译林出版社/七年级/X七年级上册.pdf_merge_folder/X七年级上册.pdf.2"
    flat = "小学/英语/译林版三年级起点/X三年级上册.pdf.3"
    assert parse_path(merge) == ("jh", "译林版-译林出版社", "X七年级上册.pdf", 2)
    assert parse_path(flat) == ("ps", "译林版三年级起点", "X三年级上册.pdf", 3)
    assert parse_path("高中/英语/人教版-人民教育出版社/普通高中教科书·英语必修 第一册.pdf")[3] == 0
    assert parse_path("高中/数学/人教版/x.pdf") is None
    assert parse_path("高中/英语/重庆大学版-重庆大学出版社/mergePDFs.exe") is None


EDITIONS = [{"stage": "jh", "code": "yl", "name": "译林版", "publisher": "译林出版社",
             "dir": "译林版-译林出版社", "parser": "generic"}]


def blob(path, size=10):
    return {"type": "blob", "path": path, "size": size}


def test_build_manifest_joins_parts_in_order():
    base = "初中/英语/译林版-译林出版社/七年级/义务教育教科书·英语七年级上册.pdf_merge_folder/义务教育教科书·英语七年级上册.pdf"
    tree = [blob(base + ".2", 5), blob(base + ".1", 7), blob("初中/英语/其它版/x七年级上册.pdf")]
    [book] = build_manifest(tree, EDITIONS)
    assert book["id"] == "jh-yl-7a"
    assert [p["path"][-1] for p in book["parts"]] == ["1", "2"]
    assert book["size"] == 12


def test_build_manifest_rejects_gap_in_parts():
    base = "初中/英语/译林版-译林出版社/七年级/X七年级上册.pdf"
    with pytest.raises(ValueError, match="分卷不连续"):
        build_manifest([blob(base + ".1"), blob(base + ".3")], EDITIONS)
