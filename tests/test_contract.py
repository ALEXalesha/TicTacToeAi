"""Вход игры по контракту PythonAiGames: GAME_INFO и create_widget(ctx) без окна.

Виджет создаётся так, как его создаёт оболочка AiGameRoom: aikit.Context с папкой данных,
темой и языком; тема и язык меняются на лету; pause/resume/shutdown; файлы - только в
ctx.data_dir. Окна - только offscreen.
"""
import json
import os
import re
import time

import numpy as np
import pytest
from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QAbstractButton, QComboBox, QLabel, QMainWindow, QTableWidget, QWidget

import game
import main
from aikit.host import Context
from game.ui import i18n, theme
from game.version import VERSION

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CYRILLIC = re.compile("[А-Яа-яЁё]")


def pump(until, timeout=5000):
    waited = 0
    while not until() and waited < timeout:
        QTest.qWait(5)
        waited += 5
    return until()


@pytest.fixture
def ctx(tmp_path):
    return Context(tmp_path / "data", "dark", "ru", 0)


@pytest.fixture
def gw(qapp, ctx):
    w = game.create_widget(ctx)
    w.change_setting("delay_ms", 0)
    w.resize(1180, 780)
    w.show()
    yield w
    w.shutdown()
    w.close()


# --- GAME_INFO ---


def test_game_info_is_complete_in_both_languages():
    info = game.GAME_INFO
    assert info["id"] == "tictactoe"
    assert info["version"] == VERSION
    for key in ("title", "summary"):
        assert set(info[key]) == {"ru", "en"} and all(v.strip() for v in info[key].values())
    assert not CYRILLIC.search(info["title"]["en"] + info["summary"]["en"])
    assert os.path.isfile(os.path.join(ROOT, info["preview"]))
    assert "langs" not in info or set(info["langs"]) == {"ru", "en"}


def test_importing_the_game_does_not_load_qt():
    """Правила, сеть и обучение работают без Qt: game/__init__ его не тянет."""
    import subprocess
    import sys
    code = "import sys, game; import game.core.rules, game.ai.net, game.ai.models; print('PySide6' in sys.modules)"
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert r.stdout.strip() == "False", r.stderr


# --- виджет ---


def test_create_widget_gives_a_plain_widget_not_a_window(gw):
    assert isinstance(gw, QWidget) and not isinstance(gw, QMainWindow)
    assert gw.parent() is None and gw.current_page() == "menu"
    # «Выход» во вкладке оболочки не нужен: её закрывает крестик вкладки
    assert not gw.menu.quit_button.isVisible()


def test_standalone_window_shows_quit_and_it_closes_the_window(qapp):
    window, _ = main.open_window()
    window.show()
    quit_button = window.game.menu.quit_button
    assert quit_button.isVisible()
    quit_button.click()
    assert not window.isVisible()


def test_theme_changes_on_the_fly(gw, ctx):
    ctx.set_theme("light")
    assert theme.palette("light")["bg"] in gw.styleSheet()
    assert gw.game.board_widget.colors == theme.palette("light")
    assert gw.settings_page.theme_combo.currentData() == "light"
    corner = gw.grab().toImage().pixelColor(3, gw.height() - 3)
    assert corner.name() == theme.palette("light")["bg"]
    ctx.set_theme("dark")
    assert theme.palette("dark")["bg"] in gw.styleSheet()


def visible_texts(widget):
    out = []
    for w in widget.findChildren(QLabel) + widget.findChildren(QAbstractButton):
        if w.isVisible() and w.text():
            out.append(w.text())
    for combo in widget.findChildren(QComboBox):
        out += [combo.itemText(i) for i in range(combo.count())]
    for t in widget.findChildren(QTableWidget):
        out += [t.horizontalHeaderItem(c).text() for c in range(t.columnCount()) if not t.isColumnHidden(c)]
        out += [t.item(r, c).text() for r in range(t.rowCount()) for c in range(t.columnCount())
                if t.item(r, c) and not t.isColumnHidden(c)]
    return out


