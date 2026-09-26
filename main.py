"""Крестики-нолики с нейросетью.

    python main.py                         # игра
    python main.py --selftest итог.txt     # самопроверка без экрана: партии сети против бота

Самопроверка нужна прежде всего собранному exe: он без консоли, поэтому итог пишется в
файл. Окно создаётся offscreen, данные игрока - во временной папке, статистику игрока она
не трогает.
"""
import argparse
import os
import sys
import tempfile
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def selftest(out_path):
    lines = []
    code = 0
    try:
        import offscreen
        offscreen.setup(force=True)
        os.environ["TICTACTOEAI_HOME"] = tempfile.mkdtemp(prefix="tictactoeai-selftest-")
        import numpy as np
        from PySide6.QtWidgets import QApplication

        import paths
        from core import bots, rules
        from game.app import MainWindow
        from game.version import VERSION

        app = QApplication.instance() or QApplication([])
        window = MainWindow()
        window.change_setting("delay_ms", 0)
        window.show()
        lines.append(f"TicTacToeAi {VERSION} самопроверка")
        lines.append(f"собранная версия: {'да' if paths.frozen() else 'нет'}")
        bot = bots.WinOrBlockBot(np.random.default_rng(7))
        for size in (3, 5):
            started = time.time()
            window.start_play()
            window.game.set_first("me")          # «я» - это бот, сеть играет ноликами
            window.game.set_level("strong")
            window.game.set_size(size)
            s = window.game.session
            while s.result is None:
                if s.human_turn():
                    window.game.on_cell(*bot.move(s.board))
                else:
                    window.game.net_turn(window.game.token)
            image = window.grab().toImage()
            if image.isNull() or image.width() < 100:
                raise RuntimeError("окно не нарисовалось")
            verdict = {"win": "бот", "loss": "сеть", "draw": "ничья"}[s.outcome_for_human()]
            lines.append(f"{size}x{size}: победитель - {verdict}, ходов {int(np.count_nonzero(s.board))}, "
                         f"статус «{window.game.status.text()}», кадр {image.width()}x{image.height()}, "
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
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest(args.selftest)
    from game.app import run
    return run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
