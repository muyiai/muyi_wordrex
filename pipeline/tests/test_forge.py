import pytest

from tw import forge
from tw.enrich import build_entry


def test_aid_stable_unique_and_url_safe():
    a = forge.aid_of("telephone/phone_number")
    assert a == forge.aid_of("telephone/phone_number")
    assert a.startswith("tw-telephone-phone-number-")
    assert forge.aid_of("can't_wait") != forge.aid_of("cant_wait")  # 规整后同名的词靠哈希区分
    assert all(c.isalnum() or c == "-" for c in forge.aid_of("You're welcome!"))


ITEM = {"word": "look forward to", "kind": "phrase", "stage": "jh"}


@pytest.mark.parametrize("sentence, ok", [
    ("We are looking forward to the trip.", True),  # 屈折变化
    ("I look forward to seeing you.", True),
    ("We want to see you soon.", False),
])
def test_uses_item(sentence, ok):
    assert forge.uses_item(sentence, ITEM) is ok


def test_uses_item_ignores_placeholders():
    assert forge.uses_item("Please take care of your sister.", {"word": "take care of sb", "kind": "phrase"})


def entry(**patch):
    e = {"w": "look forward to", "senses": [{"pos": "phr.", "zh": "期待"}], "scene": "a girl at a window",
         "ex": [{"en": "I look forward to the holiday.", "zh": "我盼着放假。"},
                {"en": "Students look forward to the sports meeting every year.", "zh": "学生们每年都期待运动会。"}]}
    return {**e, **patch}


def test_check_entry_accepts_complete_entry():
    forge.check_entry(entry(), ITEM)


@pytest.mark.parametrize("patch", [{"scene": ""}, {"ex": [{"en": "I look forward to it.", "zh": "期待。"}]},
                                   {"ex": [{"en": "See you soon.", "zh": "回头见。"}, {"en": "x", "zh": "y"}]}])
def test_check_entry_rejects_bad_entries(patch):
    with pytest.raises(ValueError):
        forge.check_entry(entry(**patch), ITEM)


def test_system_prompt_has_stage_rules():
    prompt = forge.system_prompt()
    assert "stage ps" in prompt and "4-8 words" in prompt
    assert "[TOPICS]" not in prompt and "[EXAMPLES]" not in prompt


def test_enrich_uses_generated_entry_only_without_atlas():
    occ = {"hw": "look forward to", "kind": "phrase", "senses": [{"pos": "", "zh": "期待"}], "ipa": ""}
    g = {**entry(), "aid": "tw-look-forward-to-abc123", "m": 1 | 2, "uk": "/lʊk ˈfɔːwəd tə/", "us": ""}
    e = build_entry("look_forward_to", occ, atlas={}, ecdict={}, forged={"look_forward_to": g})
    assert e["src"] == "gen" and e["aid"] == g["aid"] and e["m"] == 3 and e["ex"] == g["ex"]
    # 词光有的词不用生成的
    atlas = {"look forward to": {**g, "id": "look-forward-to", "cefr": "B1", "topic": "daily", "col": [], "fam": [],
                                 "syn": [], "ant": [], "tip": ""}}
    assert build_entry("look_forward_to", occ, atlas, {}, {"look_forward_to": g})["src"] == "atlas"