def test_language_changes_on_the_fly_and_every_page_is_english(gw, ctx):
    ctx.set_lang("en")
    assert gw.menu.play_button.text() == "Play"
    for name in ("menu", "game", "stats", "settings"):
        gw.show_page(name)
        QTest.qWait(10)
        russian = [t for t in visible_texts(gw) if CYRILLIC.search(t) and t != i18n.LANG_NAMES["ru"]]
        assert russian == [], (name, russian)
    ctx.set_lang("ru")
    assert gw.menu.play_button.text() == "Играть"
    gw.show_page("game")
    assert gw.game.status.text() in ("Ваш ход", "Сеть думает…")


def test_both_languages_have_the_same_strings():
    assert set(i18n.RU) == set(i18n.EN)
    assert [k for k, v in i18n.EN.items() if CYRILLIC.search(v)] == []
    assert i18n.translator("en").missing() == {}


@pytest.mark.parametrize("lang,n,word", [("ru", 1, "партия"), ("ru", 3, "партии"), ("ru", 11, "партий"),
                                         ("ru", 22, "партии"), ("en", 1, "game"), ("en", 2, "games")])
def test_word_for_number_of_games(lang, n, word):
    assert i18n.translator(lang)(i18n.plural_key(n, lang)) == word


def test_numbers_are_grouped_by_language():
    assert i18n.number(30000, "ru") == "30 000"
    assert i18n.number(30000, "en") == "30,000"


def test_settings_page_sends_theme_language_and_volume_to_ctx(gw, ctx):
    page = gw.settings_page
    page.theme_combo.setCurrentIndex(1)
    page.lang_combo.setCurrentIndex(1)
    page.volume.setValue(40)
    assert (ctx.theme, ctx.lang, ctx.sound.volume) == ("light", "en", 40)
    assert gw.sounds.volume == 40


def test_volume_changed_by_the_host_reaches_the_game_sounds(gw, ctx):
    ctx.set_volume(55)                  # громкость оболочки меняется без сигнала
    gw.play_sound("x")
    assert gw.sounds.volume == 55


# --- pause / resume / shutdown ---


def net_to_move(gw, delay):
    gw.change_setting("delay_ms", delay)
    gw.show_page("game")
    gw.game.set_first("net")            # сеть ходит первой - ход ждёт в таймере


def test_pause_cancels_the_waiting_net_move_and_resume_brings_it_back(gw):
    net_to_move(gw, 50)
    gw.pause()
    QTest.qWait(200)
    assert np.count_nonzero(gw.game.session.board) == 0
    gw.game.again()                     # и новая партия, пока вкладка скрыта, не будит сеть
    QTest.qWait(200)
    assert np.count_nonzero(gw.game.session.board) == 0
    gw.resume()
    assert pump(lambda: np.count_nonzero(gw.game.session.board) == 1)


def test_resume_on_another_page_does_not_start_a_move(gw):
    net_to_move(gw, 0)
    assert pump(lambda: np.count_nonzero(gw.game.session.board) == 1)
    gw.game.again()
    gw.show_page("menu")
    gw.pause()
    gw.resume()
    QTest.qWait(100)
    assert np.count_nonzero(gw.game.session.board) == 0


def test_shutdown_is_quick_stops_the_net_and_saves_settings(gw, ctx):
    net_to_move(gw, 100)
    gw.settings.show_thoughts = True    # не сохранено - shutdown сохранит
    started = time.perf_counter()
    assert gw.shutdown() is True
    assert time.perf_counter() - started < 2.0
    QTest.qWait(300)
    assert np.count_nonzero(gw.game.session.board) == 0
    saved = json.loads(open(os.path.join(ctx.data_dir, "settings.json"), encoding="utf-8").read())
    assert saved["show_thoughts"] is True
    assert [t for t in gw.findChildren(QTimer) if t.isActive()] == []


# --- файлы только в ctx.data_dir ---


def snapshot(top):
    out = {}
    for folder, dirs, files in os.walk(top):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git", ".pytest_cache", "build", "dist")]
        for name in files:
            path = os.path.join(folder, name)
            out[path] = os.path.getmtime(path)
    return out


