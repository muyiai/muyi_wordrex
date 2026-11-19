from tw.build import fnv1a
from tw.enrich import ecdict_ipa, ecdict_senses, lookup_keys


def test_fnv1a_reference_vectors():
    # 标准 FNV-1a 32 位测试向量；miniprogram/lib/hash.ts 用同样的向量测
    assert fnv1a("") == 0x811C9DC5
    assert fnv1a("a") == 0xE40C292C
    assert fnv1a("foobar") == 0xBF9CF968


def test_ecdict_ipa():
    assert ecdict_ipa("'ɑ:ftә'nu:n") == "/ˈɑːftəˈnuːn/"
    assert ecdict_ipa("'sku:lbæ^") == "/ˈskuːlbæɡ/"
    assert ecdict_ipa("") == ""


def test_ecdict_senses_drops_web_lines():
    assert ecdict_senses("n. 午后, 下午\\n[网络] 下午好") == [{"pos": "n.", "zh": "午后；下午"}]
    assert ecdict_senses("vt. & vi. 登记") == [{"pos": "vt. & vi.", "zh": "登记"}]


def test_lookup_keys_simplifies_textbook_phrases():
    assert "sign up" in lookup_keys("sign up (for sth)")
    assert "ask sb for" in lookup_keys("ask ... for")
    assert "even if" in lookup_keys("even if/though")
