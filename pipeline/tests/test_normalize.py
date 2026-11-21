import pytest

from tw.normalize import classify, make_id, repair, split_note


@pytest.mark.parametrize("raw, fixed", [
    ("afernoon", "afternoon"),  # ft 连字丢字
    ("afer", "after"),  # ECDICT 里有无词频的杂条 afer，不能算认识
    ("twelfh", "twelfth"),
    ("Tursday", "Thursday"),  # Th 连字
    ("are", "are"),  # 屈折形式在 ECDICT 里没有词频，不能被「修」成 area
    ("based", "based"),
    ("sign up (for sth)", "sign up (for sth)"),  # 占位词 sth
    ("the Andes", "the Andes"),  # 专名
    ("schoolbag", "schoolbag"),  # 词典没收的真词：找不到够常用的候选就不动
])
def test_repair(raw, fixed):
    assert repair(raw) == fixed


@pytest.mark.parametrize("hw, senses, kind", [
    ("Gina", [{"pos": "", "zh": "吉娜（女名）"}], "name"),
    ("CCTV", [{"pos": "", "zh": "中国中央电视台"}], "abbr"),
    ("Ms.", [{"pos": "", "zh": "女士"}], "abbr"),
    ("p.m.", [{"pos": "abbr.", "zh": "下午"}], "abbr"),
    ("Machu Picchu", [{"pos": "", "zh": "马丘比丘"}], "proper"),
    ("the Andes", [{"pos": "", "zh": "安第斯山脉"}], "proper"),
    ("ID card", [{"pos": "", "zh": "身份证"}], "phrase"),
    ("How old ...?", [{"pos": "", "zh": "多大年纪？"}], "phrase"),
    ("Chinese", [{"pos": "n.", "zh": "汉语"}], "word"),
    ("pencil box", [{"pos": "", "zh": "铅笔盒"}], "phrase"),
])
def test_classify(hw, senses, kind):
    assert classify(hw, senses) == kind


@pytest.mark.parametrize("hw, wid", [
    ("Good morning!", "good_morning"),
    ("How old ...?……", "how_old"),
    ("Mr.", "mr"),
    ("pencil box", "pencil_box"),
    ("telephone/phone number", "telephone/phone_number"),
])
def test_make_id(hw, wid):
    assert make_id(hw) == wid


@pytest.mark.parametrize("raw, fixed", [
    ("nextto", "next to"),  # 空格丢了的短语
    ("boildownto", "boil down to"),
    ("putsthinplace", "put sth in place"),  # 占位词优先
    ("threestrikesandyouareout", "three strikes and you are out"),  # 屈折形式按原形算词频
    ("pencilbox", "pencil box"),
    ("cannot", "cannot"),  # ECDICT 收了的真词不拆
    ("triathlete", "triathlete"),  # 不拆成 tri athlete
])
def test_repair_segments_merged_phrases(raw, fixed):
    assert repair(raw) == fixed


@pytest.mark.parametrize("raw, hw", [
    ("burned)", "burned"),
    ("compare.with", "compare ... with"),
    ("try⋯on", "try ... on"),
    ("undergroundYAndegraund", "underground"),  # 粘上的 OCR 音标
    ("decade'dekerd", "decade"),
    ("one's", "one's"),
    ("o'clock", "o'clock"),
    ("p.m.", "p.m."),
])
def test_split_note_cleanup(raw, hw):
    assert split_note(raw)[0] == hw
