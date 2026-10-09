"""TicTacToeAi: крестики-нолики 3×3 и 5×5 против нейросети, которая научилась играть сама.

Вход игры по контракту PythonAiGames: GAME_INFO и create_widget(ctx). Qt загружается
только в create_widget - правила, сеть и обучение работают без него.
"""
from game.version import VERSION

GAME_INFO = {
    "id": "tictactoe",
    "title": {"ru": "Крестики-нолики", "en": "Tic-tac-toe"},
    "summary": {"ru": "Поля 3×3 и 5×5 против нейросети, которая научилась играть сама",
                "en": "3×3 and 5×5 boards against a neural network that taught itself"},
    "preview": "docs/preview_menu.png",
    "version": VERSION,
}

APP_NAME = "TicTacToeAi"


def create_widget(ctx):
    """ctx: aikit.Context. Виджет с меню, партией, статистикой и настройками."""
    from game.ui.widget import GameWidget
    return GameWidget(ctx)
