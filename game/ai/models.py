"""Обученные сети и их паспорта из папки game/models (рядом с кодом или внутри сборки)."""
import json
import os
from functools import lru_cache

from game.ai import net

LEVELS = ("novice", "medium", "strong")
MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")


def resource(name):
    return os.path.join(MODELS_DIR, name)


@lru_cache(maxsize=None)
def load(size, level):
    return net.ValueNet.load(resource(f"{size}x{size}-{level}.npz"))


@lru_cache(maxsize=None)
def passport(size):
    with open(resource(f"{size}x{size}.json"), encoding="utf-8") as f:
        return json.load(f)
