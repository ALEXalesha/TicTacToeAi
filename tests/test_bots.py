import numpy as np
import pytest

from core import bots, rules
from tests.test_rules import board_from


def test_random_bot_moves_only_into_empty_cells():
    bot = bots.RandomBot(np.random.default_rng(0))
    b = board_from("XOX/O.X/OX.")
    for _ in range(30):
        assert bot.move(b) in [(1, 1), (2, 2)]


def test_win_or_block_takes_the_win_first():
    bot = bots.WinOrBlockBot(np.random.default_rng(0))
    # ход X: X может выиграть в (0, 2), O грозит в (1, 2)
    b = board_from("XX./OO./...")
    assert bot.move(b) == (0, 2)


def test_win_or_block_blocks_the_threat():
    bot = bots.WinOrBlockBot(np.random.default_rng(0))
    # ход O: выигрыша нет, X грозит в (0, 2)
    b = board_from("XX./O../...")
    assert bot.move(b) == (0, 2)


def test_win_or_block_on_5x5_blocks_four():
    bot = bots.WinOrBlockBot(np.random.default_rng(0))
    b = board_from("XXX../OO.../...../...../.....")
    # ход O: у O нет четвёрки, X грозит в (0, 3)
    assert bot.move(b) == (0, 3)


def test_minimax_finds_the_winning_move():
    bot = bots.MinimaxBot(np.random.default_rng(0))
    b = board_from("XX./OO./...")
    assert bot.move(b) == (0, 2)


def test_minimax_against_itself_is_always_a_draw():
    rng = np.random.default_rng(1)
    for _ in range(20):
        result, _ = bots.play_game(bots.MinimaxBot(rng), bots.MinimaxBot(rng), 3)
        assert result == 0


def test_minimax_never_loses_to_random():
    rng = np.random.default_rng(2)
    res = bots.match(bots.MinimaxBot(rng), bots.RandomBot(rng), 3, games=60)
    assert res["losses"] == 0
    assert res["wins"] > 40


def test_minimax_refuses_bigger_fields():
    with pytest.raises(ValueError):
        bots.MinimaxBot(np.random.default_rng(0)).move(rules.new_board(5))


def test_play_game_returns_legal_move_list():
    rng = np.random.default_rng(3)
    result, moves = bots.play_game(bots.RandomBot(rng), bots.RandomBot(rng), 5)
    b = rules.new_board(5)
    for cell in moves:
        b = rules.play(b, cell)
    assert rules.outcome(b) == result


def test_match_counts_every_game_and_splits_colors():
    rng = np.random.default_rng(4)
    res = bots.match(bots.RandomBot(rng), bots.RandomBot(rng), 3, games=40)
    assert res["wins"] + res["losses"] + res["draws"] == 40
    assert res["games_as_x"] == 20 and res["games_as_o"] == 20


def test_match_only_as_x():
    rng = np.random.default_rng(5)
    res = bots.match(bots.RandomBot(rng), bots.RandomBot(rng), 3, games=10, colors="x")
    assert res["games_as_x"] == 10 and res["games_as_o"] == 0
