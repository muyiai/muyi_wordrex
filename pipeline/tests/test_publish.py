import json

from tw import publish


def test_changed_lists_new_and_modified_files(tmp_path):
    old = tmp_path / "old.json"
    new = tmp_path / "new.json"
    old.write_text(json.dumps({"a": {"sha1": "1", "size": 1}, "b": {"sha1": "2", "size": 1}}))
    new.write_text(json.dumps({"a": {"sha1": "1", "size": 1}, "b": {"sha1": "3", "size": 1}, "c": {"sha1": "4", "size": 1}}))
    assert publish.changed(old, new) == ["b", "c"]
    assert publish.changed(tmp_path / "missing.json", new) == ["a", "b", "c"]  # 第一次上传：全部
