import json

import numpy as np
import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel

import paths
from game import app as app_module
from game import theme


def pump(until, timeout=5000):
    waited = 0
    while not until() and waited < timeout:
        QTest.qWait(5)
        waited += 5
    return until()


@pytest.fixture
def win(qapp):
    w = app_module.MainWindow()
    w.change_setting("delay_ms", 0)
    w.show()
    yield w
    w.close()


def click_cell(w, r, c):
    board = w.game.board_widget
    QTest.mouseClick(board, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     board.cell_rect(r, c).center().toPoint())


def distinct_colors(image, step=7):
    seen = set()
    for x in range(0, image.width(), step):
        for y in range(0, image.height(), step):
            seen.add(image.pixel(x, y))
    return len(seen)


@pytest.mark.parametrize("theme_name", ["dark", "light"])
def test_every_page_draws_in_both_themes(win, theme_name):
    win.change_setting("theme", theme_name)
    bg = theme.palette(theme_name)["bg"].lstrip("#")
    for name in ("menu", "game", "stats", "settings"):
        win.show_page(name)
        QTest.qWait(10)
        image = win.grab().toImage()
        assert not image.isNull()
        assert distinct_colors(image) > 12, name
        corner = image.pixelColor(3, image.height() - 3)
        assert corner.name().lstrip("#") == bg, (name, corner.name())


def test_menu_buttons_lead_to_pages(win):
    for button, page in ((win.menu.play_button, "game"), (win.menu.stats_button, "stats"),
                         (win.menu.settings_button, "settings")):
        win.show_page("menu")
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        assert win.current_page() == page


def test_full_game_with_the_mouse_is_recorded(win):
    win.show_page("game")
    game = win.game
    game.set_first("me")
    game.set_size(3)
    s = game.session
    while s.result is None:
        assert pump(lambda: s.result is not None or s.human_turn())
        if s.result is not None:
            break
        r, c = [int(v) for v in np.argwhere(s.board == 0)[0]]
        click_cell(win, r, c)
    assert game.status.text() in ("Победа!", "Поражение", "Ничья")
    stats = json.loads(open(paths.user_file("stats.json"), encoding="utf-8").read())
    assert stats[f"3x3/{s.level}"]["games"] == 1


def test_digit_keys_move_on_3x3(win):
    win.show_page("game")
    win.game.set_first("me")
    win.game.set_size(3)
    QTest.keyClick(win.game, Qt.Key.Key_5)
    assert win.game.session.board[1, 1] == 1
    assert pump(lambda: np.count_nonzero(win.game.session.board) == 2)
    QTest.keyClick(win.game, Qt.Key.Key_1)
    assert win.game.session.board[0, 0] == 1 or np.count_nonzero(win.game.session.board) == 2


def test_net_moves_first_when_asked(win):
    win.show_page("game")
    win.game.set_first("net")
    assert pump(lambda: np.count_nonzero(win.game.session.board) == 1)
    assert int(win.game.session.board.sum()) == 1          # это крестик сети


def test_again_starts_a_new_game_and_menu_goes_back(win):
    win.show_page("game")
    win.game.set_first("me")
    click_cell(win, 0, 0)
    assert pump(lambda: np.count_nonzero(win.game.session.board) == 2)
    QTest.mouseClick(win.game.again_button, Qt.MouseButton.LeftButton)
    assert np.count_nonzero(win.game.session.board) == 0
    QTest.mouseClick(win.game.menu_button, Qt.MouseButton.LeftButton)
    assert win.current_page() == "menu"


def test_escape_goes_back_to_the_menu(win):
    for page in ("game", "stats", "settings"):
        win.show_page(page)
        QTest.keyClick(win.pages[page], Qt.Key.Key_Escape)
        assert win.current_page() == "menu"


def test_size_and_level_buttons_start_a_new_game(win):
    win.show_page("game")
    QTest.mouseClick(win.game.size_buttons[5], Qt.MouseButton.LeftButton)
    assert win.game.session.size == 5 and win.game.session.board.shape == (5, 5)
    QTest.mouseClick(win.game.level_buttons["novice"], Qt.MouseButton.LeftButton)
    assert win.game.session.level == "novice"
    saved = json.loads(open(paths.user_file("settings.json"), encoding="utf-8").read())
    assert saved["size"] == 5 and saved["level"] == "novice"


def test_thoughts_of_the_net_are_shown_when_enabled(win):
    win.show_page("game")
    win.game.set_first("me")
    win.game.thoughts_box.setChecked(True)
    t = win.game.board_widget.thoughts
    assert t is not None and np.isfinite(t).sum() == 9
    win.game.thoughts_box.setChecked(False)
    assert win.game.board_widget.thoughts is None


def test_settings_are_saved_at_once(win):
    page = win.settings_page
    page.volume.setValue(33)
    page.delay.setValue(800)
    page.thoughts.setChecked(True)
    page.first_combo.setCurrentIndex(2)
    page.theme_combo.setCurrentIndex(1)
    saved = json.loads(open(paths.user_file("settings.json"), encoding="utf-8").read())
    assert saved["volume"] == 33 and saved["delay_ms"] == 800 and saved["show_thoughts"] is True
    assert saved["first"] == "alternate" and saved["theme"] == "light"
    assert theme.palette("light")["bg"] in win.styleSheet()
    assert win.sounds.volume == 33


