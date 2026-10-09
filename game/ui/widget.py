"""Виджет игры: меню, партия, статистика, настройки - страницы в одном QStackedWidget.

Своего главного окна у игры нет (контракт PythonAiGames): виджет встаёт во вкладку
оболочки или в окно отдельного запуска (aikit.make_window, main.py).

- тема, язык и громкость - из ctx и меняются на лету по ctx.changed; сменённые в настройках
  игры уходят в ctx, а оттуда - в оболочку и остальные игры;
- файлы - только в ctx.data_dir: settings.json (своё), stats.json (ctx.stats), звуки;
- pause()/resume(): ход сети ждёт в QTimer.singleShot с номером (token); увеличенный token
  отменяет его, resume() заново запускает ход, если он за сетью;
- shutdown(): потоков у игры нет - отменить ход сети и сохранить настройки.
"""
import os

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QFrame,
                               QGridLayout, QHBoxLayout, QHeaderView, QLabel, QPushButton,
                               QScrollArea, QSlider, QStackedWidget, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from game.ai import models
from game.core import rules
from game.session import Session, stats_key
from game.ui import theme
from game.ui.board_widget import BoardWidget
from game.ui.chart import CurveChart
from game.ui.i18n import LANG_NAMES, number, plural_key, translator
from game.ui.settings import Settings
from game.ui.sound import Sounds
from game.version import VERSION

FIRST = ("me", "net", "alternate")
FIELD_NAMES = {3: "3×3", 5: "5×5"}


def label(text, name=None, wrap=False):
    w = QLabel(text)
    if name:
        w.setObjectName(name)
    w.setWordWrap(wrap)
    return w


def card():
    frame = QFrame()
    frame.setObjectName("card")
    return frame


def button(text, name=None, slot=None):
    b = QPushButton(text)
    if name:
        b.setObjectName(name)
    b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    if slot:
        b.clicked.connect(slot)
    return b


class Page(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window_ = window
        self.setObjectName("page")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def on_show(self):
        self.setFocus()

    def retranslate(self, t):
        pass

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape and self.window_.current_page() != "menu":
            self.window_.show_page("menu")
            return
        super().keyPressEvent(event)


def segmented(options, slot):
    """Ряд кнопок-переключателей: {значение: подпись}. Возвращает (виджет, {значение: кнопка})."""
    box = QWidget()
    row = QHBoxLayout(box)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(6)
    group = QButtonGroup(box)
    group.setExclusive(True)
    buttons = {}
    for value, text in options.items():
        b = button(text, "seg")
        b.setCheckable(True)
        b.clicked.connect(lambda _=False, v=value: slot(v))
        group.addButton(b)
        row.addWidget(b)
        buttons[value] = b
    return box, buttons


# --- меню ---


class Logo(QWidget):
    """Маленькое поле с законченной партией - картинка над заголовком меню."""

    def __init__(self):
        super().__init__()
        self.setFixedSize(150, 150)

    def paintEvent(self, event):
        from game.ui.icon import render
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.drawImage(QRectF(0, 0, self.width(), self.height()), render(300))
        p.end()


class MenuPage(Page):
    def __init__(self, window):
        super().__init__(window)
        outer = QVBoxLayout(self)
        outer.addStretch(3)
        col = QVBoxLayout()
        col.setSpacing(10)
        col.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        logo = Logo()
        col.addWidget(logo, 0, Qt.AlignmentFlag.AlignHCenter)
        col.addSpacing(8)
        self.title = label("", "title")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(self.title)
        self.sub = label("", "muted")
        self.sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(self.sub)
        col.addSpacing(22)
        self.play_button = button("", "menuPrimary", lambda: window.start_play())
        self.stats_button = button("", "menu", lambda: window.show_page("stats"))
        self.settings_button = button("", "menu", lambda: window.show_page("settings"))
        self.quit_button = button("", "menu", window.quit)
        # «Выход» - только в окне отдельного запуска (main.py включает его через allow_quit):
        # во вкладке оболочки игру закрывает крестик вкладки
        self.quit_button.setVisible(False)
        for b in (self.play_button, self.stats_button, self.settings_button, self.quit_button):
            col.addWidget(b, 0, Qt.AlignmentFlag.AlignHCenter)
        outer.addLayout(col)
        outer.addStretch(4)
        self.foot = label("", "hint")
        self.foot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self.foot)

    def retranslate(self, t):
        self.title.setText(t("title"))
        self.sub.setText(t("subtitle"))
        self.play_button.setText(t("play"))
        self.stats_button.setText(t("stats"))
        self.settings_button.setText(t("settings"))
        self.quit_button.setText(t("quit"))
        self.foot.setText(t("footer", version=VERSION))

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.window_.start_play()
            return
        super().keyPressEvent(event)


