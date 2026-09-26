"""Обучение сети самоигрой: с нуля, только по исходам партий.

    python -m train.selfplay --size 3
    python -m train.selfplay --size 5

Сеть играет сама с собой пачкой партий сразу (все ходы-кандидаты всех партий - один
проход сети), с долей случайных ходов ε от 0.3 к 0.05. После пачки каждая позиция
получает цель - λ-возврат (см. lambda_returns), 8 симметрий поля делают из одной
позиции восемь примеров, сеть учится MSE и Adam на буфере последних позиций.

По ходу обучения сохраняются снимки уровней («новичок», «средний», «сильный» - конец),
каждый проверяется против ботов; итоги и кривая обучения пишутся в паспорт
models/<поле>.json, веса - в models/<поле>-<уровень>.npz.
"""
import os

# Процессор делят несколько обучений: numpy не должен забирать все ядра. Ставится до
# импорта numpy, иначе библиотека BLAS уже запущена со своим числом потоков.
for _var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_var, "4")

import argparse  # noqa: E402
import json  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import bots, net, rules  # noqa: E402
from nn import losses  # noqa: E402
from nn.optim import Adam  # noqa: E402

LEVEL_NAMES = {"novice": "новичок", "medium": "средний", "strong": "сильный"}

# Настройки, с которыми обучены модели в models/ (подобраны по проверкам, см. паспорта).
PRESETS = {
    3: {"games": 30000, "snapshots": {"novice": 600, "medium": 3000}, "batch_games": 64,
        "lam": 0.7, "gamma": 0.95, "soft": 0.1, "lr": 1e-3, "updates": 8, "batch": 256,
        "buffer": 60000, "eval_every": 1000, "net": {"hidden": 64}},
    5: {"games": 40000, "snapshots": {"novice": 1000, "medium": 6000}, "batch_games": 64,
        "lam": 0.7, "gamma": 0.97, "soft": 0.1, "lr": 5e-4, "updates": 8, "batch": 256,
        "buffer": 100000, "eval_every": 2000, "net": {"channels": 32, "conv_layers": 3, "head": 64}},
}


# --- самоигра ---


def play_batch(model, n, games, eps, rng, lam=0.7, gamma=0.95, soft=0.1):
    """Партии сети против самой себя, все сразу. Возвращает (позиции после хода глазами
    сходившего (N, n, n) int8, их цели (N,) float32, {x_wins, o_wins, draws}).

    На каждом шаге для партии запоминается backup - оценка лучшего ответа для того, кто
    ходит сейчас: (1 - soft) * лучший ход + soft * средний. Средний добавлен ради игры
    против слабых: из равных по счёту ходов сеть выберет тот, где ошибка соперника
    вероятнее. Проигрышный ход он не оправдает - проигрыш весит -1, прибавка не больше soft.
    Конечные позиции оцениваются по правилам: победа 1, ничья 0."""
    k = rules.win_length(n)
    boards = np.zeros((games, n * n), np.int8)
    alive = np.ones(games, bool)
    steps, positions = [], []
    info = {"x_wins": 0, "o_wins": 0, "draws": 0}
    mover = rules.X
    while alive.any():
        idx = np.flatnonzero(alive)
        cur = boards[idx]
        g_of, cell = np.nonzero(cur == 0)          # кандидаты: партии идут подряд
        cand = cur[g_of]
        cand[np.arange(len(g_of)), cell] = mover
        view = (cand * np.int8(mover)).reshape(-1, n, n)
        v = model.value(net.encode(view))
        win = rules.winners(view, k) == 1
        full = (cand != 0).all(axis=1)
        v_star = np.where(win, 1.0, np.where(full, 0.0, v))

        counts = np.bincount(g_of, minlength=len(idx))
        starts = np.concatenate([[0], np.cumsum(counts)[:-1]])
        best_star = np.maximum.reduceat(v_star, starts)
        mean_star = np.add.reduceat(v_star, starts) / counts
        order = np.lexsort((-v, g_of))             # в каждой партии лучший по сети первым
        greedy = order[starts]
        explored = rng.random(len(idx)) < eps
        chosen = np.where(explored, starts + rng.integers(0, counts), greedy)

        terminal = win[chosen] | full[chosen]
        steps.append({"games": idx, "terminal": terminal,
                      "outcome": win[chosen].astype(np.float64),
                      "backup": (1 - soft) * best_star + soft * mean_star,
                      "explored": explored})
        positions.append(view[chosen])
        boards[idx] = cand[chosen]
        done = idx[terminal]
        alive[done] = False
        wins = int(win[chosen].sum())
        info["x_wins" if mover == rules.X else "o_wins"] += wins
        info["draws"] += int(terminal.sum()) - wins
        mover = -mover
    targets = lambda_returns(steps, games, lam, gamma)
    return np.concatenate(positions), np.concatenate(targets).astype(np.float32), info