def test_stats_page_shows_recorded_games(win):
    win.stats.record(5, "medium", "win")
    win.show_page("stats")
    table = win.stats_page.table
    texts = [table.item(r, c).text() for r in range(table.rowCount()) for c in range(table.columnCount())
             if table.item(r, c)]
    assert "5×5 · средний" in texts
    row = texts.index("5×5 · средний") // table.columnCount()
    assert table.item(row, 1).text() == "1" and table.item(row, 2).text() == "1"


def test_stats_page_shows_curve_and_checks_for_both_fields(win):
    win.show_page("stats")
    page = win.stats_page
    for size in (3, 5):
        page.set_field(size)
        assert len(page.chart.curve) > 3
        assert page.checks.rowCount() == 3


def test_window_place_is_saved_on_close(qapp):
    from game import window_state

    w = app_module.MainWindow()
    w.show()
    # экран offscreen маленький (800x600): окно минимального размера и место, где оно
    # влезает целиком, - иначе правило места законно его подвинет
    width, height = w.minimumWidth(), w.minimumHeight()
    area = window_state.work_areas()[0]
    x = area["x"] + min(12, area["width"] - width)
    y = area["y"] + min(20, area["height"] - height)
    w.resize(width, height)
    w.move(x, y)
    qapp.processEvents()
    w.close()
    saved = json.loads(open(paths.user_file("window.json"), encoding="utf-8").read())
    assert (saved["x"], saved["y"], saved["width"], saved["height"]) == (x, y, width, height)
    w2 = app_module.MainWindow()
    w2.show()
    assert (w2.x(), w2.y(), w2.width(), w2.height()) == (x, y, width, height)
    w2.close()


def test_window_is_never_smaller_than_the_game_panel(qapp):
    w = app_module.MainWindow()
    w.show()
    w.resize(100, 100)
    w.show_page("game")
    qapp.processEvents()
    need = w.game.minimumSizeHint()
    assert w.game.width() >= need.width() and w.game.height() >= need.height()
    w.close()


def test_window_fits_a_1024x768_screen(qapp):
    w = app_module.MainWindow()
    # экран 1024x768 минус панель задач и заголовок окна
    assert w.minimumWidth() <= 1000 and w.minimumHeight() <= 690
    w.close()


def test_mark_drawn_where_clicked(win):
    """Пиксель в центре клетки после хода - цвета крестика."""
    win.show_page("game")
    win.game.set_first("me")
    win.game.set_size(3)
    click_cell(win, 2, 2)
    board = win.game.board_widget
    image = board.grab().toImage()
    center = board.cell_rect(2, 2).center().toPoint()
    assert image.pixelColor(center).name() == theme.palette(win.settings.theme)["x"]
    assert image.pixelColor(QPoint(3, 3)).name() != theme.palette(win.settings.theme)["x"]


# Закон: подпись с переносом строк не ограничена по высоте и помещается целиком. Нашёл
# Алексей 26.09.2026 на своём экране: подсказка клавиш под «В меню» была обрезана сверху и
# снизу. Ей дали высоту ровно в одну строку (18 px), а на настоящем экране фраза чуть шире,
# чем в offscreen, - перенеслась на вторую строку и не влезла. Шрифт крупнее на 10%
# изображает этот «чуть шире».
QWIDGETSIZE_MAX = 16777215


def wrapped_labels(widget):
    return [lb for lb in widget.findChildren(QLabel) if lb.wordWrap() and lb.isVisible() and lb.text()]


def test_wrapping_labels_are_never_capped_in_height(win):
    for name in ("menu", "game", "stats", "settings"):
        win.show_page(name)
        QTest.qWait(10)
        capped = [lb.text() for lb in wrapped_labels(win) if lb.maximumHeight() < QWIDGETSIZE_MAX]
        assert capped == [], (name, capped)


@pytest.mark.parametrize("size", [3, 5])
@pytest.mark.parametrize("scale", [1.0, 1.1])
def test_game_panel_text_fits_at_minimum_window_size(qapp, size, scale):
    """Шрифт на 10% крупнее - «текст на настоящем экране шире, чем в offscreen»."""
    w = app_module.MainWindow()
    w.show()
    w.show_page("game")
    w.game.set_size(size)
    qapp.processEvents()
    for lb in w.game.findChildren(QLabel):
        px = lb.font().pixelSize() if lb.font().pixelSize() > 0 else round(lb.font().pointSizeF() * 96 / 72)
        lb.setStyleSheet(f"font-size: {round(px * scale)}px;")
    w.resize(w.minimumSize())
    QTest.qWait(30)
    clipped = [(lb.text(), lb.height(), lb.heightForWidth(lb.width())) for lb in wrapped_labels(w.game)
               if lb.heightForWidth(lb.width()) > lb.height()]
    w.close()
    assert clipped == []