# --- партия ---


class GamePage(Page):
    def __init__(self, window):
        super().__init__(window)
        self.session = None
        self.token = 0
        s = window.settings
        self.size, self.level, self.first = s.size, s.level, s.first

        root = QHBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(24)
        self.board_widget = BoardWidget()
        self.board_widget.cellClicked.connect(self.on_cell)
        root.addWidget(self.board_widget, 1)

        side = card()
        side.setFixedWidth(300)
        col = QVBoxLayout(side)
        col.setContentsMargins(18, 16, 18, 16)
        col.setSpacing(6)

        self.field_caption = label("", "muted")
        col.addWidget(self.field_caption)
        box, self.size_buttons = segmented(FIELD_NAMES, self.set_size)
        col.addWidget(box)
        col.addSpacing(4)
        self.level_caption = label("", "muted")
        col.addWidget(self.level_caption)
        box, self.level_buttons = segmented({lv: lv for lv in models.LEVELS}, self.set_level)
        col.addWidget(box)
        col.addSpacing(4)
        self.first_caption = label("", "muted")
        col.addWidget(self.first_caption)
        self.first_combo = QComboBox()
        self.first_combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for key in FIRST:
            self.first_combo.addItem(key, key)
        self.first_combo.currentIndexChanged.connect(
            lambda i: self.set_first(self.first_combo.itemData(i)))
        col.addWidget(self.first_combo)

        col.addSpacing(8)

        self.status = label("", "status")
        col.addWidget(self.status)
        self.substatus = label("", "muted", wrap=True)
        # не меньше двух строк: текст меняется по ходу партии, а панель не должна прыгать.
        # Но и не больше нельзя: фиксированная высота обрезала перенесённый текст (26.09).
        self.substatus.setMinimumHeight(40)
        self.substatus.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        col.addWidget(self.substatus)
        col.addSpacing(4)

        score = QHBoxLayout()
        score.setSpacing(6)
        self.score_labels = {}
        self.score_caps = {}
        for key in ("wins", "draws", "losses"):
            cell = QVBoxLayout()
            cell.setSpacing(0)
            num = label("0", "bigNumber")
            num.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cap = label("", "hint")
            cap.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cell.addWidget(num)
            cell.addWidget(cap)
            score.addLayout(cell)
            self.score_labels[key] = num
            self.score_caps[key] = cap
        col.addLayout(score)
        self.score_caption = label("", "hint", wrap=True)
        self.score_caption.setMinimumHeight(18)
        self.score_caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(self.score_caption)
        col.addSpacing(4)

        self.thoughts_box = QCheckBox()
        self.thoughts_box.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.thoughts_box.setChecked(s.show_thoughts)
        self.thoughts_box.toggled.connect(lambda on: window.change_setting("show_thoughts", on))
        col.addWidget(self.thoughts_box)
        self.thoughts_hint = label("", "hint", wrap=True)
        col.addWidget(self.thoughts_hint)
        col.addStretch(1)

        self.again_button = button("", "primary", self.again)
        self.menu_button = button("", None, lambda: window.show_page("menu"))
        col.addWidget(self.again_button)
        col.addWidget(self.menu_button)
        self.keys_hint = label("", "hint", wrap=True)
        # Высота - от текста: на настоящем экране фраза шире, чем в offscreen, переносится
        # на вторую строку, и высота в одну строку её обрезала (Алексей, 26.09.2026).
        self.keys_hint.setMinimumHeight(18)
        self.keys_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(self.keys_hint)
        root.addWidget(side)
        self.sync_controls()

    def retranslate(self, t):
        self.field_caption.setText(t("field"))
        self.level_caption.setText(t("net_level"))
        self.first_caption.setText(t("first_move"))
        for level, b in self.level_buttons.items():
            b.setText(t("level_" + level))
        for i, key in enumerate(FIRST):
            self.first_combo.setItemText(i, t("first_" + key))
        for key, cap in self.score_caps.items():
            cap.setText(t(key + "_small"))
        self.thoughts_box.setText(t("thoughts"))
        self.thoughts_hint.setText(t("thoughts_hint"))
        self.again_button.setText(t("again"))
        self.menu_button.setText(t("to_menu"))
        self.refresh()

    # --- выбор партии ---

    def sync_controls(self):
        self.size_buttons[self.size].setChecked(True)
        self.level_buttons[self.level].setChecked(True)
        self.first_combo.blockSignals(True)
        self.first_combo.setCurrentIndex(FIRST.index(self.first))
        self.first_combo.blockSignals(False)

    def set_size(self, size):
        self.size = size
        self.window_.change_setting("size", size)
        self.new_session()

    def set_level(self, level):
        self.level = level
        self.window_.change_setting("level", level)
        self.new_session()

    def set_first(self, first):
        self.first = first
        self.new_session()

    def new_session(self):
        self.sync_controls()
        self.session = Session(self.size, self.level, models.load(self.size, self.level), first=self.first,
                               stats=self.window_.stats)
        self.after_change()

    def again(self):
        if self.session is None:
            self.new_session()
            return
        self.session.restart()
        self.after_change()

    # --- ходы ---

    def on_cell(self, r, c):
        if self.session is not None and self.session.human_move((r, c)):
            self.after_move()

    def keyPressEvent(self, event):
        key = event.key()
        if self.session is not None and self.size == 3 and Qt.Key.Key_1 <= key <= Qt.Key.Key_9:
            self.on_cell(*divmod(key - Qt.Key.Key_1, 3))
            return
        if key in (Qt.Key.Key_R, Qt.Key.Key_F2):
            self.again()
            return
        super().keyPressEvent(event)

    def after_move(self):
        s = self.session
        if s.result is None:
            self.window_.play_sound("x" if s.board[s.last] == rules.X else "o")
        else:
            self.window_.play_sound(s.outcome_for_human())
        self.after_change()

    def after_change(self):
        self.token += 1
        self.refresh()
        s = self.session
        if s.result is None and not s.human_turn() and not self.window_.paused and not self.window_.closed:
            token = self.token
            QTimer.singleShot(self.window_.settings.delay_ms, lambda: self.net_turn(token))

    def net_turn(self, token):
        s = self.session
        if token != self.token or s.result is not None or s.human_turn():
            return
        s.net_move()
        self.after_move()

    # --- вид ---

    def refresh(self):
        s = self.session
        if s is None:
            return
        t = self.window_.t
        show = self.window_.settings.show_thoughts
        self.board_widget.set_state(s.board, s.line, s.last, s.thoughts() if show and s.result is None else None,
                                    interactive=s.human_turn())
        mark = t("mark_x") if s.human == rules.X else t("mark_o")
        level = t("level_" + s.level)
        outcome = s.outcome_for_human()
        if outcome is None:
            self.status.setObjectName("status")
            self.status.setText(t("your_move") if s.human_turn() else t("net_thinks"))
            self.substatus.setText(t("playing", mark=mark, rule=t(f"rule_{s.size}"), level=level))
        else:
            self.status.setObjectName({"win": "statusWin", "loss": "statusLoss", "draw": "statusDraw"}[outcome])
            self.status.setText(t(outcome))
            self.substatus.setText(t("played", tail=t("tail_" + outcome), mark=mark))
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        e = self.window_.stats.entry(stats_key(s.size, s.level))
        for key, w in self.score_labels.items():
            w.setText(str(e[key]))
        streak = e["streak"]
        word = t(plural_key(e["games"], self.window_.ctx.lang))
        self.score_caption.setText(
            t("score_caption", field=FIELD_NAMES[s.size], level=level, games=e["games"], word=word)
            + (t("streak", streak=streak) if streak > 1 else ""))
        self.keys_hint.setText(t("keys_3") if s.size == 3 else t("keys_5"))
        self.thoughts_box.blockSignals(True)
        self.thoughts_box.setChecked(show)
        self.thoughts_box.blockSignals(False)

    def apply_theme(self, name):
        self.board_widget.set_theme(name)


