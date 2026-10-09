"""Настройки игры. Сохраняются сразу при изменении; каждое плохое поле в файле заменяется
значением по умолчанию само по себе, остальные остаются.

Тема, язык и громкость - общие, они в ctx (оболочка или окно отдельного запуска); здесь
только своё: задержка хода сети, «Мысли сети», первый ход, последние поле и уровень.
Файл 1.0.x с полями theme и volume читается: лишние поля пропускаются."""
from dataclasses import asdict, dataclass, fields

from aikit.storage import is_int, load_json, save_json

FIRST = ("me", "net", "alternate")
LEVELS = ("novice", "medium", "strong")
SIZES = (3, 5)


@dataclass
class Settings:
    delay_ms: int = 450         # пауза перед ходом сети, 0..2000
    show_thoughts: bool = False
    first: str = "me"           # кто ходит первым: я, сеть, по очереди
    size: int = 3               # последнее выбранное поле
    level: str = "strong"       # последний выбранный уровень

    @staticmethod
    def valid(name, value):
        checks = {
            "delay_ms": lambda v: is_int(v) and 0 <= v <= 2000,
            "show_thoughts": lambda v: isinstance(v, bool),
            "first": lambda v: v in FIRST,
            "size": lambda v: is_int(v) and v in SIZES,
            "level": lambda v: v in LEVELS,
        }
        try:
            return checks[name](value)
        except TypeError:           # нехэшируемое значение в проверке «in»
            return False

    @classmethod
    def load(cls, path):
        data = load_json(path)
        s = cls()
        if isinstance(data, dict):
            for f in fields(cls):
                if f.name in data and cls.valid(f.name, data[f.name]):
                    setattr(s, f.name, data[f.name])
        return s

    def save(self, path):
        return save_json(path, asdict(self))
