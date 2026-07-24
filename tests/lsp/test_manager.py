from pathlib import Path

from nexcoder.lsp.manager import (
    LANGUAGE_FAMILIES, apply_text_edits, path_to_uri, uri_to_path,
)


def test_uri_round_trip(tmp_path):
    target = tmp_path / "src" / "app.py"
    target.parent.mkdir()
    target.write_text("x = 1", encoding="utf-8")
    uri = path_to_uri(target)
    assert uri.startswith("file:///")
    assert Path(uri_to_path(uri)) == target.resolve()


def test_language_families_cover_core_languages():
    for language in ("python", "typescript", "javascript", "html",
                     "css", "json"):
        assert language in LANGUAGE_FAMILIES


def test_apply_text_edits_single_replacement():
    text = "def greet(name):\n    return name\n"
    edits = [{"range": {"start": {"line": 0, "character": 4},
                        "end": {"line": 0, "character": 9}},
              "newText": "salute"}]
    out = apply_text_edits(text, edits)
    assert out == "def salute(name):\n    return name\n"


def test_apply_text_edits_multiple_reverse_safe():
    text = "aaa bbb aaa\n"
    edits = [
        {"range": {"start": {"line": 0, "character": 0},
                   "end": {"line": 0, "character": 3}}, "newText": "xxxx"},
        {"range": {"start": {"line": 0, "character": 8},
                   "end": {"line": 0, "character": 11}}, "newText": "yy"},
    ]
    out = apply_text_edits(text, edits)
    assert out == "xxxx bbb yy\n"


def test_apply_text_edits_multiline_range():
    text = "line one\nline two\nline three\n"
    edits = [{"range": {"start": {"line": 0, "character": 5},
                        "end": {"line": 2, "character": 5}},
              "newText": "X"}]
    assert apply_text_edits(text, edits) == "line Xthree\n"


def test_apply_text_edits_out_of_bounds_is_clamped():
    text = "short\n"
    edits = [{"range": {"start": {"line": 9, "character": 0},
                        "end": {"line": 9, "character": 5}},
              "newText": "tail"}]
    assert apply_text_edits(text, edits) == "short\ntail"
