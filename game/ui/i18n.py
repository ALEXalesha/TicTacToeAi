"""Строки интерфейса на русском и английском. Язык - ctx.lang, меняется на лету.

Ключи - короткие имена; подстановки - через format: t("score_caption", field=..., ...).
Тест проверяет, что у обоих языков одни и те же ключи.
"""
from aikit.i18n import Translator

RU = {
    # меню
    "title": "Крестики-нолики",
    "subtitle": "против нейросети, которая научилась играть сама",
    "play": "Играть",
    "stats": "Статистика",
    "settings": "Настройки",
    "quit": "Выход",
    "footer": "версия {version} · поля 3×3 и 5×5 · сеть на numpy, без готовых библиотек",
    # партия
    "field": "Поле",
    "net_level": "Уровень сети",
    "first_move": "Первый ход",
    "first_me": "Я",
    "first_net": "Сеть",
    "first_alternate": "По очереди",
    "level_novice": "новичок",
    "level_medium": "средний",
    "level_strong": "сильный",
    "rule_3": "три в ряд",
    "rule_5": "четыре в ряд",
    "wins_small": "победы",
    "draws_small": "ничьи",
    "losses_small": "поражения",
    "thoughts": "Мысли сети",
    "thoughts_hint": "Оценка клеток для того, чья очередь: +1 - победа, −1 - поражение",
    "again": "Ещё раз",
    "to_menu": "В меню",
    "your_move": "Ваш ход",
    "net_thinks": "Сеть думает…",
    "mark_x": "крестиками (X)",
    "mark_o": "ноликами (O)",
    "playing": "Вы играете {mark}, нужно {rule}. Сеть: {level}.",
    "win": "Победа!",
    "loss": "Поражение",
    "draw": "Ничья",
    "tail_win": "Вы обыграли сеть.",
    "tail_loss": "Сеть собрала линию.",
    "tail_draw": "Поле заполнено, линии нет ни у кого.",
    "played": "{tail} Вы играли {mark}.",
    "games_1": "партия",
    "games_2": "партии",
    "games_5": "партий",
    "score_caption": "{field}, {level}: {games} {word}",
    "streak": ", серия побед {streak}",
    "keys_3": "Мышь или цифры 1–9 · R - ещё раз · Esc - меню",
    "keys_5": "Ход мышью · R - ещё раз · Esc - меню",
    # статистика
    "your_games": "Ваши партии",
    "total_games": "партий",
    "total_wins": "побед",
    "total_draws": "ничьих",
    "total_losses": "поражений",
    "total_best": "лучшая серия побед",
    "col_field_level": "Поле и уровень сети",
    "col_games": "Партии",
    "col_wins": "Победы",
    "col_losses": "Поражения",
    "col_draws": "Ничьи",
    "col_streak": "Серия",
    "col_best": "Лучшая серия",
    "how_learned": "Как сеть училась",
    "net_checks": "Проверки сети",
    "col_level": "Уровень",
    "col_train_games": "Партий обучения",
    "col_vs_random": "Против случайного",
    "col_vs_bot": "Против бота",
    "col_vs_minimax": "Против минимакса",
    "kind_dense": "плотная сеть 18 → {h} → {h} → 1",
    "kind_conv": "свёртки 3×3 (2 → {layers})",
    "kind_head": ", плотный слой {head} → 1",
    "seconds": "{n} с",
    "minutes": "{n} мин",
    "learn_caption": ("Поле {field}, {rule}. Сеть: {kind}, {params} весов. Она сыграла сама с собой "
                      "{games} партий за {took}; ни одной стратегии ей не давали. "
                      "Линии - доля побед сети по ходу обучения, пунктир - где сняты уровни."),
    "checks_caption": ("По {games} партий на проверку, половину сеть ходит первой. Числа: доля побед, "
                       "затем победы / ничьи / поражения. Бот «выиграй или помешай» смотрит на ход вперёд."),
    "minimax_caption": " Минимакс перебирает всю игру и не проигрывает никогда.",
    "safe_caption": (" Полным перебором всех ходов соперника проверено: уровень {names} не проигрывает "
                     "никому, ни крестиками, ни ноликами."),
    "quote": "«{}»",
    # график
    "thousands": "{n:g} тыс.",
    "vs_random": "против случайного",
    "vs_bot": "против бота «выиграй или помешай»",
    "no_data": "нет данных",
    "selfplay_games": "партий самоигры",
    # настройки
    "volume": "Громкость",
    "volume_hint": "Звуки ходов и конца партии",
    "theme": "Тема",
    "theme_hint": "Тёмная или светлая",
    "theme_dark": "Тёмная",
    "theme_light": "Светлая",
    "language": "Язык",
    "language_hint": "Русский или английский",
    "delay": "Задержка хода сети",
    "delay_hint": "Пауза перед ходом, чтобы его было видно",
    "delay_value": "{s} с",
    "thoughts_title": "Мысли сети",
    "thoughts_settings_hint": "Оценка каждой свободной клетки цветом и числом",
    "show": "Показывать",
    "default_first": "Первый ход по умолчанию",
    "default_first_hint": "Кто ходит первым, когда нажато «Играть»",
    "saved_at_once": "Всё сохраняется сразу.",
}

