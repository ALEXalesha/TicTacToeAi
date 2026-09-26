import json

import numpy as np
import pytest

from core import bots, net, rules
from train import selfplay


def one_game(outcome_last, moves, backups=None, explored=None):
    """Шаги одной партии из moves ходов: последний ход завершает партию с исходом
    outcome_last для сходившего (1 - победа, 0 - ничья)."""
    backups = backups or [0.0] * moves
    explored = explored or [False] * moves
    steps = []
    for t in range(moves):
        last = t == moves - 1
        steps.append({"games": np.array([0]), "terminal": np.array([last]),
                      "outcome": np.array([outcome_last if last else 0.0]),
                      "backup": np.array([backups[t]]), "explored": np.array([explored[t]])})
    return steps


def flat(targets):
    return [float(t[0]) for t in targets]


def test_monte_carlo_returns_alternate_sign_by_turn():
    # X ходит на шагах 0, 2, 4 и выигрывает; O - на шагах 1, 3
    got = flat(selfplay.lambda_returns(one_game(1.0, 5), 1, lam=1.0, gamma=1.0))
    assert got == [1.0, -1.0, 1.0, -1.0, 1.0]


def test_discount_makes_early_moves_count_less():
    got = flat(selfplay.lambda_returns(one_game(1.0, 3), 1, lam=1.0, gamma=0.9))
    assert got == pytest.approx([0.81, -0.9, 1.0])


def test_draw_gives_zero_everywhere():
    got = flat(selfplay.lambda_returns(one_game(0.0, 9), 1, lam=1.0, gamma=0.9))
    assert got == [0.0] * 9


def test_lambda_zero_is_the_best_reply_backup():
    # backup шага t - оценка лучшего ответа для того, кто ходит на шаге t
    steps = one_game(1.0, 3, backups=[0.0, 0.5, -0.2])
    got = flat(selfplay.lambda_returns(steps, 1, lam=0.0, gamma=1.0))
    assert got == pytest.approx([-0.5, 0.2, 1.0])


def test_exploratory_reply_cuts_the_trace():
    # ответ на шаге 1 был случайным: цель шага 0 - не исход партии, а лучший ответ
    steps = one_game(1.0, 3, backups=[0.0, 0.3, 0.0], explored=[False, True, False])
    got = flat(selfplay.lambda_returns(steps, 1, lam=1.0, gamma=1.0))
    assert got == pytest.approx([-0.3, -1.0, 1.0])


def test_two_games_of_different_length_in_one_batch():
    steps = []
    for t in range(4):
        ids = [0, 1] if t < 3 else [1]
        term = [t == 2, False] if t < 3 else [True]
        out = [1.0 if t == 2 else 0.0, 0.0] if t < 3 else [0.0]
        steps.append({"games": np.array(ids), "terminal": np.array(term), "outcome": np.array(out),
                      "backup": np.zeros(len(ids)), "explored": np.zeros(len(ids), bool)})
    got = selfplay.lambda_returns(steps, 2, lam=1.0, gamma=1.0)
    assert list(got[0]) == [1.0, 0.0]
    assert list(got[1]) == [-1.0, 0.0]


@pytest.mark.parametrize("n", [3, 5])
def test_play_batch_gives_positions_from_the_movers_view(n):
    model = net.ValueNet(n, rng=np.random.default_rng(0))
    boards, targets, info = selfplay.play_batch(model, n, 16, eps=0.3, rng=np.random.default_rng(1))
    assert boards.dtype == np.int8 and boards.shape[1:] == (n, n)
    own = (boards == 1).reshape(len(boards), -1).sum(axis=1)
    opp = (boards == -1).reshape(len(boards), -1).sum(axis=1)
    assert set(np.unique(own - opp)) <= {0, 1}
    assert np.all(np.abs(targets) <= 1.0)
    assert info["x_wins"] + info["o_wins"] + info["draws"] == 16


def test_play_batch_ends_every_game():
    model = net.ValueNet(3, rng=np.random.default_rng(0))
    boards, targets, _ = selfplay.play_batch(model, 3, 8, eps=1.0, rng=np.random.default_rng(2))
    # у каждой завершённой партии последняя позиция - победа сходившего или полное поле
    finals = targets == np.round(targets)
    assert finals.any()
    for b in boards[np.abs(targets) == 1.0]:
        assert rules.winner(b) == 1


def test_augment_gives_8_examples_per_position():
    boards = np.zeros((2, 3, 3), np.int8)
    boards[0, 0, 1] = 1
    b, t = selfplay.augment(boards, np.array([0.5, -0.5], np.float32))
    assert b.shape == (16, 3, 3) and t.shape == (16,)
    assert np.all(t[:8] == 0.5)
    assert len({x.tobytes() for x in b[:8]}) == 4   # клетка на ребре: 4 разных положения


def test_short_training_beats_an_untrained_net_against_random():
    rng = np.random.default_rng(3)
    fresh = net.ValueNet(3, rng=np.random.default_rng(4))
    before = bots.match(net.NetPlayer(fresh), bots.RandomBot(rng), 3, games=200)
    trained, _ = selfplay.train(3, games=2500, seed=4, snapshots={}, eval_every=0, log=None)
    after = bots.match(net.NetPlayer(trained), bots.RandomBot(np.random.default_rng(3)), 3, games=200)
    assert after["wins"] - after["losses"] > before["wins"] - before["losses"] + 40


def test_train_writes_levels_and_passport(tmp_path):
    model, passport = selfplay.train(3, games=400, seed=1, snapshots={"novice": 100, "medium": 200},
                                     eval_every=200, eval_games=20, final_games=20,
                                     out_dir=tmp_path, log=None)
    saved = json.loads((tmp_path / "3x3.json").read_text(encoding="utf-8"))
    assert saved == json.loads(json.dumps(passport))
    assert [lv["key"] for lv in saved["levels"]] == ["novice", "medium", "strong"]
    for lv in saved["levels"]:
        assert (tmp_path / lv["file"]).exists()
        assert {"vs_random", "vs_random_first", "vs_bot", "vs_minimax"} <= set(lv["checks"])
        net.ValueNet.load(tmp_path / lv["file"])
    assert [p["games"] for p in saved["curve"]] == [200, 400]
    assert {"vs_random", "vs_bot"} <= set(saved["curve"][0])
    assert saved["method"]["lambda"] is not None


def test_worst_case_finds_a_loss_of_an_untrained_net():
    model = net.ValueNet(3, rng=np.random.default_rng(0))
    assert selfplay.worst_case(model, rules.X) == -1
    assert selfplay.worst_case(model, rules.O) == -1


def test_recheck_rewrites_the_same_checks(tmp_path):
    _, passport = selfplay.train(3, games=200, seed=2, snapshots={}, eval_every=0, final_games=10,
                                 out_dir=tmp_path, log=None)
    again = selfplay.recheck(3, tmp_path, final_games=10, log=None)
    assert again["levels"][0]["checks"] == json.loads(json.dumps(passport["levels"][0]["checks"]))
