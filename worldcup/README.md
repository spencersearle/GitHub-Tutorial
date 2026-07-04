# World Cup 2026 — Live ML Winner Prediction

A machine-learning model that predicts who will win the 2026 FIFA World Cup **from
the current state of the tournament**, and presents it as an intuitive, interactive
dashboard.

> **Snapshot: 4 July 2026 — Round of 16.** The group stage and Round of 32 are
> already played. Rather than guessing a pre-tournament field, the model simulates
> the tournament *forward from the real remaining bracket* — the most relevant
> possible prediction of who lifts the trophy.

## Result (live projection from the Round of 16)

| # | Team | Title odds | Market (implied) |
|---|------|-----------:|-----------------:|
| 1 | France 🇫🇷 | **39.3%** | 36% (+180) |
| 2 | Argentina 🇦🇷 | 34.0% | 20% (+400) |
| 3 | Spain 🇪🇸 | 12.2% | 15% (+550) |
| 4 | Brazil 🇧🇷 | 6.1% | 8% (+1100) |
| 5 | England 🏴 | 4.9% | 9% (+1000) |

The model independently lands on **France as the favourite**, matching the live
betting market. Open **`dashboard.html`** for the full interactive view.

## What it does

1. **Live state** — the 16 teams still alive and the *actual* fixed knockout
   bracket (Round of 16 → Quarterfinals → Semifinals → Final). Notable results
   already in: Germany and the Netherlands were knocked out in the Round of 32;
   Argentina survived Cape Verde 3-2 after extra time.
2. **Learned goal engine** — a scikit-learn `PoissonRegressor` is *trained* to
   predict goals scored from attacking rating, defending rating and home advantage
   (hosts USA / Mexico / Canada get a real edge). Learned coefficients:
   `attack ≈ +0.42`, `defence ≈ −0.42`, `home ≈ +0.25`.
3. **Monte-Carlo knockout** — the remaining bracket is played out **50,000 times**,
   every tie decided by the model (extra time and penalties on draws). Each team's
   share of simulated titles is its probability of winning.

## Run it yourself

```bash
pip install numpy pandas scikit-learn
python3 model.py           # trains the model, simulates, writes predictions.json
python3 build_dashboard.py # renders dashboard.html + artifact.html
```

The knockout simulation is fully vectorised — 50,000 tournaments run in ~2 seconds.
**Re-run after each round** (update the teams, bracket and ratings in `model.py`)
and every figure on the dashboard refreshes automatically.

## Files

| File | Purpose |
|------|---------|
| `model.py` | Trained Poisson model + vectorised Monte-Carlo knockout. |
| `build_dashboard.py` | Turns `predictions.json` into the HTML dashboard. |
| `predictions.json` | Model output: per-team stage probabilities + the bracket. |
| `dashboard.html` | Standalone, responsive, light/dark dashboard. |

## Data sources

Bracket, results and market odds sourced from live 2026 World Cup coverage
(ESPN, FOX Sports, Sky Sports, Yahoo Sports) as of 4 July 2026. Strength ratings
are Elo-style estimates reflecting current form and market consensus.
