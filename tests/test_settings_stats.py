import json

import pytest

from game import settings as st
from game import stats as ss


def test_defaults_when_there_is_no_file(tmp_path):
    s = st.Settings.load(tmp_path / "none.json")
    assert s == st.Settings()
    assert s.theme == "dark" and s.first == "me" and not s.show_thoughts


def test_settings_round_trip(tmp_path):
    path = tmp_path / "settings.json"
    s = st.Settings(volume=15, theme="light", delay_ms=900, show_thoughts=True, first="alternate",
                    size=5, level="novice")
    s.save(path)
    assert st.Settings.load(path) == s


@pytest.mark.parametrize("text", ["", "{", "[1, 2]", "null", "\x00\xff", '{"volume": "громко"}'])
def test_broken_settings_file_gives_defaults(tmp_path, text):
    path = tmp_path / "settings.json"
    path.write_bytes(text.encode("utf-8", "surrogateescape") if isinstance(text, str) else text)
    s = st.Settings.load(path)
    assert s.theme == "dark" and s.volume == st.Settings().volume


def test_each_bad_field_falls_back_alone(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"volume": 500, "theme": "pink", "delay_ms": -3, "show_thoughts": "да",
                                "first": "cat", "size": 4, "level": 7, "extra": 1}), encoding="utf-8")
    s = st.Settings.load(path)
    assert s == st.Settings()
    path.write_text(json.dumps({"volume": 30, "theme": "pink"}), encoding="utf-8")
    s = st.Settings.load(path)
    assert s.volume == 30 and s.theme == "dark"


def test_settings_file_is_written_whole(tmp_path):
    path = tmp_path / "deep" / "settings.json"
    st.Settings(volume=1).save(path)
    assert json.loads(path.read_text(encoding="utf-8"))["volume"] == 1
    assert not (tmp_path / "deep" / "settings.json.tmp").exists()


def test_stats_count_wins_losses_draws_by_field_and_level(tmp_path):
    s = ss.Stats()
    s.record(3, "strong", "win")
    s.record(3, "strong", "loss")
    s.record(3, "strong", "draw")
    s.record(5, "novice", "win")
    e = s.entry(3, "strong")
    assert (e["games"], e["wins"], e["losses"], e["draws"]) == (3, 1, 1, 1)
    assert s.entry(5, "novice")["wins"] == 1
    assert s.entry(5, "strong")["games"] == 0
    assert s.totals()["games"] == 4


def test_win_streak_and_best_streak():
    s = ss.Stats()
    for r in ["win", "win", "win", "draw", "win"]:
        s.record(3, "medium", r)
    e = s.entry(3, "medium")
    assert e["streak"] == 1 and e["best_streak"] == 3
    s.record(3, "medium", "loss")
    assert s.entry(3, "medium")["streak"] == 0


def test_stats_round_trip(tmp_path):
    path = tmp_path / "stats.json"
    s = ss.Stats()
    s.record(5, "strong", "draw")
    s.save(path)
    back = ss.Stats.load(path)
    assert back.entry(5, "strong") == s.entry(5, "strong")


@pytest.mark.parametrize("text", ["", "{{", "[]", '{"3x3/strong": "много"}',
                                  '{"3x3/strong": {"games": -5, "wins": "x"}}'])
def test_broken_stats_file_gives_empty_stats(tmp_path, text):
    path = tmp_path / "stats.json"
    path.write_text(text, encoding="utf-8")
    s = ss.Stats.load(path)
    assert s.entry(3, "strong")["games"] == 0
    s.record(3, "strong", "win")          # и дальше пишется как ни в чём не бывало
    s.save(path)
    assert ss.Stats.load(path).entry(3, "strong")["wins"] == 1


def test_unknown_result_is_refused():
    with pytest.raises(ValueError):
        ss.Stats().record(3, "strong", "победа")
