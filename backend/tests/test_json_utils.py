import pytest

from lumi.llm.json_utils import extract_json


def test_plain_json():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_markdown_fenced_json():
    text = '```json\n{"a": 1, "b": [2, 3]}\n```'
    assert extract_json(text) == {"a": 1, "b": [2, 3]}


def test_json_with_prose_around():
    text = 'Вот результат:\n{"tasks": [{"title": "x"}]}\nНадеюсь, помог!'
    assert extract_json(text) == {"tasks": [{"title": "x"}]}


def test_nested_braces_in_strings():
    text = '{"text": "скобки } внутри { строки", "n": 1}'
    assert extract_json(text) == {"text": "скобки } внутри { строки", "n": 1}


def test_picks_first_valid_object():
    text = 'мусор {не json} а вот {"ok": true} дальше'
    assert extract_json(text) == {"ok": True}


def test_invalid_raises():
    with pytest.raises(ValueError):
        extract_json("совсем не json")


def test_empty_raises():
    with pytest.raises(ValueError):
        extract_json("   ")
