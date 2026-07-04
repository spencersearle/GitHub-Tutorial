"""
World Cup 2026 winner-prediction model.

Pipeline
--------
1.  Team data — the 48-team field for the 2026 FIFA World Cup, each team tagged
    with its confederation and an Elo-style strength rating.  Elo ratings are
    themselves distilled from real historical results, so they carry genuine
    real-world signal about relative team strength.

2.  Machine-learning core — a scikit-learn ``PoissonRegressor`` is *trained* to
    map (attacking team rating, defending team rating, home flag) -> goals
    scored in a match.  Training data is a large sample of matches drawn from a
    calibrated generative process whose average scoring rate (~2.7 goals/game)
    and home advantage (~+0.25 goals) match observed international football.
    The regressor learns the strength -> goals relationship and is then used as
    the match engine.

3.  Monte-Carlo tournament — the full bracket (12 groups of 4, best-third
    qualification, then a 32-team single-elimination knockout) is simulated tens
    of thousands of times using the trained model.  Aggregating the outcomes
    gives every team's probability of winning the World Cup, reaching the final,
    and so on.

The script writes ``predictions.json`` next to itself, which the visualisation
layer turns into a readable dashboard.

Note: the field, group draw and ratings are a reproducible model projection, not
the official FIFA draw.  Swap in official numbers to re-run against reality.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.linear_model import PoissonRegressor

RNG_SEED = 2026
N_SIMULATIONS = 20_000

# ---------------------------------------------------------------------------
# 1. The 48-team field: (name, confederation, Elo strength rating)
# ---------------------------------------------------------------------------
TEAMS: list[tuple[str, str, float]] = [
    # CONMEBOL (South America)
    ("Argentina", "CONMEBOL", 2105),
    ("Brazil", "CONMEBOL", 2015),
    ("Uruguay", "CONMEBOL", 1930),
    ("Colombia", "CONMEBOL", 1960),
    ("Ecuador", "CONMEBOL", 1880),
    ("Paraguay", "CONMEBOL", 1820),
    ("Venezuela", "CONMEBOL", 1795),
    # UEFA (Europe)
    ("France", "UEFA", 2085),
    ("Spain", "UEFA", 2055),
    ("England", "UEFA", 2025),
    ("Portugal", "UEFA", 1995),
    ("Netherlands", "UEFA", 1985),
    ("Germany", "UEFA", 1965),
    ("Italy", "UEFA", 1945),
    ("Belgium", "UEFA", 1940),
    ("Croatia", "UEFA", 1900),
    ("Switzerland", "UEFA", 1870),
    ("Denmark", "UEFA", 1860),
    ("Austria", "UEFA", 1850),
    ("Turkey", "UEFA", 1825),
    ("Ukraine", "UEFA", 1830),
    ("Serbia", "UEFA", 1815),
    ("Norway", "UEFA", 1830),
    # CONCACAF (North/Central America) — hosts USA, Mexico, Canada
    ("USA", "CONCACAF", 1830),
    ("Mexico", "CONCACAF", 1810),
    ("Canada", "CONCACAF", 1800),
    ("Panama", "CONCACAF", 1720),
    ("Costa Rica", "CONCACAF", 1700),
    ("Jamaica", "CONCACAF", 1710),
    # AFC (Asia)
    ("Japan", "AFC", 1870),
    ("Iran", "AFC", 1810),
    ("South Korea", "AFC", 1800),
    ("Australia", "AFC", 1790),
    ("Saudi Arabia", "AFC", 1740),
    ("Qatar", "AFC", 1720),
    ("Iraq", "AFC", 1700),
    ("Uzbekistan", "AFC", 1710),
    # CAF (Africa)
    ("Morocco", "CAF", 1900),
    ("Senegal", "CAF", 1860),
    ("Nigeria", "CAF", 1830),
    ("Algeria", "CAF", 1820),
    ("Egypt", "CAF", 1810),
    ("Ivory Coast", "CAF", 1810),
    ("Cameroon", "CAF", 1790),
    ("Tunisia", "CAF", 1780),
    ("Ghana", "CAF", 1780),
    ("DR Congo", "CAF", 1760),
    # OFC (Oceania)
    ("New Zealand", "OFC", 1700),
]

HOSTS = {"USA", "Mexico", "Canada"}


# ---------------------------------------------------------------------------
# 2. Train the scikit-learn Poisson goal model
# ---------------------------------------------------------------------------
def train_goal_model(seed: int = RNG_SEED) -> PoissonRegressor:
    """Fit a PoissonRegressor that predicts goals scored in a match.

    Features per (attacker, defender) matchup:
        x0 = attacker rating (scaled, /100)
        x1 = defender rating (scaled, /100)
        x2 = home flag (1 if attacker at home, else 0)

    Training matches are sampled from a calibrated generative process so the
    learned coefficients reflect realistic international-football scoring.
    """
    rng = np.random.default_rng(seed)
    n = 40_000

    atk = rng.uniform(1650, 2150, n)
    dfd = rng.uniform(1650, 2150, n)
    home = rng.integers(0, 2, n)

    # Ground-truth generative log-rate. Calibrated so an even, neutral match
    # yields ~1.35 goals/team (~2.7 total) with a modest home edge.
    base = np.log(1.35)
    log_mu = base + 0.42 * (atk - dfd) / 100.0 + 0.25 * home
    goals = rng.poisson(np.exp(log_mu))

    X = np.column_stack([atk / 100.0, dfd / 100.0, home.astype(float)])
    model = PoissonRegressor(alpha=1e-6, max_iter=500)
    model.fit(X, goals)
    return model


def expected_goals(model: PoissonRegressor, atk_r, dfd_r, home) -> np.ndarray:
    """Vectorised expected-goals prediction from the trained model."""
    atk_r = np.atleast_1d(np.asarray(atk_r, dtype=float))
    dfd_r = np.atleast_1d(np.asarray(dfd_r, dtype=float))
    home = np.atleast_1d(np.asarray(home, dtype=float))
    X = np.column_stack([atk_r / 100.0, dfd_r / 100.0, home])
    return model.predict(X)


# ---------------------------------------------------------------------------
# 3. Group draw (deterministic, pot-based, confederation-aware)
# ---------------------------------------------------------------------------
def draw_groups(seed: int = RNG_SEED) -> list[list[int]]:
    """Draw 12 groups of 4 from four seeding pots.

    Pot 1 = 3 hosts + 9 strongest others; pots 2-4 by descending Elo.
    Applies the real constraint of at most one team per confederation per group
    (UEFA allowed up to two), using retries.
    """
    rng = np.random.default_rng(seed)
    idx = list(range(len(TEAMS)))

    hosts = [i for i in idx if TEAMS[i][0] in HOSTS]
    others = sorted(
        (i for i in idx if TEAMS[i][0] not in HOSTS),
        key=lambda i: TEAMS[i][2],
        reverse=True,
    )
    pot1 = hosts + others[:9]
    pot1.sort(key=lambda i: TEAMS[i][2], reverse=True)
    pot2, pot3, pot4 = others[9:21], others[21:33], others[33:]

    for _attempt in range(2000):
        groups: list[list[int]] = [[] for _ in range(12)]
        ok = True
        for pot in (pot1, pot2, pot3, pot4):
            order = list(pot)
            rng.shuffle(order)
            # Assign each team to a group slot without breaking the
            # confederation constraint.
            slots = list(range(12))
            placed = _assign_pot(order, groups, slots, rng)
            if not placed:
                ok = False
                break
        if ok and all(len(g) == 4 for g in groups):
            return groups
    raise RuntimeError("Could not build a valid group draw")


def _conf_ok(group: list[int], conf: str) -> bool:
    confs = [TEAMS[i][1] for i in group]
    limit = 2 if conf == "UEFA" else 1
    return confs.count(conf) < limit


def _assign_pot(order, groups, slots, rng) -> bool:
    """Greedy-with-backtracking assignment of one pot's teams to groups."""
    open_slots = [g for g in slots if len(groups[g]) < 4]
    rng.shuffle(open_slots)

    def backtrack(k: int, used: set[int]) -> bool:
        if k == len(order):
            return True
        team = order[k]
        conf = TEAMS[team][1]
        for g in open_slots:
            if g in used:
                continue
            if _conf_ok(groups[g], conf):
                groups[g].append(team)
                used.add(g)
                if backtrack(k + 1, used):
                    return True
                groups[g].pop()
                used.discard(g)
        return False

    return backtrack(0, set())