# --- статистика ---


def table(columns):
    t = QTableWidget(0, len(columns))
    t.setHorizontalHeaderLabels(columns)
    t.verticalHeader().setVisible(False)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
    t.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    t.setShowGrid(False)
    t.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    t.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    header = t.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
    header.setHighlightSections(False)
    return t


def fit_height(t):
    t.resizeRowsToContents()
    h = t.horizontalHeader().height() + sum(t.rowHeight(r) for r in range(t.rowCount())) + 4
    t.setFixedHeight(h)


def item(text, align=Qt.AlignmentFlag.AlignCenter, color=None):
    it = QTableWidgetItem(text)
    it.setTextAlignment(align | Qt.AlignmentFlag.AlignVCenter)
    if color:
        it.setForeground(QColor(color))
    return it


def check_text(c):
    return f"{round(100 * c['win_rate'])}%   {c['wins']} / {c['draws']} / {c['losses']}"


TABLE_COLUMNS = ("col_field_level", "col_games", "col_wins", "col_losses", "col_draws", "col_streak",
                 "col_best")
CHECK_COLUMNS = ("col_level", "col_train_games", "col_vs_random", "col_vs_bot", "col_vs_minimax")


class StatsPage(Page):
    def __init__(self, window):
        super().__init__(window)
        self.field = 3
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)
        body = QWidget()
        body.setObjectName("page")
        body.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        scroll.setWidget(body)
        col = QVBoxLayout(body)
        col.setContentsMargins(28, 24, 28, 24)
        col.setSpacing(16)

        top = QHBoxLayout()
        self.heading = label("", "heading")
        top.addWidget(self.heading)
        top.addStretch(1)
        self.menu_button = button("", None, lambda: window.show_page("menu"))
        top.addWidget(self.menu_button)
        col.addLayout(top)

        # ваши партии
        mine = card()
        mc = QVBoxLayout(mine)
        mc.setContentsMargins(20, 16, 20, 16)
        mc.setSpacing(10)
        self.mine_title = label("", "section")
        mc.addWidget(self.mine_title)
        totals = QHBoxLayout()
        self.total_labels = {}
        self.total_caps = {}
        for key, name in (("games", "total_games"), ("wins", "total_wins"), ("draws", "total_draws"),
                          ("losses", "total_losses"), ("best_streak", "total_best")):
            cell = QVBoxLayout()
            cell.setSpacing(0)
            num = label("0", "bigNumber")
            cap = label("", "hint")
            cell.addWidget(num)
            cell.addWidget(cap)
            totals.addLayout(cell)
            self.total_labels[key] = num
            self.total_caps[name] = cap
        totals.addStretch(1)
        mc.addLayout(totals)
        self.table = table(TABLE_COLUMNS)
        mc.addWidget(self.table)
        col.addWidget(mine)

        # обучение
        learn = card()
        lc = QVBoxLayout(learn)
        lc.setContentsMargins(20, 16, 20, 16)
        lc.setSpacing(10)
        head = QHBoxLayout()
        self.learn_title = label("", "section")
        head.addWidget(self.learn_title)
        head.addStretch(1)
        box, self.field_buttons = segmented(FIELD_NAMES, self.set_field)
        head.addWidget(box)
        lc.addLayout(head)
        self.learn_caption = label("", "muted", wrap=True)
        lc.addWidget(self.learn_caption)
        self.chart = CurveChart()
        lc.addWidget(self.chart)
        self.checks_title = label("", "section")
        lc.addWidget(self.checks_title)
        self.checks = table(CHECK_COLUMNS)
        lc.addWidget(self.checks)
        self.checks_caption = label("", "hint", wrap=True)
        lc.addWidget(self.checks_caption)
        col.addWidget(learn)
        col.addStretch(1)

    def retranslate(self, t):
        self.heading.setText(t("stats"))
        self.menu_button.setText(t("to_menu"))
        self.mine_title.setText(t("your_games"))
        for name, cap in self.total_caps.items():
            cap.setText(t(name))
        self.table.setHorizontalHeaderLabels([t(c) for c in TABLE_COLUMNS])
        self.learn_title.setText(t("how_learned"))
        self.checks_title.setText(t("net_checks"))
        self.checks.setHorizontalHeaderLabels([t(c) for c in CHECK_COLUMNS])
        self.chart.set_lang(self.window_.ctx.lang)
        self.refresh()

    def on_show(self):
        super().on_show()
        self.refresh()

    def set_field(self, size):
        self.field = size
        self.refresh()

    def refresh(self):
        t = self.window_.t
        lang = self.window_.ctx.lang
        stats = self.window_.stats
        tot = stats.totals()
        for key, w in self.total_labels.items():
            w.setText(str(tot[key]))
        rows = [(size, level) for size in (3, 5) for level in models.LEVELS]
        self.table.setRowCount(len(rows))
        for r, (size, level) in enumerate(rows):
            e = stats.entry(stats_key(size, level))
            self.table.setItem(r, 0, item(f"{FIELD_NAMES[size]} · {t('level_' + level)}",
                                          Qt.AlignmentFlag.AlignLeft))
            for c, key in enumerate(("games", "wins", "losses", "draws", "streak", "best_streak"), start=1):
                self.table.setItem(r, c, item(str(e[key])))
        fit_height(self.table)

        self.field_buttons[self.field].setChecked(True)
        pp = models.passport(self.field)
        marks = [(lv["games"], t("level_" + lv["key"])) for lv in pp["levels"] if lv["key"] != "strong"]
        self.chart.set_data(pp["curve"], marks)
        net = pp["network"]
        if net["kind"] == "dense":
            kind = t("kind_dense", h=net["hidden"])
        else:
            kind = (t("kind_conv", layers=" → ".join([str(net["channels"])] * net["conv_layers"]))
                    + (t("kind_head", head=net["head"]) if net.get("head") else " → 1"))
        sec = pp["train_seconds"]
        took = t("seconds", n=round(sec)) if sec < 90 else t("minutes", n=round(sec / 60))
        self.learn_caption.setText(t(
            "learn_caption", field=FIELD_NAMES[self.field], rule=t(f"rule_{self.field}"), kind=kind,
            params=number(net["parameters"], lang), games=number(pp["games"], lang), took=took))
        self.checks.setRowCount(len(pp["levels"]))
        minimax = self.field == 3
        self.checks.setColumnHidden(4, not minimax)
        for r, lv in enumerate(pp["levels"]):
            ch = lv["checks"]
            self.checks.setItem(r, 0, item(t("level_" + lv["key"]), Qt.AlignmentFlag.AlignLeft))
            self.checks.setItem(r, 1, item(number(lv["games"], lang)))
            self.checks.setItem(r, 2, item(check_text(ch["vs_random"])))
            self.checks.setItem(r, 3, item(check_text(ch["vs_bot"])))
            if minimax:
                mm = ch["vs_minimax"]
                good = self.window_.colors()["good" if mm["losses"] == 0 else "bad"]
                self.checks.setItem(r, 4, item(check_text(mm), color=good))
        fit_height(self.checks)
        games = pp["levels"][-1]["checks"]["vs_random"]["games"]
        text = t("checks_caption", games=games)
        if minimax:
            text += t("minimax_caption")
            safe = [t("quote").format(t("level_" + lv["key"])) for lv in pp["levels"]
                    if min(lv["checks"].get("worst_case", {"x": -1}).values()) >= 0]
            if safe:
                text += t("safe_caption", names=", ".join(safe))
        self.checks_caption.setText(text)

    def apply_theme(self, name):
        self.chart.set_theme(name)
        if self.isVisible():
            self.refresh()


