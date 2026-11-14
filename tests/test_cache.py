from pathlib import Path

from niyam.models.cache import ResponseCache, cache_key


def test_key_is_stable_across_dict_ordering() -> None:
    a = cache_key("gemini", "m", "v1", {"state": "s", "questions": {"a": "x", "b": "y"}})
    b = cache_key("gemini", "m", "v1", {"questions": {"b": "y", "a": "x"}, "state": "s"})
    assert a == b


def test_key_changes_with_every_component() -> None:
    base = cache_key("gemini", "m", "v1", {"q": 1})
    assert base != cache_key("other", "m", "v1", {"q": 1})
    assert base != cache_key("gemini", "m2", "v1", {"q": 1})
    assert base != cache_key("gemini", "m", "v2", {"q": 1})
    assert base != cache_key("gemini", "m", "v1", {"q": 2})


def test_round_trip_and_persistence(tmp_path: Path) -> None:
    path = tmp_path / "cache.sqlite"
    cache = ResponseCache(path)
    assert cache.get("k") is None
    cache.put("k", {"probabilities": {"a": 0.5}, "text": "₹2,00,000"})
    cache.close()

    reopened = ResponseCache(path)
    assert reopened.get("k") == {"probabilities": {"a": 0.5}, "text": "₹2,00,000"}
    reopened.close()
