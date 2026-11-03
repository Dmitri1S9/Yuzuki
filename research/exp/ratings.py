"""Ординалы из попарных сравнений текста ("A defeated B", "A is stronger than B", ничья).

Bradley–Terry с ничьими по Davidson (1970), MAP с гауссовым приором на силу (L2) — приор держит конечными
персонажей "только побеждал" и даёт осмысленную шкалу в редких графах. Фит — диагональный Ньютон (без numpy,
чистый Python: десятки персонажей, сотни сравнений). Компоненты связности фитятся раздельно: между вселенными
без "мостов" сравнивать нельзя, это не баг, а свойство данных (см. REPORT.md: VS Battles tiers как общий приор).

    P(i > j) = πi / (πi + πj + ν√(πiπj)),  P(tie) = ν√(πiπj) / (...),  π = exp(θ)
"""
import math
from collections import defaultdict


def components(players: set[str], games: list[tuple[str, str, bool]]) -> list[set[str]]:
    adj = defaultdict(set)
    for a, b, _ in games:
        adj[a].add(b)
        adj[b].add(a)
    seen, comps = set(), []
    for p in sorted(players):
        if p in seen:
            continue
        stack, comp = [p], set()
        while stack:
            x = stack.pop()
            if x in comp:
                continue
            comp.add(x)
            stack.extend(adj[x] - comp)
        seen |= comp
        comps.append(comp)
    return comps


def fit(games: list[tuple[str, str, bool]], prior_sd: float = 1.0, prior_mean: dict[str, float] | None = None,
        iters: int = 2000, lr: float = 0.5) -> tuple[dict[str, float], float]:
    """games: (winner, loser, is_tie). Возвращает (θ по игрокам, ν). θ — лог-сила, сравнима только внутри компоненты."""
    prior_mean = prior_mean or {}
    players = {p for g in games for p in g[:2]}
    theta = {p: prior_mean.get(p, 0.0) for p in players}
    log_nu = math.log(0.5)
    # диагональный Ньютон: кривизна лог-правдоподобия ≤ 1/4 на игру + 1/sd² от приора -> шаг стабилен при любом числе игр
    n_games = defaultdict(int)
    for a, b, _ in games:
        n_games[a] += 1
        n_games[b] += 1
    curv = {p: n_games[p] / 4 + 1 / prior_sd ** 2 for p in players}
    for _ in range(iters):
        grad = {p: -(theta[p] - prior_mean.get(p, 0.0)) / prior_sd ** 2 for p in players}
        g_nu = 0.0
        nu = math.exp(log_nu)
        for a, b, tie in games:
            pa, pb = math.exp(theta[a]), math.exp(theta[b])
            t = nu * math.sqrt(pa * pb)
            z = pa + pb + t
            # d log z / d theta_a = (pa + t/2) / z
            da, db = (pa + t / 2) / z, (pb + t / 2) / z
            if tie:
                grad[a] += 0.5 - da
                grad[b] += 0.5 - db
                g_nu += 1 - t / z
            else:
                grad[a] += 1 - da
                grad[b] += -db
                g_nu += -t / z
        for p in players:
            theta[p] += lr * grad[p] / curv[p]
        log_nu += lr * g_nu / max(len(games), 1)
    return theta, math.exp(log_nu)


def tiers(theta: dict[str, float], n_tiers: int = 5) -> dict[str, int]:
    """Сила -> тир 1..n по квантилям внутри компоненты (1 = сильнейший)."""
    order = sorted(theta, key=theta.get, reverse=True)
    return {p: 1 + i * n_tiers // len(order) for i, p in enumerate(order)}