def lambda_returns(steps, games, lam, gamma):
    """Цели для каждой позиции, от конца партии к началу.

    Конец партии - исход для сходившего (победа 1, ничья 0). Иначе
        G_t = gamma * ((1 - lam) * (-backup_{t+1}) + lam * (-G_{t+1})),
    минус - потому что следующий ход делает соперник. lam = 1 - чистый итог партии с
    дисконтом, lam = 0 - только лучший ответ соперника (как в минимаксе). Если ответ был
    случайным (exploration), след обрывается: его исход ничего не говорит о позиции, и
    цель берётся из лучшего ответа."""
    g_next = np.zeros(games)
    backup_next = np.zeros(games)
    explored_next = np.zeros(games, bool)
    out = [None] * len(steps)
    for t in range(len(steps) - 1, -1, -1):
        s = steps[t]
        ids = s["games"]
        cont_mc = -g_next[ids]
        cont_best = -backup_next[ids]
        cont = np.where(explored_next[ids], cont_best, (1 - lam) * cont_best + lam * cont_mc)
        g = np.where(s["terminal"], s["outcome"], gamma * cont)
        out[t] = g
        g_next[ids] = g
        backup_next[ids] = s["backup"]
        explored_next[ids] = s["explored"]
    return out


def augment(boards, targets):
    """8 симметрий каждой позиции с той же целью: (N, n, n) -> (8N, n, n)."""
    sym = np.concatenate([net.transform(boards, i) for i in range(8)])
    order = np.arange(8 * len(boards)).reshape(8, -1).T.reshape(-1)
    return np.ascontiguousarray(sym[order]), np.repeat(targets, 8)


# --- проверки ---


def rate(res):
    games = res["wins"] + res["losses"] + res["draws"]
    return {"games": games, "wins": res["wins"], "losses": res["losses"], "draws": res["draws"],
            "win_rate": round(res["wins"] / max(games, 1), 4)}


def evaluate(model, n, games, seed=0, full=True):
    """Проверка сети против ботов. Сеть ходит без случайности; сиды фиксированы, поэтому
    паспорт можно пересчитать и сверить."""
    player = net.NetPlayer(model)
    rng = np.random.default_rng(seed)
    checks = {"vs_random": rate(bots.match(player, bots.RandomBot(rng), n, games)),
              "vs_bot": rate(bots.match(player, bots.WinOrBlockBot(rng), n, games))}
    if full:
        checks["vs_random_first"] = rate(bots.match(player, bots.RandomBot(rng), n, games, colors="x"))
        if n == 3:
            checks["vs_minimax"] = rate(bots.match(player, bots.MinimaxBot(rng), n, games))
    return checks


# --- обучение ---