# ---------------------------------------------------------------------------
# 4. Match + tournament simulation
# ---------------------------------------------------------------------------
class Tournament:
    def __init__(self, model: PoissonRegressor, groups: list[list[int]], seed: int):
        self.model = model
        self.groups = groups
        self.rng = np.random.default_rng(seed)
        self.ratings = np.array([t[2] for t in TEAMS], dtype=float)

    def _play(self, a: int, b: int, neutral: bool = True) -> tuple[int, int]:
        """Return (goals_a, goals_b) for a 90-minute match."""
        # Hosts get a home flag; all others neutral.
        ha = 0.0 if neutral else float(TEAMS[a][0] in HOSTS)
        hb = 0.0 if neutral else float(TEAMS[b][0] in HOSTS)
        la = expected_goals(self.model, self.ratings[a], self.ratings[b], ha)[0]
        lb = expected_goals(self.model, self.ratings[b], self.ratings[a], hb)[0]
        return int(self.rng.poisson(la)), int(self.rng.poisson(lb))

    def _knockout(self, a: int, b: int) -> int:
        """Return winner of a knockout tie (extra time + penalties modelled)."""
        ga, gb = self._play(a, b, neutral=False)
        if ga > gb:
            return a
        if gb > ga:
            return b
        # Draw -> extra time / penalties: decide via Elo win expectation.
        ra, rb = self.ratings[a], self.ratings[b]
        p_a = 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))
        return a if self.rng.random() < p_a else b

    def simulate(self) -> tuple[int, list[int], list[int], list[int]]:
        """Run one full tournament.

        Returns (champion, finalists, semifinalists, quarterfinalists).
        """
        standings: dict[int, dict] = {}
        thirds: list[tuple] = []
        winners, runners = [], []

        for group in self.groups:
            tbl = {i: {"pts": 0, "gd": 0, "gf": 0} for i in group}
            for x in range(4):
                for y in range(x + 1, 4):
                    a, b = group[x], group[y]
                    ga, gb = self._play(a, b, neutral=False)
                    tbl[a]["gf"] += ga
                    tbl[b]["gf"] += gb
                    tbl[a]["gd"] += ga - gb
                    tbl[b]["gd"] += gb - ga
                    if ga > gb:
                        tbl[a]["pts"] += 3
                    elif gb > ga:
                        tbl[b]["pts"] += 3
                    else:
                        tbl[a]["pts"] += 1
                        tbl[b]["pts"] += 1
            ranked = sorted(
                group,
                key=lambda i: (
                    tbl[i]["pts"],
                    tbl[i]["gd"],
                    tbl[i]["gf"],
                    self.rng.random(),
                ),
                reverse=True,
            )
            winners.append(ranked[0])
            runners.append(ranked[1])
            thirds.append((ranked[2], tbl[ranked[2]]))
            standings.update(tbl)

        # Best 8 of 12 third-placed teams advance.
        thirds.sort(
            key=lambda t: (t[1]["pts"], t[1]["gd"], t[1]["gf"], self.rng.random()),
            reverse=True,
        )
        best_thirds = [t[0] for t in thirds[:8]]

        # Seed the 32 qualifiers: winners strongest, then runners, then thirds;
        # within each tier by Elo. Standard bracket pairing (1v32, 2v31, ...)
        # keeps the strongest apart until late rounds.
        qualifiers = (
            sorted(winners, key=lambda i: self.ratings[i], reverse=True)
            + sorted(runners, key=lambda i: self.ratings[i], reverse=True)
            + sorted(best_thirds, key=lambda i: self.ratings[i], reverse=True)
        )
        quarterfinalists: list[int] = []
        semifinalists: list[int] = []
        finalists: list[int] = []

        bracket = qualifiers
        round_no = 0
        while len(bracket) > 1:
            n = len(bracket)
            nxt = []
            for i in range(n // 2):
                a, b = bracket[i], bracket[n - 1 - i]
                nxt.append(self._knockout(a, b))
            if len(nxt) == 4:
                semifinalists = list(nxt)
            elif len(nxt) == 8:
                quarterfinalists = list(nxt)
            elif len(nxt) == 2:
                finalists = list(nxt)
            bracket = nxt
            round_no += 1

        champion = bracket[0]
        return champion, finalists, semifinalists, quarterfinalists


# ---------------------------------------------------------------------------
# 5. Run the Monte-Carlo experiment and write predictions.json
# ---------------------------------------------------------------------------
def main() -> None:
    print("Training scikit-learn Poisson goal model...")
    model = train_goal_model()
    coefs = model.coef_
    print(
        f"  learned coefficients: attack={coefs[0]:+.3f}  "
        f"defence={coefs[1]:+.3f}  home={coefs[2]:+.3f}"
    )

    groups = draw_groups()
    print(f"Drew 12 groups. Running {N_SIMULATIONS:,} tournament simulations...")

    champ = np.zeros(len(TEAMS))
    final = np.zeros(len(TEAMS))
    semi = np.zeros(len(TEAMS))
    quarter = np.zeros(len(TEAMS))

    for s in range(N_SIMULATIONS):
        t = Tournament(model, groups, seed=RNG_SEED + s + 1)
        c, fs, ss, qs = t.simulate()
        champ[c] += 1
        for i in fs:
            final[i] += 1
        for i in ss:
            semi[i] += 1
        for i in qs:
            quarter[i] += 1
        if (s + 1) % 2000 == 0:
            print(f"  {s + 1:,}/{N_SIMULATIONS:,} simulations complete")

    results = []
    for i, (name, conf, elo) in enumerate(TEAMS):
        results.append(
            {
                "team": name,
                "confederation": conf,
                "elo": elo,
                "champion_pct": round(100 * champ[i] / N_SIMULATIONS, 2),
                "final_pct": round(100 * final[i] / N_SIMULATIONS, 2),
                "semifinal_pct": round(100 * semi[i] / N_SIMULATIONS, 2),
                "quarterfinal_pct": round(100 * quarter[i] / N_SIMULATIONS, 2),
            }
        )
    results.sort(key=lambda r: r["champion_pct"], reverse=True)

    group_out = []
    for gi, group in enumerate(groups):
        group_out.append(
            {
                "name": f"Group {chr(ord('A') + gi)}",
                "teams": [
                    {"team": TEAMS[i][0], "confederation": TEAMS[i][1], "elo": TEAMS[i][2]}
                    for i in group
                ],
            }
        )

    payload = {
        "meta": {
            "simulations": N_SIMULATIONS,
            "model": "scikit-learn PoissonRegressor + Elo strength + Monte Carlo",
            "learned_coefficients": {
                "attack": round(float(coefs[0]), 4),
                "defence": round(float(coefs[1]), 4),
                "home": round(float(coefs[2]), 4),
            },
            "generated": "2026 World Cup projection",
        },
        "predictions": results,
        "groups": group_out,
    }

    out = Path(__file__).with_name("predictions.json")
    out.write_text(json.dumps(payload, indent=2))
    print(f"\nWrote {out}")
    print("\nTop 10 title favourites:")
    for r in results[:10]:
        print(f"  {r['team']:<14} {r['champion_pct']:>5.1f}%")


if __name__ == "__main__":
    main()
