import json

import pytest

from aikit import stats as ss
from game.session import stats_key
from game.ui import settings as st


def test_defaults_when_there_is_no_file(tmp_path):
    s = st.Settings.load(tmp_path / "none.json")
    assert s == st.Settings()
    assert s.delay_ms == 450 and s.first == "me" and not s.show_thoughts


def test_settings_round_trip(tmp_path):
    path = tmp_path / "settings.json"
    s = st.Settings(delay_ms=900, show_thoughts=True, first="alternate",
                    size=5, level="novice")
    s.save(path)
    assert st.Settings.load(path) == s


@pytest.mark.parametrize("text", ["", "{", "[1, 2]", "null", "\x00\xff", '{"volume": "громко"}'])
def test_broken_settings_file_gives_defaults(tmp_path, text):
    path = tmp_path / "settings.json"
    path.write_bytes(text.encode("utf-8", "surrogateescape") if isinstance(text, str) else text)
    s = st.Settings.load(path)
    assert s == st.Settings()


def test_each_bad_field_falls_back_alone(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"volume": 500, "theme": "pink", "delay_ms": -3, "show_thoughts": "да",
                                "first": "cat", "size": 4, "level": 7, "extra": 1}), encoding="utf-8")
    s = st.Settings.load(path)
    assert s == st.Settings()
    path.write_text(json.dumps({"delay_ms": 300, "first": "cat"}), encoding="utf-8")
    s = st.Settings.load(path)
    assert s.delay_ms == 300 and s.first == "me"


def test_settings_of_1_0_with_theme_and_volume_are_read(tmp_path):
    """Тема и громкость теперь в ctx; файл прежней версии читается, своё из него не теряется."""
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"volume": 30, "theme": "light", "delay_ms": 0, "show_thoughts": True,
                                "first": "net", "size": 5, "level": "medium"}), encoding="utf-8")
    s = st.Settings.load(path)
    assert (s.delay_ms, s.show_thoughts, s.first, s.size, s.level) == (0, True, "net", 5, "medium")


def test_settings_file_is_written_whole(tmp_path):
    path = tmp_path / "deep" / "settings.json"
    st.Settings(delay_ms=100).save(path)
    assert json.loads(path.read_text(encoding="utf-8"))["delay_ms"] == 100
    assert not (tmp_path / "deep" / "settings.json.tmp").exists()


def test_stats_count_wins_losses_draws_by_field_and_level(tmp_path):
    s = ss.Stats()
    s.record(stats_key(3, "strong"), "win")
    s.record(stats_key(3, "strong"), "loss")
    s.record(stats_key(3, "strong"), "draw")
    s.record(stats_key(5, "novice"), "win")
    e = s.entry(stats_key(3, "strong"))
    assert (e["games"], e["wins"], e["losses"], e["draws"]) == (3, 1, 1, 1)
    assert s.entry(stats_key(5, "novice"))["wins"] == 1
    assert s.entry(stats_key(5, "strong"))["games"] == 0
    assert s.totals()["games"] == 4


def test_win_streak_and_best_streak():
    s = ss.Stats()
    for r in ["win", "win", "win", "draw", "win"]:
        s.record(stats_key(3, "medium"), r)
    e = s.entry(stats_key(3, "medium"))
    assert e["streak"] == 1 and e["best_streak"] == 3
    s.record(stats_key(3, "medium"), "loss")
    assert s.entry(stats_key(3, "medium"))["streak"] == 0


def test_stats_round_trip(tmp_path):
    path = tmp_path / "stats.json"
    s = ss.Stats(path)
    s.record(stats_key(5, "strong"), "draw")          # пишется сразу
    back = ss.Stats(path)
    assert back.entry(stats_key(5, "strong")) == s.entry(stats_key(5, "strong"))


@pytest.mark.parametrize("text", ["", "{{", "[]", '{"3x3/strong": "много"}',
                                  '{"3x3/strong": {"games": -5, "wins": "x"}}'])
def test_broken_stats_file_gives_empty_stats(tmp_path, text):
    path = tmp_path / "stats.json"
    path.write_text(text, encoding="utf-8")
    s = ss.Stats(path)
    assert s.entry(stats_key(3, "strong"))["games"] == 0
    s.record(stats_key(3, "strong"), "win")          # и дальше пишется как ни в чём не бывало
    assert ss.Stats(path).entry(stats_key(3, "strong"))["wins"] == 1


def test_stats_file_of_1_0_is_read_as_is(tmp_path):
    """Статистика 1.0.x - тот же файл: ключ «3x3/strong», те же поля."""
    path = tmp_path / "stats.json"
    e = {"games": 4, "wins": 2, "losses": 1, "draws": 1, "streak": 0, "best_streak": 2}
    path.write_text(json.dumps({"3x3/strong": e, "5x5/novice": e}), encoding="utf-8")
    s = ss.Stats(path)
    assert s.entry(stats_key(3, "strong")) == e and s.totals()["games"] == 8


def test_unknown_result_is_refused():
    with pytest.raises(ValueError):
        ss.Stats().record(stats_key(3, "strong"), "победа")
