# World Cup 2026 — ML Winner Prediction

A machine-learning model that predicts who will win the 2026 FIFA World Cup and
presents the result as an intuitive, interactive dashboard.

![Top favourites](https://img.shields.io) <!-- see dashboard.html for the live view -->

## What it does

1. **Team strength** — all 48 teams carry an Elo rating that distils real
   historical results into a single number.
2. **Learned goal engine** — a scikit-learn `PoissonRegressor` is *trained* to
   predict goals scored from the attacking rating, defending rating and home
   advantage. The learned coefficients (`attack ≈ +0.42`, `defence ≈ −0.42`,
   `home ≈ +0.25`) confirm the model recovered a realistic scoring relationship.
3. **Monte-Carlo tournament** — the full bracket (12 groups of 4, best-third
   qualification, then a 32-team knockout with extra time / penalties) is
   simulated **20,000 times**. Each team's share of simulated titles is its
   probability of winning.

## Result (model projection)

| # | Team | Win % |
|---|------|------:|
| 1 | Argentina | 39.4% |
| 2 | France | 28.0% |
| 3 | Spain | 14.0% |
| 4 | England | 6.0% |
| 5 | Brazil | 4.6% |

Open **`dashboard.html`** in a browser for the full interactive view: podium,
title-odds bar chart, a stage-by-stage table for all 48 teams, the group draw
and the methodology.

## Run it yourself

```bash
pip install numpy pandas scikit-learn
python3 model.py          # trains the model, simulates, writes predictions.json
python3 build_dashboard.py # renders dashboard.html + artifact.html
```

## Files

| File | Purpose |
|------|---------|
| `model.py` | Trains the Poisson model and runs the Monte-Carlo tournament. |
| `build_dashboard.py` | Turns `predictions.json` into the HTML dashboard. |
| `predictions.json` | Model output: per-team stage probabilities + the draw. |
| `dashboard.html` | Standalone, responsive, light/dark dashboard. |

## Notes & assumptions

The field, group draw and ratings are a **reproducible model projection**, not
the official FIFA draw. To predict against reality, replace the ratings and
groups in `model.py` with official numbers and re-run — every figure on the
dashboard updates automatically.