# --- настройки ---


class SettingsPage(Page):
    ROWS = (("volume", "volume", "volume_hint"), ("theme", "theme", "theme_hint"),
            ("language", "language", "language_hint"), ("delay", "delay", "delay_hint"),
            ("thoughts", "thoughts_title", "thoughts_settings_hint"),
            ("first", "default_first", "default_first_hint"))

    def __init__(self, window):
        super().__init__(window)
        s = window.settings
        ctx = window.ctx
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(16)
        top = QHBoxLayout()
        self.heading = label("", "heading")
        top.addWidget(self.heading)
        top.addStretch(1)
        self.menu_button = button("", None, lambda: window.show_page("menu"))
        top.addWidget(self.menu_button)
        outer.addLayout(top)

        box = card()
        box.setMaximumWidth(720)
        grid = QGridLayout(box)
        grid.setContentsMargins(24, 20, 24, 20)
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(18)
        grid.setColumnStretch(1, 1)
        self.row_labels = {}

        def row(r, key, widget, extra=None):
            names = QVBoxLayout()
            names.setSpacing(2)
            title, hint = label("", "section"), label("", "hint", wrap=True)
            self.row_labels[key] = (title, hint)
            names.addWidget(title)
            names.addWidget(hint)
            grid.addLayout(names, r, 0)
            line = QHBoxLayout()
            line.addWidget(widget, 1)
            if extra is not None:
                line.addWidget(extra)
            grid.addLayout(line, r, 1)

        volume = ctx.sound.volume
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(volume)
        self.volume_label = label(f"{volume}%")
        self.volume_label.setMinimumWidth(56)
        self.volume.valueChanged.connect(self.on_volume)
        row(0, "volume", self.volume, self.volume_label)

        self.theme_combo = QComboBox()
        for key in theme.THEME_NAMES:
            self.theme_combo.addItem(key, key)
        self.theme_combo.setCurrentIndex(list(theme.THEME_NAMES).index(ctx.theme))
        self.theme_combo.currentIndexChanged.connect(lambda i: ctx.set_theme(self.theme_combo.itemData(i)))
        row(1, "theme", self.theme_combo)

        self.lang_combo = QComboBox()
        for key, text in LANG_NAMES.items():
            self.lang_combo.addItem(text, key)
        self.lang_combo.setCurrentIndex(list(LANG_NAMES).index(ctx.lang))
        self.lang_combo.currentIndexChanged.connect(lambda i: ctx.set_lang(self.lang_combo.itemData(i)))
        row(2, "language", self.lang_combo)

        self.delay = QSlider(Qt.Orientation.Horizontal)
        self.delay.setRange(0, 2000)
        self.delay.setSingleStep(50)
        self.delay.setPageStep(250)
        self.delay.setValue(s.delay_ms)
        self.delay_label = label("")
        self.delay_label.setMinimumWidth(56)
        self.delay.valueChanged.connect(self.on_delay)
        row(3, "delay", self.delay, self.delay_label)

        self.thoughts = QCheckBox()
        self.thoughts.setChecked(s.show_thoughts)
        self.thoughts.toggled.connect(lambda on: window.change_setting("show_thoughts", on))
        row(4, "thoughts", self.thoughts)

        self.first_combo = QComboBox()
        for key in FIRST:
            self.first_combo.addItem(key, key)
        self.first_combo.setCurrentIndex(FIRST.index(s.first))
        self.first_combo.currentIndexChanged.connect(
            lambda i: window.change_setting("first", self.first_combo.itemData(i)))
        row(5, "first", self.first_combo)

        outer.addWidget(box)
        self.saved_hint = label("", "hint")
        outer.addWidget(self.saved_hint)
        outer.addStretch(1)

    def retranslate(self, t):
        self.heading.setText(t("settings"))
        self.menu_button.setText(t("to_menu"))
        for key, title_key, hint_key in self.ROWS:
            title, hint = self.row_labels[key]
            title.setText(t(title_key))
            hint.setText(t(hint_key))
        for i, key in enumerate(theme.THEME_NAMES):
            self.theme_combo.setItemText(i, t("theme_" + key))
        for i, key in enumerate(FIRST):
            self.first_combo.setItemText(i, t("first_" + key))
        self.thoughts.setText(t("show"))
        self.saved_hint.setText(t("saved_at_once"))
        self.delay_label.setText(self.delay_text(self.window_.settings.delay_ms))

    def delay_text(self, ms):
        s = f"{ms / 1000:.2f}"
        if self.window_.ctx.lang == "ru":
            s = s.replace(".", ",")
        return self.window_.t("delay_value", s=s)

    def on_volume(self, v):
        self.volume_label.setText(f"{v}%")
        self.window_.set_volume(v)

    def on_delay(self, v):
        v = int(round(v / 50) * 50)
        self.delay_label.setText(self.delay_text(v))
        self.window_.change_setting("delay_ms", v)

    def sync(self):
        s = self.window_.settings
        volume = self.window_.ctx.sound.volume
        for w, value in ((self.volume, volume), (self.delay, s.delay_ms)):
            w.blockSignals(True)
            w.setValue(value)
            w.blockSignals(False)
        self.volume_label.setText(f"{volume}%")
        self.delay_label.setText(self.delay_text(s.delay_ms))
        self.thoughts.blockSignals(True)
        self.thoughts.setChecked(s.show_thoughts)
        self.thoughts.blockSignals(False)
        self.sync_combos()

    def on_show(self):
        super().on_show()
        self.sync()

    def sync_combos(self):
        s = self.window_.settings
        ctx = self.window_.ctx
        for combo, keys, value in ((self.theme_combo, list(theme.THEME_NAMES), ctx.theme),
                                   (self.lang_combo, list(LANG_NAMES), ctx.lang),
                                   (self.first_combo, list(FIRST), s.first)):
            combo.blockSignals(True)
            combo.setCurrentIndex(keys.index(value))
            combo.blockSignals(False)


