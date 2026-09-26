import numpy as np
import pytest

from core import bots, net, rules
from tests.test_rules import board_from


def asymmetric(n):
    b = rules.new_board(n)
    b[0, 1] = 1
    b[1, 2 % n] = -1
    b[n - 1, 0] = 1
    return b


@pytest.mark.parametrize("n", [3, 5])
def test_symmetries_give_8_different_boards(n):
    s = net.symmetries(asymmetric(n))
    assert s.shape == (8, n, n)
    assert len({x.tobytes() for x in s}) == 8
    np.testing.assert_array_equal(s[0], asymmetric(n))


@pytest.mark.parametrize("n", [3, 5])
def test_every_symmetry_can_be_undone(n):
    b = asymmetric(n)
    for i in range(8):
        np.testing.assert_array_equal(net.untransform(net.transform(b, i), i), b)


def test_symmetries_keep_the_outcome():
    b = board_from("X../.X./..X")
    for s in net.symmetries(b):
        assert rules.winner(s) == 1
    b = board_from("XXXX./OOO../...../...../.....")
    for s in net.symmetries(b):
        assert rules.winner(s) == 1


def test_encode_is_from_the_movers_view():
    b = board_from("X../.O./...")
    planes = net.encode(net.perspective(b[None], np.array([-1])))
    assert planes.shape == (1, 3, 3, 2)
    # для O свои - нолики, чужие - крестики
    assert planes[0, 1, 1, 0] == 1 and planes[0, 0, 0, 1] == 1
    assert planes[0, 0, 0, 0] == 0 and planes[0, 1, 1, 1] == 0
    assert planes.dtype == np.float32


def test_afterstates_are_from_the_view_of_who_just_moved():
    b = board_from("X../.O./...")          # ходит X
    cells, after = net.afterstates(b)
    assert len(cells) == 7 and after.shape == (7, 3, 3)
    i = cells.index((2, 2))
    assert after[i, 2, 2] == 1 and after[i, 0, 0] == 1 and after[i, 1, 1] == -1
    b2 = rules.play(b, (2, 2))             # ходит O
    cells, after = net.afterstates(b2)
    i = cells.index((0, 1))
    # после хода O свои - нолики: O стал 1, X стал -1
    assert after[i, 0, 1] == 1 and after[i, 1, 1] == 1 and after[i, 0, 0] == -1


@pytest.mark.parametrize("n,kind", [(3, "dense"), (5, "conv")])
def test_net_outputs_one_value_in_minus_one_one(n, kind):
    model = net.ValueNet(n, rng=np.random.default_rng(0))
    assert model.kind == kind
    x = net.encode(np.stack([asymmetric(n)] * 4))
    v = model.value(x)
    assert v.shape == (4,)
    assert np.all(np.abs(v) < 1)


class FavourCell:
    """Поддельная сеть: чем больше своих в клетке (0, 0) после хода, тем лучше."""
    n = 3

    def value(self, planes):
        return planes[:, 0, 0, 0] * 0.9 - 0.1


def test_net_player_picks_the_highest_value():
    b = board_from(".../.O./..X")        # ходит O
    assert net.NetPlayer(FavourCell()).move(b) == (0, 0)


def test_net_player_moves_only_into_empty_cells_even_if_occupied_looks_best():
    # (0, 0) занята крестиком: поддельная сеть больше всего хотела бы её, но хода туда нет
    b = board_from("X../.O./...")
    move = net.NetPlayer(FavourCell()).move(b)
    assert b[move] == 0


@pytest.mark.parametrize("n", [3, 5])
def test_random_net_always_makes_legal_moves(n):
    rng = np.random.default_rng(1)
    player = net.NetPlayer(net.ValueNet(n, rng=rng))
    for _ in range(5):
        bots.play_game(player, bots.RandomBot(rng), n)   # play() упал бы на занятой клетке


def test_move_values_has_nan_for_occupied_cells():
    model = net.ValueNet(3, rng=np.random.default_rng(0))
    vals = net.move_values(model, board_from("X../.O./..."))
    assert np.isnan(vals[0, 0]) and np.isnan(vals[1, 1])
    assert np.isfinite(vals[2, 2])


@pytest.mark.parametrize("n", [3, 5])
def test_save_and_load_give_the_same_values(tmp_path, n):
    a = net.ValueNet(n, rng=np.random.default_rng(1))
    path = tmp_path / "m.npz"
    a.save(path)
    b = net.ValueNet.load(path)
    assert b.n == n and b.kind == a.kind
    x = net.encode(np.stack([asymmetric(n)]))
    np.testing.assert_array_equal(a.value(x), b.value(x))
