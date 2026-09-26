import numpy as np
import pytest

from core import net, rules
from game.session import Session
from game.stats import Stats


@pytest.fixture
def model3():
    return net.ValueNet(3, rng=np.random.default_rng(0))


def make(model, first="me", stats=None, path=None, size=3):
    return Session(size, "strong", model, first=first, stats=stats or Stats(), stats_path=path)


def play_out(s, rng):
    """Доиграть партию: за человека - случайные ходы."""
    while s.result is None:
        if s.human_turn():
            moves = rules.legal_moves(s.board)
            assert s.human_move(moves[rng.integers(len(moves))])
        else:
            s.net_move()


def test_human_first_plays_x(model3):
    s = make(model3, "me")
    assert s.human == rules.X and s.human_turn()


def test_net_first_plays_x(model3):
    s = make(model3, "net")
    assert s.human == rules.O and not s.human_turn()
    cell = s.net_move()
    assert s.board[cell] == rules.X and s.human_turn()


def test_alternate_changes_color_every_game(model3):
    s = make(model3, "alternate")
    colors = []
    for _ in range(4):
        colors.append(s.human)
        play_out(s, np.random.default_rng(1))
        s.restart()
    assert colors == [rules.X, rules.O, rules.X, rules.O]


def test_move_into_occupied_cell_is_refused(model3):
    s = make(model3)
    assert s.human_move((1, 1))
    s.net_move()
    assert not s.human_move((1, 1))
    assert int(np.count_nonzero(s.board)) == 2


def test_human_cannot_move_on_the_nets_turn(model3):
    s = make(model3)
    s.human_move((0, 0))
    assert not s.human_move((2, 2))


def test_net_cannot_move_on_the_humans_turn(model3):
    with pytest.raises(RuntimeError):
        make(model3).net_move()


def test_game_goes_to_the_end_and_is_recorded_once(model3, tmp_path):
    stats = Stats()
    path = tmp_path / "stats.json"
    s = make(model3, stats=stats, path=path)
    play_out(s, np.random.default_rng(2))
    assert s.result is not None
    assert s.outcome_for_human() in ("win", "loss", "draw")
    assert stats.entry(3, "strong")["games"] == 1
    # после конца партии ходы не проходят и статистика не растёт
    empty = rules.legal_moves(s.board)
    if empty:
        assert not s.human_move(empty[0])
    s.finish()
    assert stats.entry(3, "strong")["games"] == 1
    assert Stats.load(path).entry(3, "strong")["games"] == 1


def test_winning_line_is_known_after_a_win(model3):
    s = make(model3)
    # человек ставит X в верхнюю строку, сеть ходит куда хочет; если сеть заняла клетку -
    # партия всё равно доигрывается, линия проверяется только при победе X
    rng = np.random.default_rng(3)
    play_out(s, rng)
    if s.result in (1, -1):
        assert s.line is not None and len(s.line) == 3
    else:
        assert s.line is None


def test_forced_human_win_gives_win_and_line(model3):
    s = make(model3)
    s.board = np.array([[1, 1, 0], [-1, -1, 0], [0, 0, 0]], np.int8)
    assert s.human_move((0, 2))
    assert s.result == rules.X and s.outcome_for_human() == "win"
    assert sorted(s.line) == [(0, 0), (0, 1), (0, 2)]


def test_thoughts_cover_free_cells(model3):
    s = make(model3)
    s.human_move((1, 1))
    t = s.thoughts()
    assert np.isnan(t[1, 1]) and np.isfinite(t).sum() == 8