# --- виджет игры ---


class GameWidget(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.t = translator(ctx.lang)
        self.paused = False
        self.closed = False
        self._quit = None
        self.setObjectName("gameRoot")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.settings_path = ctx.file("settings.json")
        self.settings = Settings.load(self.settings_path)
        self.stats = ctx.stats
        # свои звуки (крестик, нолик, итог партии) - в своей подпапке: в sounds/ пишет ctx.sound
        self.sounds = Sounds(os.path.join(ctx.data_dir, "game-sounds"), ctx.sound.volume)

        self.stack = QStackedWidget()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.stack)
        self.menu = MenuPage(self)
        self.game = GamePage(self)
        self.stats_page = StatsPage(self)
        self.settings_page = SettingsPage(self)
        self.pages = {"menu": self.menu, "game": self.game, "stats": self.stats_page,
                      "settings": self.settings_page}
        for page in self.pages.values():
            self.stack.addWidget(page)
        self.apply_theme(ctx.theme)
        self.game.new_session()
        self.retranslate()
        self.show_page("menu")
        ctx.changed.connect(self.on_ctx_changed)

    # --- страницы ---

    def colors(self):
        return theme.palette(self.ctx.theme)

    def current_page(self):
        current = self.stack.currentWidget()
        return next(name for name, page in self.pages.items() if page is current)

    def show_page(self, name):
        if name != "game":
            self.game.token += 1          # ход сети, ждущий в таймере, больше не нужен
        self.stack.setCurrentWidget(self.pages[name])
        self.pages[name].on_show()
        if name == "game" and self.game.session is None:
            self.game.new_session()

    def start_play(self):
        """«Играть» из меню: первый ход - из настроек, поле и уровень - последние выбранные."""
        self.game.first = self.settings.first
        self.stack.setCurrentWidget(self.game)
        self.game.on_show()
        self.game.new_session()

    def allow_quit(self, slot):
        """Окно отдельного запуска: показать «Выход» в меню; slot закрывает окно."""
        self._quit = slot
        self.menu.quit_button.setVisible(True)

    def quit(self):
        if self._quit is not None:
            self._quit()

    # --- настройки ---

    def change_setting(self, name, value):
        setattr(self.settings, name, value)
        self.settings.save(self.settings_path)
        if name == "show_thoughts":
            self.game.refresh()

    def set_volume(self, value):
        self.ctx.set_volume(value)
        self.sounds.set_volume(value)

    def play_sound(self, name):
        # громкость общая и в оболочке меняется без сигнала - сверяется перед звуком
        if self.sounds.volume != self.ctx.sound.volume:
            self.sounds.set_volume(self.ctx.sound.volume)
        self.sounds.play(name)

    # --- тема и язык на лету ---

    def on_ctx_changed(self, what):
        if what == "theme":
            self.apply_theme(self.ctx.theme)
        elif what == "lang":
            self.t = translator(self.ctx.lang)
            self.retranslate()
        self.settings_page.sync_combos()

    def apply_theme(self, name):
        self.setStyleSheet(theme.qss(name))
        for page in self.pages.values():
            if hasattr(page, "apply_theme"):
                page.apply_theme(name)

    def retranslate(self):
        for page in self.pages.values():
            page.retranslate(self.t)

    # --- жизнь во вкладке оболочки ---

    def pause(self):
        self.paused = True
        self.game.token += 1               # ход сети, ждущий в таймере, отменён

    def resume(self):
        self.paused = False
        if self.game.session is not None and self.current_page() == "game":
            self.game.after_change()       # снова запустит ход, если он за сетью

    def shutdown(self):
        """Потоков у игры нет: отменить ход сети и сохранить настройки. True - всё остановлено."""
        self.closed = True
        self.game.token += 1
        self.settings.save(self.settings_path)
        return True