EN = {
    "title": "Tic-tac-toe",
    "subtitle": "against a neural network that taught itself to play",
    "play": "Play",
    "stats": "Statistics",
    "settings": "Settings",
    "quit": "Quit",
    "footer": "version {version} · 3×3 and 5×5 boards · the network is plain numpy, no ready-made libraries",
    "field": "Board",
    "net_level": "Network level",
    "first_move": "First move",
    "first_me": "Me",
    "first_net": "Network",
    "first_alternate": "Take turns",
    "level_novice": "novice",
    "level_medium": "medium",
    "level_strong": "strong",
    "rule_3": "three in a row",
    "rule_5": "four in a row",
    "wins_small": "wins",
    "draws_small": "draws",
    "losses_small": "losses",
    "thoughts": "Network's thoughts",
    "thoughts_hint": "Cell values for the side to move: +1 is a win, −1 is a loss",
    "again": "Again",
    "to_menu": "Menu",
    "your_move": "Your move",
    "net_thinks": "The network is thinking…",
    "mark_x": "crosses (X)",
    "mark_o": "noughts (O)",
    "playing": "You play {mark} and need {rule}. Network: {level}.",
    "win": "Victory!",
    "loss": "Defeat",
    "draw": "Draw",
    "tail_win": "You beat the network.",
    "tail_loss": "The network made a line.",
    "tail_draw": "The board is full and nobody has a line.",
    "played": "{tail} You played {mark}.",
    "games_1": "game",
    "games_2": "games",
    "games_5": "games",
    "score_caption": "{field}, {level}: {games} {word}",
    "streak": ", win streak {streak}",
    "keys_3": "Mouse or digits 1–9 · R - again · Esc - menu",
    "keys_5": "Move with the mouse · R - again · Esc - menu",
    "your_games": "Your games",
    "total_games": "games",
    "total_wins": "wins",
    "total_draws": "draws",
    "total_losses": "losses",
    "total_best": "best win streak",
    "col_field_level": "Board and network level",
    "col_games": "Games",
    "col_wins": "Wins",
    "col_losses": "Losses",
    "col_draws": "Draws",
    "col_streak": "Streak",
    "col_best": "Best streak",
    "how_learned": "How the network learned",
    "net_checks": "Network checks",
    "col_level": "Level",
    "col_train_games": "Training games",
    "col_vs_random": "Vs random",
    "col_vs_bot": "Vs bot",
    "col_vs_minimax": "Vs minimax",
    "kind_dense": "dense network 18 → {h} → {h} → 1",
    "kind_conv": "3×3 convolutions (2 → {layers})",
    "kind_head": ", dense layer {head} → 1",
    "seconds": "{n} s",
    "minutes": "{n} min",
    "learn_caption": ("Board {field}, {rule}. Network: {kind}, {params} weights. It played {games} games "
                      "against itself in {took}; it was never taught any strategy. "
                      "The lines are the network's win rate during training, the dashes mark where the levels were taken."),
    "checks_caption": ("{games} games per check, the network moves first in half of them. Numbers: win rate, "
                       "then wins / draws / losses. The \"win or block\" bot looks one move ahead."),
    "minimax_caption": " Minimax searches the whole game and never loses.",
    "safe_caption": (" A full search over every opponent move proves that level {names} never loses to "
                     "anyone, neither with crosses nor with noughts."),
    "quote": "\"{}\"",
    "thousands": "{n:g}k",
    "vs_random": "vs random",
    "vs_bot": "vs the \"win or block\" bot",
    "no_data": "no data",
    "selfplay_games": "self-play games",
    "volume": "Volume",
    "volume_hint": "Sounds of moves and of the game end",
    "theme": "Theme",
    "theme_hint": "Dark or light",
    "theme_dark": "Dark",
    "theme_light": "Light",
    "language": "Language",
    "language_hint": "Russian or English",
    "delay": "Network move delay",
    "delay_hint": "A pause before the move so you can see it",
    "delay_value": "{s} s",
    "thoughts_title": "Network's thoughts",
    "thoughts_settings_hint": "The value of every free cell as a colour and a number",
    "show": "Show",
    "default_first": "Default first move",
    "default_first_hint": "Who moves first when you press Play",
    "saved_at_once": "Everything is saved at once.",
}

TABLES = {"ru": RU, "en": EN}
LANG_NAMES = {"ru": "Русский", "en": "English"}


def translator(lang):
    return Translator(TABLES, lang)


def plural_key(n, lang):
    """Ключ слова «партия» для числа n: games_1 / games_2 / games_5 (по-русски три формы)."""
    n = abs(n)
    if lang == "en":
        return "games_1" if n == 1 else "games_5"
    if n % 10 == 1 and n % 100 != 11:
        return "games_1"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "games_2"
    return "games_5"


def number(n, lang):
    """12345 -> «12 345» по-русски (неразрывный пробел), «12,345» по-английски."""
    return f"{n:,}" if lang == "en" else f"{n:,}".replace(",", " ")
