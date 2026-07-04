"""
World Cup 2026 winner-prediction model — LIVE knockout edition.

Snapshot: 4 July 2026, Round of 16.  The group stage and Round of 32 are already
played; 16 teams remain.  Rather than guessing a pre-tournament field, this model
simulates the tournament *forward from the real Round-of-16 bracket* — the most
relevant possible prediction of who lifts the trophy from here.

Pipeline
--------
1.  Live state — the 16 teams still alive and the *actual* fixed knockout bracket
    (sourced from the live 2026 World Cup, see README for citations).  Each team
    carries an Elo-style strength rating reflecting current form.

2.  Machine-learning core — a scikit-learn ``PoissonRegressor`` is trained to map
    (attacking rating, defending rating, home flag) -> goals scored, calibrated to
    realistic international scoring (~2.7 goals/game, host home edge).

3.  Monte-Carlo knockout — the remaining bracket (Round of 16 -> Quarterfinals ->
    Semifinals -> Final, with extra time and penalties on draws) is simulated
    50,000 times.  Each team's share of simulated titles is its probability of
    winning the World Cup from the current position.

Writes ``predictions.json`` next to this file.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from sklearn.linear_model import PoissonRegressor

RNG_SEED = 2026
N_SIMULATIONS = 50_000

# North-American hosts get a home edge in every match (playing on home soil).
HOSTS = {"USA", "Mexico", "Canada"}

# ---------------------------------------------------------------------------
# 1. Live state — 16 teams still alive, with current strength ratings.
#    (name -> confederation, Elo). Ratings reflect current form / market as of
#    4 July 2026: France & Argentina co-favourites, Spain next, then Brazil,
#    England, Portugal, Colombia, Morocco...
# ---------------------------------------------------------------------------
TEAMS: dict[str, tuple[str, float]] = {
    "France": ("UEFA", 2090),
    "Argentina": ("CONMEBOL", 2080),
    "Spain": ("UEFA", 2055),
    "Brazil": ("CONMEBOL", 2010),
    "England": ("UEFA", 2000),
    "Portugal": ("UEFA", 1990),
    "Colombia": ("CONMEBOL", 1955),
    "Morocco": ("CAF", 1900),
    "Belgium": ("UEFA", 1925),
    "Switzerland": ("UEFA", 1855),
    "Norway": ("UEFA", 1850),
    "USA": ("CONCACAF", 1825),
    "Paraguay": ("CONMEBOL", 1815),
    "Mexico": ("CONCACAF", 1810),
    "Canada": ("CONCACAF", 1800),
    "Egypt": ("CAF", 1795),
}

# The real, fixed Round-of-16 bracket (snapshot 4 July 2026).
# Order matters: consecutive matches feed a quarterfinal; consecutive QFs feed a
# semifinal. Top half -> SF1, bottom half -> SF2, then the Final.
#   Round of 32 note: Argentina edged Cape Verde 3-2 (AET); Colombia beat Ghana;
#   Germany & Netherlands were knocked out on penalties.
ROUND_OF_16: list[tuple[str, str]] = [
    ("Brazil", "Norway"),        # \
    ("Mexico", "England"),       #  } QF A ─┐
    ("Belgium", "USA"),          # \        } SF1 (top half)
    ("Argentina", "Egypt"),      #  } QF B ─┘
    ("France", "Paraguay"),      # \
    ("Canada", "Morocco"),       #  } QF C ─┐
    ("Spain", "Portugal"),       # \        } SF2 (bottom half)
    ("Switzerland", "Colombia"), #  } QF D ─┘
]


# ---------------------------------------------------------------------------
# 2. Train the scikit-learn Poisson goal model
# ---------------------------------------------------------------------------
def train_goal_model(seed: int = RNG_SEED) -> PoissonRegressor:
    rng = np.random.default_rng(seed)
    n = 40_000
    atk = rng.uniform(1650, 2150, n)
    dfd = rng.uniform(1650, 2150, n)
    home = rng.integers(0, 2, n)

    base = np.log(1.35)  # ~1.35 goals/team on an even, neutral match
    log_mu = base + 0.42 * (atk - dfd) / 100.0 + 0.25 * home
    goals = rng.poisson(np.exp(log_mu))

    X = np.column_stack([atk / 100.0, dfd / 100.0, home.astype(float)])
    model = PoissonRegressor(alpha=1e-6, max_iter=500)
    model.fit(X, goals)
    return model


# ---------------------------------------------------------------------------
# 3. Monte-Carlo knockout simulation (vectorised across all simulations)
# ---------------------------------------------------------------------------
class Knockout:
    """Simulates the remaining bracket N times at once using numpy arrays."""

    def __init__(self, model: PoissonRegressor, n_sims: int, seed: int):
        self.n = n_sims
        self.rng = np.random.default_rng(seed)
        self.names = list(TEAMS.keys())
        self.idx = {name: i for i, name in enumerate(self.names)}
        self.ratings = np.array([TEAMS[n][1] for n in self.names], dtype=float)
        self.is_host = np.array([n in HOSTS for n in self.names], dtype=float)
        self.model = model
        # Pre-fit linear coefficients for fast vectorised scoring.
        self.b_atk, self.b_dfd, self.b_home = model.coef_
        self.b0 = model.intercept_

    def _expected_goals(self, atk, dfd, home):
        return np.exp(
            self.b0
            + self.b_atk * atk / 100.0
            + self.b_dfd * dfd / 100.0
            + self.b_home * home
        )

    def _play_round(self, left: np.ndarray, right: np.ndarray) -> np.ndarray:
        """Vectorised knockout tie between two arrays of team indices.

        left, right : (n_sims,) arrays of team indices.
        Returns the winner index per simulation (extra time + penalties modelled).
        """
        ra, rb = self.ratings[left], self.ratings[right]
        ha, hb = self.is_host[left], self.is_host[right]
        la = self._expected_goals(ra, rb, ha)
        lb = self._expected_goals(rb, ra, hb)
        ga = self.rng.poisson(la)
        gb = self.rng.poisson(lb)

        winner = np.where(ga > gb, left, right)
        drawn = ga == gb
        if drawn.any():
            # Extra time / penalties: decide by Elo win expectation.
            p_left = 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))
            coin = self.rng.random(self.n) < p_left
            winner = np.where(drawn, np.where(coin, left, right), winner)
        return winner

    def simulate(self):
        n = self.n
        # Seed the eight Round-of-16 ties as index arrays.
        r16 = [
            (np.full(n, self.idx[a]), np.full(n, self.idx[b]))
            for a, b in ROUND_OF_16
        ]

        reach_qf = np.zeros(len(self.names))   # won Round of 16
        reach_sf = np.zeros(len(self.names))
        reach_final = np.zeros(len(self.names))
        champion = np.zeros(len(self.names))

        def tally(counter, winners):
            vals, counts = np.unique(winners, return_counts=True)
            counter[vals] += counts

        # Round of 16 -> 8 quarterfinalists
        qf_teams = [self._play_round(l, r) for l, r in r16]
        for w in qf_teams:
            tally(reach_qf, w)

        # Quarterfinals -> 4 semifinalists
        sf_teams = [
            self._play_round(qf_teams[i], qf_teams[i + 1]) for i in (0, 2, 4, 6)
        ]
        for w in sf_teams:
            tally(reach_sf, w)

        # Semifinals -> 2 finalists
        final_teams = [
            self._play_round(sf_teams[0], sf_teams[1]),
            self._play_round(sf_teams[2], sf_teams[3]),
        ]
        for w in final_teams:
            tally(reach_final, w)

        # Final -> champion
        champ = self._play_round(final_teams[0], final_teams[1])
        tally(champion, champ)

        return reach_qf, reach_sf, reach_final, champion


# ---------------------------------------------------------------------------
# 4. Run and write predictions.json
# ---------------------------------------------------------------------------
def main() -> None:
    print("Training scikit-learn Poisson goal model...")
    model = train_goal_model()
    c = model.coef_
    print(
        f"  learned coefficients: attack={c[0]:+.3f}  "
        f"defence={c[1]:+.3f}  home={c[2]:+.3f}"
    )

    print(f"Simulating the knockout bracket {N_SIMULATIONS:,} times...")
    ko = Knockout(model, N_SIMULATIONS, seed=RNG_SEED + 1)
    reach_qf, reach_sf, reach_final, champion = ko.simulate()

    results = []
    for i, name in enumerate(ko.names):
        conf, elo = TEAMS[name]
        results.append(
            {
                "team": name,
                "confederation": conf,
                "elo": elo,
                "champion_pct": round(100 * champion[i] / N_SIMULATIONS, 2),
                "final_pct": round(100 * reach_final[i] / N_SIMULATIONS, 2),
                "semifinal_pct": round(100 * reach_sf[i] / N_SIMULATIONS, 2),
                "quarterfinal_pct": round(100 * reach_qf[i] / N_SIMULATIONS, 2),
            }
        )
    results.sort(key=lambda r: r["champion_pct"], reverse=True)

    # Bracket description for the dashboard.
    labels = ["QF A", "QF A", "QF B", "QF B", "QF C", "QF C", "QF D", "QF D"]
    bracket = []
    for (a, b), lab in zip(ROUND_OF_16, labels):
        bracket.append(
            {
                "home": a,
                "away": b,
                "qf": lab,
                "half": "Top half → Semifinal 1" if lab in ("QF A", "QF B")
                else "Bottom half → Semifinal 2",
            }
        )

    payload = {
        "meta": {
            "snapshot": "2026-07-04 (Round of 16)",
            "simulations": N_SIMULATIONS,
            "model": "scikit-learn PoissonRegressor + Elo strength + Monte Carlo",
            "learned_coefficients": {
                "attack": round(float(c[0]), 4),
                "defence": round(float(c[1]), 4),
                "home": round(float(c[2]), 4),
            },
            "context": "Live knockout projection — simulates forward from the "
            "actual Round-of-16 bracket. Germany & the Netherlands were "
            "eliminated in the Round of 32; Argentina survived Cape Verde 3-2 AET.",
            "market_odds": [
                {"team": "France", "odds": "+180"},
                {"team": "Argentina", "odds": "+400"},
                {"team": "Spain", "odds": "+550"},
                {"team": "England", "odds": "+1000"},
                {"team": "Brazil", "odds": "+1100"},
            ],
        },
        "predictions": results,
        "bracket": bracket,
    }

    out = Path(__file__).with_name("predictions.json")
    out.write_text(json.dumps(payload, indent=2))
    print(f"\nWrote {out}")
    print("\nTitle odds from the Round of 16:")
    for r in results:
        print(f"  {r['team']:<13} {r['champion_pct']:>5.1f}%")


if __name__ == "__main__":
    main()