def test_game_writes_only_into_ctx_data_dir(qapp, ctx, monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    before = snapshot(ROOT)
    w = game.create_widget(ctx)
    w.change_setting("delay_ms", 0)
    w.show_page("game")
    w.game.set_first("me")
    s = w.game.session
    while s.result is None:
        if s.human_turn():
            w.game.on_cell(*[int(v) for v in np.argwhere(s.board == 0)[0]])
        else:
            w.game.net_turn(w.game.token)
    ctx.set_theme("light")
    ctx.set_lang("en")
    w.shutdown()
    w.close()
    after = snapshot(ROOT)
    assert sorted(p for p, m in after.items() if before.get(p) != m) == []
    names = set(os.listdir(ctx.data_dir))
    assert {"settings.json", "stats.json"} <= names
    assert not (tmp_path / "local").exists() and not (tmp_path / "roaming").exists()
    stats = json.loads(open(os.path.join(ctx.data_dir, "stats.json"), encoding="utf-8").read())
    assert stats["3x3/strong"]["games"] == 1


# --- перенос данных 1.0.x в окне отдельного запуска ---


def test_data_of_1_0_is_copied_into_the_contract_layout(tmp_path):
    old, root = tmp_path / "old", tmp_path / "root"
    old.mkdir()
    entry = {"games": 2, "wins": 1, "losses": 1, "draws": 0, "streak": 0, "best_streak": 1}
    (old / "settings.json").write_text(json.dumps({"volume": 25, "theme": "light", "delay_ms": 0,
                                                   "first": "net"}), encoding="utf-8")
    (old / "stats.json").write_text(json.dumps({"5x5/medium": entry}), encoding="utf-8")
    (old / "window.json").write_text(json.dumps({"x": 1, "y": 2, "width": 900, "height": 650}), encoding="utf-8")
    done = main.migrate(str(old), str(root), str(root / "tictactoe"))
    assert sorted(done) == ["host.json", "settings.json", "stats.json", "window.json"]
    host = json.loads((root / "host.json").read_text(encoding="utf-8"))
    assert host["theme"] == "light" and host["volume"] == 25
    assert json.loads((root / "tictactoe" / "stats.json").read_text(encoding="utf-8"))["5x5/medium"] == entry
    assert (old / "settings.json").exists() and (old / "stats.json").exists()      # копия, не перенос
    # второй раз ничего не перезаписывает
    (root / "tictactoe" / "stats.json").write_text("{}", encoding="utf-8")
    assert main.migrate(str(old), str(root), str(root / "tictactoe")) == []
    assert (root / "tictactoe" / "stats.json").read_text(encoding="utf-8") == "{}"


def test_old_data_dir_is_where_1_0_kept_it(tmp_path):
    env = {"LOCALAPPDATA": str(tmp_path / "lad")}
    assert main.old_data_dir(False, "python.exe", env) == str(tmp_path / "lad" / "TicTacToeAi")
    exe = tmp_path / "app" / "TicTacToeAi.exe"
    exe.parent.mkdir()
    (exe.parent / "portable.txt").write_text("x", encoding="utf-8")
    assert main.old_data_dir(True, str(exe), env) == str(exe.parent / "saves")
    assert main.old_data_dir(False, "python.exe", {**env, "TICTACTOEAI_HOME": "X"}) == "X"


def test_standalone_window_reads_settings_and_stats_of_1_0(qapp, tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("TICTACTOEAI_HOME", str(home))
    entry = {"games": 7, "wins": 7, "losses": 0, "draws": 0, "streak": 7, "best_streak": 7}
    (home / "settings.json").write_text(json.dumps({"theme": "light", "size": 5}), encoding="utf-8")
    (home / "stats.json").write_text(json.dumps({"5x5/strong": entry}), encoding="utf-8")
    window, ctx = main.open_window()
    assert ctx.theme == "light" and window.game.settings.size == 5
    assert window.game.stats.entry("5x5/strong") == entry
    window.close()
