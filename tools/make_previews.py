"""Кадры экранов для README: docs/preview_*.png (английские - с окончанием _en).

    python tools\\make_previews.py

Окно создаётся offscreen (Qt рисует в память), кадр снимается widget.grab() - без экрана
и без чужих окон поверх. Данные игрока - во временной папке: статистика на кадре взята
из партий бота «выиграй или помешай» против сети, а не из личной статистики.
"""
import os
import sys
import tempfile

os.environ["TICTACTOEAI_HOME"] = tempfile.mkdtemp(prefix="tictactoeai-previews-")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from aikit import offscreen  # noqa: E402

offscreen.setup(force=True)

import numpy as np  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from game.core import bots  # noqa: E402
from main import open_window  # noqa: E402

SIZE = (1100, 720)


def shot(window, name):
    QApplication.processEvents()
    path = os.path.join(ROOT, "docs", f"preview_{name}.png")
    window.grab().save(path)
    print(path)


def bot_plays(gw, size, level, first, stop=None, seed=0):
    """Бот за человека против сети; stop(session) - остановиться посреди партии."""
    game = gw.game
    game.first = first
    game.level = level
    game.size = size
    game.new_session()
    bot = bots.WinOrBlockBot(np.random.default_rng(seed))
    s = game.session
    while s.result is None:
        if stop and stop(s):
            break
        if s.human_turn():
            game.on_cell(*bot.move(s.board))
        else:
            game.net_turn(game.token)
    return s


def main():
    app = QApplication.instance() or QApplication([])
    window, ctx = open_window()
    gw = window.game
    gw.change_setting("delay_ms", 0)
    gw.set_volume(0)
    window.resize(*SIZE)
    window.show()

    # немного партий для статистики - бот против сети разных уровней
    for i, (size, level) in enumerate([(3, "novice"), (3, "novice"), (3, "medium"), (3, "strong"),
                                       (3, "strong"), (5, "novice"), (5, "novice"), (5, "medium"),
                                       (5, "strong"), (5, "strong"), (3, "novice"), (5, "novice")]):
        bot_plays(gw, size, level, "alternate" if i % 2 else "me", seed=i)

    for theme, lang in (("dark", "ru"), ("light", "ru"), ("dark", "en")):
        ctx.set_theme(theme)
        ctx.set_lang(lang)
        suffix = ("" if theme == "dark" else "_light") + ("" if lang == "ru" else "_en")

        gw.show_page("menu")
        shot(window, "menu" + suffix)

        # 3x3 посреди партии, с мыслями сети
        gw.show_page("game")
        gw.change_setting("show_thoughts", True)
        game = gw.game
        game.first, game.level, game.size = "me", "strong", 3
        game.new_session()
        for cell in [(0, 0)]:
            game.on_cell(*cell)
            game.net_turn(game.token)
        shot(window, "thoughts" + suffix)

        # 5x5 до конца: сеть собирает четыре в ряд
        gw.change_setting("show_thoughts", False)
        for seed in range(50):
            s = bot_plays(gw, 5, "strong", "me", seed=100 + seed)
            if s.outcome_for_human() == "loss" and np.count_nonzero(s.board) >= 11:
                break
        shot(window, "game5" + suffix)

        # статистика длиннее окна - кадр с высоким окном, чтобы влезла целиком
        window.resize(SIZE[0], 1130)
        gw.show_page("stats")
        gw.stats_page.set_field(5)
        shot(window, "stats" + suffix)
        window.resize(*SIZE)

        gw.set_volume(70)
        gw.change_setting("delay_ms", 450)
        gw.show_page("settings")
        shot(window, "settings" + suffix)
        gw.set_volume(0)
        gw.change_setting("delay_ms", 0)
    window.close()


if __name__ == "__main__":
    main()
