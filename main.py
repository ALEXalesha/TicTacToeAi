"""Крестики-нолики с нейросетью.

    python main.py                         # игра
    python main.py --offscreen             # без экрана (проверки)
    python main.py --selftest итог.txt     # самопроверка без экрана: партии сети против бота

Игра - виджет по контракту PythonAiGames (game/__init__.py); здесь только окно отдельного
запуска (aikit.make_window) с размером и «Выходом», как до 1.1.0, и перенос данных 1.0.x.

Самопроверка нужна прежде всего собранному exe: он без консоли, поэтому итог пишется в
файл. Окно создаётся offscreen, данные игрока - во временной папке, статистику игрока она
не трогает.
"""
import argparse
import os
import shutil
import sys
import tempfile
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

APP_NAME = "TicTacToeAi"
HOME_ENV = "TICTACTOEAI_HOME"           # подменяет папку данных целиком (тесты, самопроверка)
# окно - как у 1.0.x: 1000x700, не меньше 780x560 и не меньше панели партии
WINDOW_OPTS = {"width": 1000, "height": 700, "minWidth": 780, "minHeight": 560}


def old_data_dir(frozen, exe, env):
    """Где 1.0.x держал настройки и статистику: %LOCALAPPDATA%\\TicTacToeAi, у portable - saves
    рядом с exe, с переменной TICTACTOEAI_HOME - в ней."""
    if env.get(HOME_ENV):
        return env[HOME_ENV]
    if frozen:
        beside = os.path.dirname(os.path.abspath(exe))
        if os.path.exists(os.path.join(beside, "portable.txt")):
            return os.path.join(beside, "saves")
    base = env.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, APP_NAME)


def migrate(old, root, game_dir):
    """Перенести данные 1.0.x в раскладку контракта: settings.json и stats.json - в папку игры,
    window.json - в корень, тема и громкость - в host.json. Копией: старые файлы остаются на
    месте, уже перенесённое не перезаписывается. Возвращает список перенесённого."""
    from aikit import host, settings
    from aikit.storage import load_json

    done = []
    pairs = (("settings.json", game_dir), ("stats.json", game_dir), ("window.json", root))
    for name, folder in pairs:
        src, dst = os.path.join(old, name), os.path.join(folder, name)
        if os.path.isfile(src) and not os.path.exists(dst) and os.path.abspath(src) != os.path.abspath(dst):
            os.makedirs(folder, exist_ok=True)
            shutil.copy2(src, dst)
            done.append(name)
    host_path = os.path.join(root, "host.json")
    old_settings = load_json(os.path.join(old, "settings.json"))
    if not os.path.exists(host_path) and isinstance(old_settings, dict):
        hs = settings.Settings(host.host_schema(), host_path)
        for key in ("theme", "volume"):
            try:
                hs.set(key, old_settings[key])
            except (KeyError, ValueError):
                pass
        hs.save()
        done.append("host.json")
    return done


def open_window(root=None):
    """Окно отдельного запуска с виджетом игры. QApplication должно уже быть. Возвращает
    (окно, ctx); окно ещё не показано - window.memory.show()."""
    import aikit
    from aikit.window_state import WindowMemory
    from game import GAME_INFO, create_widget
    from game.ui.icon import app_icon

    root = root or aikit.data_root(APP_NAME)
    migrate(old_data_dir(aikit.frozen(), sys.executable, os.environ), root, os.path.join(root, GAME_INFO["id"]))
    window, ctx = aikit.make_window(GAME_INFO, create_widget, APP_NAME, root)
    need = window.game.minimumSizeHint()
    opts = {**WINDOW_OPTS, "minWidth": max(WINDOW_OPTS["minWidth"], need.width()),
            "minHeight": max(WINDOW_OPTS["minHeight"], need.height())}
    window.window_opts = opts
    window.setMinimumSize(opts["minWidth"], opts["minHeight"])
    window.memory = WindowMemory(window, os.path.join(root, "window.json"), opts)
    window.setWindowIcon(app_icon())
    window.game.allow_quit(window.close)
    return window, ctx


def selftest(out_path):
    lines = []
    code = 0
    try:
        from aikit import offscreen
        offscreen.setup(force=True)
        os.environ[HOME_ENV] = tempfile.mkdtemp(prefix="tictactoeai-selftest-")
        import numpy as np
        from PySide6.QtWidgets import QApplication

        import aikit
        from game.core import bots, rules
        from game.version import VERSION

        app = QApplication.instance() or QApplication([])
        window, _ = open_window()
        gw = window.game
        gw.change_setting("delay_ms", 0)
        window.show()
        lines.append(f"TicTacToeAi {VERSION} самопроверка")
        lines.append(f"собранная версия: {'да' if aikit.frozen() else 'нет'}")
        bot = bots.WinOrBlockBot(np.random.default_rng(7))
        for size in (3, 5):
            started = time.time()
            gw.start_play()
            gw.game.set_first("me")          # «я» - это бот, сеть играет ноликами
            gw.game.set_level("strong")
            gw.game.set_size(size)
            s = gw.game.session
            while s.result is None:
                if s.human_turn():
                    gw.game.on_cell(*bot.move(s.board))
                else:
                    gw.game.net_turn(gw.game.token)
            image = window.grab().toImage()
            if image.isNull() or image.width() < 100:
                raise RuntimeError("окно не нарисовалось")
            verdict = {"win": "бот", "loss": "сеть", "draw": "ничья"}[s.outcome_for_human()]
            lines.append(f"{size}x{size}: победитель - {verdict}, ходов {int(np.count_nonzero(s.board))}, "
                         f"статус «{gw.game.status.text()}», кадр {image.width()}x{image.height()}, "
                         f"{time.time() - started:.2f} с")
            if rules.outcome(s.board) is None:
                raise RuntimeError("партия не закончилась")
        window.close()
        app.processEvents()
        lines.append("ИТОГ: работает")
    except Exception:  # noqa: BLE001 - любая ошибка должна попасть в файл
        lines.append("ИТОГ: ошибка")
        lines.append(traceback.format_exc())
        code = 1
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return code


def main(argv=None):
    ap = argparse.ArgumentParser(description="Крестики-нолики с нейросетью")
    ap.add_argument("--selftest", metavar="ФАЙЛ", nargs="?", const="selftest.txt",
                    help="без окна сыграть сетью против бота и записать итог в файл")
    ap.add_argument("--offscreen", action="store_true", help="без экрана")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest(args.selftest)
    if args.offscreen:
        from aikit import offscreen
        offscreen.setup(force=True)
    from PySide6.QtWidgets import QApplication

    from game.ui.icon import app_icon
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(app_icon())
    window, _ = open_window()
    window.memory.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
