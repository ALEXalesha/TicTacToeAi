import numpy as np
import pytest

from core import rules


def board_from(text):
    """'X.O/.X./..X' -> поле: X = 1, O = -1, точка - пусто."""
    rows = text.split("/")
    value = {"X": 1, "O": -1, ".": 0}
    return np.array([[value[c] for c in row] for row in rows], dtype=np.int8)


def test_new_board_is_empty_int8():
    b = rules.new_board(5)
    assert b.shape == (5, 5) and b.dtype == np.int8 and not b.any()


def test_win_length_per_field():
    assert rules.win_length(3) == 3
    assert rules.win_length(5) == 4


@pytest.mark.parametrize("row", range(3))
def test_3x3_row_wins(row):
    b = rules.new_board(3)
    b[row, :] = 1
    assert rules.winner(b) == 1


@pytest.mark.parametrize("col", range(3))
def test_3x3_column_wins(col):
    b = rules.new_board(3)
    b[:, col] = -1
    assert rules.winner(b) == -1


def test_3x3_both_diagonals_win():
    assert rules.winner(board_from("X../.X./..X")) == 1
    assert rules.winner(board_from("..O/.O./O..")) == -1


def test_3x3_two_in_a_row_is_not_a_win():
    assert rules.winner(board_from("XX./OO./...")) == 0


def test_5x5_four_in_a_row_not_from_the_edge():
    # строка со второй клетки
    assert rules.winner(board_from("...../.XXXX/...../...../.....")) == 1
    # столбец в середине, с первой по четвёртую строку
    assert rules.winner(board_from("...../..O../..O../..O../..O..")) == -1
    # главная диагональ со второй клетки
    assert rules.winner(board_from("...../.X.../..X../...X./....X")) == 1
    # короткая диагональ над главной
    assert rules.winner(board_from(".X.../..X../...X./....X/.....")) == 1
    # обратная короткая диагональ
    assert rules.winner(board_from("...O./..O../.O.../O..../.....")) == -1


def test_5x5_three_in_a_row_is_not_a_win():
    assert rules.winner(board_from("XXX../...../...../...../.....")) == 0
    assert rules.winner(board_from("X..../.X.../..X../...../.....")) == 0


def test_5x5_broken_four_is_not_a_win():
    assert rules.winner(board_from("XX.XX/...../...../...../.....")) == 0


def test_winning_line_returns_the_cells():
    line = rules.winning_line(board_from("...../.X.../..X../...X./....X"))
    assert sorted(line) == [(1, 1), (2, 2), (3, 3), (4, 4)]
    assert rules.winning_line(rules.new_board(3)) is None


def test_number_of_lines():
    assert len(rules.lines(3, 3)) == 8
    # 5x5, 4 в ряд: 5*2 по строкам + 5*2 по столбцам + 4 + 4 по диагоналям
    assert len(rules.lines(5, 4)) == 28


def test_draw_on_full_board_without_winner():
    b = board_from("XOX/XOO/OXX")
    assert rules.winner(b) == 0
    assert rules.is_draw(b)
    assert rules.outcome(b) == 0


def test_full_board_with_winner_is_not_draw():
    b = board_from("XXX/OOX/XOO")
    assert not rules.is_draw(b)
    assert rules.outcome(b) == 1


def test_outcome_none_while_game_goes_on():
    assert rules.outcome(board_from("X../.O./...")) is None


def test_x_moves_first_then_turns_alternate():
    b = rules.new_board(3)
    assert rules.to_move(b) == 1
    b = rules.play(b, (1, 1))
    assert rules.to_move(b) == -1
    b = rules.play(b, (0, 0))
    assert rules.to_move(b) == 1
    assert b[1, 1] == 1 and b[0, 0] == -1


def test_play_does_not_change_the_old_board():
    b = rules.new_board(3)
    after = rules.play(b, (0, 0))
    assert not b.any() and after[0, 0] == 1


def test_play_into_occupied_cell_fails():
    b = rules.play(rules.new_board(3), (0, 0))
    with pytest.raises(ValueError):
        rules.play(b, (0, 0))


def test_play_outside_the_field_fails():
    with pytest.raises(ValueError):
        rules.play(rules.new_board(3), (3, 0))


def test_play_after_the_end_fails():
    b = board_from("XXX/OO./...")
    with pytest.raises(ValueError):
        rules.play(b, (2, 2))


def test_legal_moves_are_the_empty_cells():
    b = board_from("X../.O./..X")
    moves = rules.legal_moves(b)
    assert len(moves) == 6
    assert (0, 0) not in moves and (0, 1) in moves


def test_winner_for_a_batch_of_boards():
    boards = np.stack([board_from("XXX/OO./..."), board_from("X../.O./..."), board_from("O../O../O..")])
    np.testing.assert_array_equal(rules.winners(boards, 3), [1, 0, -1])
