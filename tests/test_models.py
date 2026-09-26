"""Обученные модели из models/: пороги из п. 4 спецификации и честность паспортов.

Проверки пересчитываются заново теми же функциями и с теми же сидами, что в конце
обучения, и должны совпасть с паспортом до партии."""
import pytest

from core import rules
from game import models
from train import selfplay

LEVELS = ("novice", "medium", "strong")


def level(size, key):
    return next(lv for lv in models.passport(size)["levels"] if lv["key"] == key)


@pytest.fixture(scope="module")
def rechecked():
    return {(size, key): selfplay.evaluate(models.load(size, key), size, 200, seed=1000 + size)
            for size in (3, 5) for key in LEVELS}


@pytest.mark.parametrize("size", [3, 5])
def test_every_level_loads_and_the_passport_lists_it(size):
    pp = models.passport(size)
    assert [lv["key"] for lv in pp["levels"]] == list(LEVELS)
    for key in LEVELS:
        assert models.load(size, key).n == size
    assert pp["size"] == size and pp["win_length"] == rules.win_length(size)
    assert len(pp["curve"]) >= 10


@pytest.mark.parametrize("size", [3, 5])
@pytest.mark.parametrize("key", LEVELS)
def test_passport_numbers_are_what_the_models_really_do(rechecked, size, key):
    assert rechecked[(size, key)] == level(size, key)["checks"]


def test_3x3_strong_never_loses_to_minimax_in_200_games(rechecked):
    mm = rechecked[(3, "strong")]["vs_minimax"]
    assert mm["games"] == 200 and mm["losses"] == 0


def test_3x3_strong_never_loses_to_anybody():
    # полный перебор всех ходов соперника, а не 200 случайных партий
    m = models.load(3, "strong")
    assert selfplay.worst_case(m, rules.X) >= 0
    assert selfplay.worst_case(m, rules.O) >= 0


def test_3x3_strong_beats_random_moving_first(rechecked):
    first = rechecked[(3, "strong")]["vs_random_first"]
    assert first["games"] == 200 and first["win_rate"] >= 0.95


def test_5x5_strong_beats_random(rechecked):
    r = rechecked[(5, "strong")]["vs_random"]
    assert r["games"] == 200 and r["win_rate"] >= 0.95


def test_5x5_strong_wins_more_than_it_loses_against_win_or_block(rechecked):
    b = rechecked[(5, "strong")]["vs_bot"]
    assert b["games"] == 200 and b["wins"] > b["losses"]


@pytest.mark.parametrize("size", [3, 5])
def test_novice_is_clearly_weaker_than_strong(rechecked, size):
    novice, strong = rechecked[(size, "novice")], rechecked[(size, "strong")]
    assert novice["vs_bot"]["win_rate"] + 0.2 < strong["vs_bot"]["win_rate"] or \
        novice["vs_bot"]["losses"] > strong["vs_bot"]["losses"] + 40
    assert novice["vs_random"]["losses"] > strong["vs_random"]["losses"]


def test_3x3_novice_loses_to_minimax_and_strong_does_not(rechecked):
    assert rechecked[(3, "novice")]["vs_minimax"]["losses"] > 50
    assert rechecked[(3, "strong")]["vs_minimax"]["losses"] == 0