def train(n, games, seed=0, snapshots=None, batch_games=64, lam=0.7, gamma=0.95, soft=0.1,
          eps_start=0.3, eps_end=0.05, lr=1e-3, updates=8, batch=256, buffer=60000,
          eval_every=1000, eval_games=100, final_games=200, out_dir=None, log=print, net_args=None):
    """Обучить сеть поля n x n на games партиях. snapshots - {уровень: после скольких
    партий снять}, «сильный» - конец. out_dir - куда писать веса и паспорт (None - никуда).
    Возвращает (сеть в конце, паспорт)."""
    rng = np.random.default_rng(seed)
    model = net.ValueNet(n, rng=np.random.default_rng(seed + 1), **(net_args or {}))
    opt = Adam(model.params(), lr=lr)
    buf_b = np.zeros((buffer, n, n), np.int8)
    buf_t = np.zeros(buffer, np.float32)
    filled, head = 0, 0
    snapshots = dict(snapshots or {})
    taken, curve = {}, []
    played, started = 0, time.time()
    next_eval = eval_every or None

    def say(text):
        if log:
            log(text)

    while played < games:
        eps = eps_start + (eps_end - eps_start) * min(1.0, played / max(games * 0.8, 1))
        # пачка не перескакивает точку проверки и снимка - они ровно на своём числе партий
        stops = [games] + ([next_eval] if next_eval else []) + \
            [at for key, at in snapshots.items() if key not in taken and at > played]
        count = min(batch_games, min(stops) - played)
        boards, targets, info = play_batch(model, n, count, eps, rng, lam, gamma, soft)
        played += count
        boards, targets = augment(boards, targets)
        pos = (head + np.arange(len(boards))) % buffer
        buf_b[pos], buf_t[pos] = boards, targets
        head = (head + len(boards)) % buffer
        filled = min(buffer, filled + len(boards))
        loss = 0.0
        for _ in range(updates):
            pick = rng.integers(0, filled, size=min(batch, filled))
            x = net.encode(buf_b[pick])
            pred = model.forward(x)
            loss, grad = losses.mse(pred, buf_t[pick][:, None])
            model.backward(grad)
            opt.step()

        for key, at in snapshots.items():
            if key not in taken and played >= at:
                taken[key] = (played, snapshot_arrays(model))
        if next_eval and played >= next_eval:
            checks = evaluate(model, n, eval_games, seed=played, full=False)
            curve.append({"games": played, "vs_random": checks["vs_random"]["win_rate"],
                          "vs_bot": checks["vs_bot"]["win_rate"],
                          "vs_bot_losses": round(checks["vs_bot"]["losses"] / max(eval_games, 1), 4)})
            say(f"партий {played:6d}  ε {eps:.3f}  потеря {loss:.4f}  "
                f"против случайного {checks['vs_random']['win_rate']:.2f}  "
                f"против бота {checks['vs_bot']['win_rate']:.2f}/{curve[-1]['vs_bot_losses']:.2f}  "
                f"{time.time() - started:.0f} с")
            next_eval += eval_every

    taken["strong"] = (played, snapshot_arrays(model))
    passport = {
        "field": f"{n}x{n}", "size": n, "win_length": rules.win_length(n),
        "network": {**model.config, "parameters": model.count()},
        "method": {"targets": "λ-возврат по цепочке лучших ответов, дисконт, обрыв на случайном ответе",
                   "lambda": lam, "gamma": gamma, "soft": soft, "eps_start": eps_start,
                   "eps_end": eps_end, "lr": lr, "batch_games": batch_games, "updates": updates,
                   "batch": batch, "buffer": buffer, "symmetries": 8, "seed": seed},
        "games": played, "train_seconds": round(time.time() - started, 1),
        "levels": [], "curve": curve,
    }
    order = [k for k in ("novice", "medium") if k in taken] + ["strong"]
    for key in order:
        at, arrays = taken[key]
        level_model = net.ValueNet(n, **(net_args or {}))
        restore_arrays(level_model, arrays)
        checks = evaluate(level_model, n, final_games, seed=1000 + n)
        entry = {"key": key, "name": LEVEL_NAMES[key], "games": at,
                 "file": f"{n}x{n}-{key}.npz", "checks": checks}
        passport["levels"].append(entry)
        say(f"{LEVEL_NAMES[key]:8s} ({at} партий): " + ", ".join(
            f"{name} {c['wins']}/{c['draws']}/{c['losses']}" for name, c in checks.items()))
        if out_dir is not None:
            Path(out_dir).mkdir(parents=True, exist_ok=True)
            level_model.save(Path(out_dir) / entry["file"])
    if out_dir is not None:
        path = Path(out_dir) / f"{n}x{n}.json"
        path.write_text(json.dumps(passport, ensure_ascii=False, indent=1), encoding="utf-8")
    return model, passport


def snapshot_arrays(model):
    return [p.copy() for _, p, _ in model.params()]


def restore_arrays(model, arrays):
    for (_, p, _), a in zip(model.params(), arrays):
        p[...] = a


def main():
    ap = argparse.ArgumentParser(description="Обучение сети крестиков-ноликов самоигрой")
    ap.add_argument("--size", type=int, choices=(3, 5), required=True)
    ap.add_argument("--games", type=int, help="сколько партий (по умолчанию - из PRESETS)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models"))
    args = ap.parse_args()
    p = dict(PRESETS[args.size])
    games = args.games or p.pop("games")
    p.pop("games", None)
    net_args = p.pop("net")
    train(args.size, games, seed=args.seed, out_dir=args.out, net_args=net_args, **p)


if __name__ == "__main__":
    main()
