"""Turn predictions.json into a readable World Cup dashboard.

Produces two files from one shared body template:
  * dashboard.html  — a full standalone HTML document (committed to the repo)
  * artifact.html   — body-only content for publishing as a Claude Artifact
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).parent
DATA = json.loads((HERE / "predictions.json").read_text())

# Confederation -> categorical palette slot (light / dark), from the validated
# reference palette. Order chosen so adjacent bars stay CVD-separable.
CONF_COLORS = {
    "UEFA": ("#2a78d6", "#3987e5"),       # blue
    "CONMEBOL": ("#1baf7a", "#199e70"),   # aqua
    "CAF": ("#eda100", "#c98500"),        # yellow
    "AFC": ("#4a3aa7", "#9085e9"),        # violet
    "CONCACAF": ("#e34948", "#e66767"),   # red
    "OFC": ("#eb6834", "#d95926"),        # orange
}
CONF_FULL = {
    "UEFA": "Europe",
    "CONMEBOL": "South America",
    "CAF": "Africa",
    "AFC": "Asia / Australia",
    "CONCACAF": "North America",
    "OFC": "Oceania",
}


def build_inner() -> str:
    preds = DATA["predictions"]
    meta = DATA["meta"]
    groups = DATA["groups"]
    champ = preds[0]

    # confederation css vars
    conf_vars_light = "\n".join(
        f"    --conf-{k.lower()}: {v[0]};" for k, v in CONF_COLORS.items()
    )
    conf_vars_dark = "\n".join(
        f"      --conf-{k.lower()}: {v[1]};" for k, v in CONF_COLORS.items()
    )

    # ---- podium (top 3) ----
    podium_order = [1, 0, 2]  # silver, gold, bronze visual order
    medals = {0: "🥇", 1: "🥈", 2: "🥉"}
    podium_cards = ""
    for rank in podium_order:
        t = preds[rank]
        podium_cards += f"""
        <div class="podium-card rank-{rank}">
          <div class="podium-medal">{medals[rank]}</div>
          <div class="podium-team">{t['team']}</div>
          <div class="podium-conf" style="color:var(--conf-{t['confederation'].lower()})">{CONF_FULL[t['confederation']]}</div>
          <div class="podium-pct">{t['champion_pct']:.1f}%</div>
          <div class="podium-label">to win it all</div>
        </div>"""

    # ---- bar chart (top 16 title odds) ----
    top = preds[:16]
    vmax = top[0]["champion_pct"]
    bars = ""
    for t in top:
        w = max(1.0, 100 * t["champion_pct"] / vmax)
        conf = t["confederation"].lower()
        bars += f"""
        <div class="bar-row" tabindex="0"
             data-tip="{t['team']} — {CONF_FULL[t['confederation']]} · Elo {t['elo']:.0f}&#10;Champion {t['champion_pct']:.1f}% · Final {t['final_pct']:.1f}% · Semi {t['semifinal_pct']:.1f}%">
          <div class="bar-name">{t['team']}</div>
          <div class="bar-track">
            <div class="bar-fill" style="width:{w:.2f}%;background:var(--conf-{conf})"></div>
          </div>
          <div class="bar-val">{t['champion_pct']:.1f}%</div>
        </div>"""

    # ---- legend ----
    used_confs = []
    for t in preds:
        if t["confederation"] not in used_confs:
            used_confs.append(t["confederation"])
    legend = "".join(
        f'<span class="lg-item"><span class="lg-swatch" style="background:var(--conf-{c.lower()})"></span>{CONF_FULL[c]}</span>'
        for c in used_confs
    )

    # ---- full table ----
    rows = ""
    for i, t in enumerate(preds):
        conf = t["confederation"].lower()
        rows += f"""
        <tr>
          <td class="t-rank">{i + 1}</td>
          <td class="t-team"><span class="dot" style="background:var(--conf-{conf})"></span>{t['team']}</td>
          <td class="t-conf">{CONF_FULL[t['confederation']]}</td>
          <td class="t-num">{t['elo']:.0f}</td>
          <td class="t-num">{t['quarterfinal_pct']:.1f}%</td>
          <td class="t-num">{t['semifinal_pct']:.1f}%</td>
          <td class="t-num">{t['final_pct']:.1f}%</td>
          <td class="t-num t-champ">{t['champion_pct']:.1f}%</td>
        </tr>"""

    # ---- groups ----
    gcards = ""
    for g in groups:
        gteams = "".join(
            f'<li><span class="dot" style="background:var(--conf-{tm["confederation"].lower()})"></span>{tm["team"]}<span class="g-elo">{tm["elo"]:.0f}</span></li>'
            for tm in sorted(g["teams"], key=lambda x: x["elo"], reverse=True)
        )
        gcards += f"""
        <div class="group-card">
          <div class="group-name">{g['name']}</div>
          <ul>{gteams}</ul>
        </div>"""

    coefs = meta["learned_coefficients"]

    return f"""
<style>
  .wc-root {{
    --surface-1: #fcfcfb;
    --surface-2: #ffffff;
    --page: #f2f2ef;
    --ink: #0b0b0b;
    --ink-2: #52514e;
    --muted: #898781;
    --grid: #e1e0d9;
    --border: rgba(11,11,11,0.10);
    --gold: #eda100;
{conf_vars_light}
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    color: var(--ink);
    background: var(--page);
    line-height: 1.5;
    -webkit-font-smoothing: antialiased;
    padding: clamp(16px, 4vw, 40px);
    max-width: 1120px;
    margin: 0 auto;
  }}
  @media (prefers-color-scheme: dark) {{
    .wc-root {{
      --surface-1: #1a1a19;
      --surface-2: #202020;
      --page: #0d0d0d;
      --ink: #ffffff;
      --ink-2: #c3c2b7;
      --muted: #898781;
      --grid: #2c2c2a;
      --border: rgba(255,255,255,0.10);
      --gold: #f0b73a;
{conf_vars_dark}
    }}
  }}
  :root[data-theme="light"] .wc-root {{
    --surface-1:#fcfcfb;--surface-2:#fff;--page:#f2f2ef;--ink:#0b0b0b;--ink-2:#52514e;
    --grid:#e1e0d9;--border:rgba(11,11,11,0.10);--gold:#eda100;
{conf_vars_light}
  }}
  :root[data-theme="dark"] .wc-root {{
    --surface-1:#1a1a19;--surface-2:#202020;--page:#0d0d0d;--ink:#fff;--ink-2:#c3c2b7;
    --grid:#2c2c2a;--border:rgba(255,255,255,0.10);--gold:#f0b73a;
{conf_vars_dark}
  }}
  .wc-root * {{ box-sizing: border-box; }}
  .wc-hero-eyebrow {{
    text-transform: uppercase; letter-spacing: .14em; font-size: .72rem;
    font-weight: 700; color: var(--muted); margin: 0 0 .4rem;
  }}
  .wc-title {{ font-size: clamp(1.6rem, 4.5vw, 2.5rem); font-weight: 800; margin: 0; letter-spacing: -.02em; }}
  .wc-sub {{ color: var(--ink-2); margin: .5rem 0 0; max-width: 62ch; font-size: .98rem; }}

  .card {{
    background: var(--surface-1); border: 1px solid var(--border);
    border-radius: 16px; padding: clamp(18px, 3vw, 28px); margin-top: 22px;
    box-shadow: 0 1px 2px rgba(0,0,0,.04);
  }}
  .sec-title {{ font-size: 1.06rem; font-weight: 700; margin: 0 0 4px; }}
  .sec-note {{ font-size: .85rem; color: var(--muted); margin: 0 0 18px; }}

  /* champion banner */
  .champ-banner {{
    display: flex; align-items: center; gap: clamp(16px,3vw,28px); flex-wrap: wrap;
    background: linear-gradient(135deg, color-mix(in srgb, var(--gold) 16%, var(--surface-1)), var(--surface-1) 70%);
    border-color: color-mix(in srgb, var(--gold) 35%, var(--border));
  }}
  .champ-trophy {{ font-size: clamp(3rem, 9vw, 4.6rem); line-height: 1; filter: drop-shadow(0 3px 6px rgba(0,0,0,.18)); }}
  .champ-info {{ flex: 1 1 220px; }}
  .champ-kicker {{ text-transform: uppercase; letter-spacing: .12em; font-size: .72rem; font-weight: 700; color: var(--muted); }}
  .champ-name {{ font-size: clamp(2rem, 6vw, 3.1rem); font-weight: 800; letter-spacing: -.02em; margin: 2px 0; }}
  .champ-meta {{ color: var(--ink-2); font-size: .95rem; }}
  .champ-figure {{ text-align: right; }}
  .champ-big {{ font-size: clamp(2.6rem, 8vw, 3.8rem); font-weight: 800; color: var(--gold); letter-spacing: -.03em; }}
  .champ-big small {{ font-size: .9rem; color: var(--muted); font-weight: 600; display:block; letter-spacing: normal; }}

  /* podium */
  .podium {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; align-items: end; }}
  .podium-card {{
    background: var(--surface-2); border: 1px solid var(--border); border-radius: 14px;
    padding: 18px 12px; text-align: center;
  }}
  .podium-card.rank-0 {{ border-color: color-mix(in srgb, var(--gold) 45%, var(--border)); transform: translateY(-10px); box-shadow: 0 6px 18px rgba(0,0,0,.08); }}
  .podium-medal {{ font-size: 1.8rem; }}
  .podium-team {{ font-weight: 700; font-size: 1.05rem; margin-top: 4px; }}
  .podium-conf {{ font-size: .78rem; font-weight: 600; }}
  .podium-pct {{ font-size: 1.7rem; font-weight: 800; margin-top: 6px; letter-spacing: -.02em; }}
  .podium-label {{ font-size: .72rem; color: var(--muted); }}

  /* bars */
  .legend {{ display: flex; flex-wrap: wrap; gap: 8px 16px; margin-bottom: 16px; }}
  .lg-item {{ display: inline-flex; align-items: center; gap: 6px; font-size: .8rem; color: var(--ink-2); }}
  .lg-swatch {{ width: 12px; height: 12px; border-radius: 3px; }}
  .bar-row {{ display: grid; grid-template-columns: 108px 1fr 52px; align-items: center; gap: 12px; padding: 5px 4px; border-radius: 8px; outline: none; }}
  .bar-row:hover, .bar-row:focus {{ background: color-mix(in srgb, var(--ink) 5%, transparent); }}
  .bar-name {{ font-size: .88rem; font-weight: 600; text-align: right; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .bar-track {{ background: color-mix(in srgb, var(--grid) 60%, transparent); border-radius: 5px; height: 20px; overflow: hidden; }}
  .bar-fill {{ height: 100%; border-radius: 4px; min-width: 3px; transition: width .2s; }}
  .bar-val {{ font-size: .85rem; font-weight: 700; font-variant-numeric: tabular-nums; text-align: right; }}

  /* table */
  .table-wrap {{ overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; font-size: .88rem; min-width: 620px; }}
  thead th {{
    text-align: right; font-size: .72rem; text-transform: uppercase; letter-spacing: .05em;
    color: var(--muted); font-weight: 700; padding: 8px 10px; border-bottom: 1px solid var(--grid); position: sticky; top: 0; background: var(--surface-1);
  }}
  thead th.l {{ text-align: left; }}
  tbody td {{ padding: 8px 10px; border-bottom: 1px solid var(--grid); font-variant-numeric: tabular-nums; }}
  tbody tr:hover {{ background: color-mix(in srgb, var(--ink) 4%, transparent); }}
  .t-rank {{ color: var(--muted); width: 32px; }}
  .t-team {{ font-weight: 600; white-space: nowrap; }}
  .t-conf {{ color: var(--ink-2); }}
  .t-num {{ text-align: right; }}
  .t-champ {{ font-weight: 800; color: var(--gold); }}
  .dot {{ display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 8px; vertical-align: baseline; }}

  /* groups */
  .groups {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; }}
  .group-card {{ background: var(--surface-2); border: 1px solid var(--border); border-radius: 12px; padding: 12px 14px; }}
  .group-name {{ font-weight: 700; font-size: .82rem; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); margin-bottom: 8px; }}
  .group-card ul {{ list-style: none; margin: 0; padding: 0; }}
  .group-card li {{ display: flex; align-items: center; font-size: .9rem; padding: 3px 0; }}
  .g-elo {{ margin-left: auto; color: var(--muted); font-size: .78rem; font-variant-numeric: tabular-nums; }}

  .method {{ font-size: .84rem; color: var(--ink-2); }}
  .method code {{ background: color-mix(in srgb, var(--ink) 7%, transparent); padding: 1px 6px; border-radius: 5px; font-size: .82rem; }}
  .method b {{ color: var(--ink); }}
  .foot {{ text-align: center; color: var(--muted); font-size: .78rem; margin-top: 26px; }}

  /* tooltip */
  #wc-tip {{
    position: fixed; pointer-events: none; z-index: 50; opacity: 0; transition: opacity .12s;
    background: var(--ink); color: var(--page); padding: 8px 11px; border-radius: 8px;
    font-size: .78rem; line-height: 1.45; max-width: 260px; white-space: pre-line; box-shadow: 0 6px 20px rgba(0,0,0,.28);
  }}
  @media (max-width: 560px) {{
    .bar-row {{ grid-template-columns: 84px 1fr 46px; gap: 8px; }}
    .podium-team {{ font-size: .95rem; }}
  }}
</style>

<div class="wc-root">
  <header>
    <p class="wc-hero-eyebrow">FIFA World Cup 2026 · ML Projection</p>
    <h1 class="wc-title">Who will win the World Cup?</h1>
    <p class="wc-sub">A scikit-learn Poisson goal model trained on team strength, then run through
      <b>{meta['simulations']:,}</b> Monte-Carlo simulations of the full 48-team bracket. Percentages are
      each team's share of simulated titles.</p>
  </header>

  <section class="card champ-banner">
    <div class="champ-trophy">🏆</div>
    <div class="champ-info">
      <div class="champ-kicker">Model's Favourite</div>
      <div class="champ-name">{champ['team']}</div>
      <div class="champ-meta">{CONF_FULL[champ['confederation']]} · Elo {champ['elo']:.0f} · reaches the final in {champ['final_pct']:.0f}% of simulations</div>
    </div>
    <div class="champ-figure">
      <div class="champ-big">{champ['champion_pct']:.1f}%<small>chance to lift the cup</small></div>
    </div>
  </section>

  <section class="card">
    <h2 class="sec-title">The Podium</h2>
    <p class="sec-note">Three most likely champions across all simulations.</p>
    <div class="podium">{podium_cards}
    </div>
  </section>

  <section class="card">
    <h2 class="sec-title">Title Odds — Top 16</h2>
    <p class="sec-note">Bar length is each team's probability of winning the tournament. Colour marks the confederation.</p>
    <div class="legend">{legend}</div>
    <div class="bars">{bars}
    </div>
  </section>

  <section class="card">
    <h2 class="sec-title">Full Projection — How Far Each Team Goes</h2>
    <p class="sec-note">Probability of reaching each stage. Sorted by title odds. Scroll sideways on narrow screens.</p>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th class="l">#</th><th class="l">Team</th><th class="l">Region</th>
            <th>Elo</th><th>Quarters</th><th>Semis</th><th>Final</th><th>Champion</th>
          </tr>
        </thead>
        <tbody>{rows}
        </tbody>
      </table>
    </div>
  </section>

  <section class="card">
    <h2 class="sec-title">The Draw — 12 Groups</h2>
    <p class="sec-note">Reproducible pot-based draw (seeded by strength, confederation-aware).</p>
    <div class="groups">{gcards}
    </div>
  </section>

  <section class="card method">
    <h2 class="sec-title">How the model works</h2>
    <p style="margin-top:10px">
      <b>1. Strength ratings.</b> Every team carries an Elo rating that distils real historical
      results into a single number — the higher the gap, the more one side is expected to dominate.
    </p>
    <p>
      <b>2. Learned goal engine.</b> A scikit-learn <code>PoissonRegressor</code> is trained to predict goals
      scored from the attacking and defending ratings plus home advantage. It recovered coefficients
      <code>attack {coefs['attack']:+.3f}</code>, <code>defence {coefs['defence']:+.3f}</code>,
      <code>home {coefs['home']:+.3f}</code> — i.e. stronger attack and weaker opposing defence both
      raise expected goals, and hosts get a real edge.
    </p>
    <p>
      <b>3. Monte-Carlo tournament.</b> The model plays every group match and knockout tie (extra time and
      penalties included) across <b>{meta['simulations']:,}</b> full tournaments. Counting how often each team
      lifts the trophy gives the probabilities above.
    </p>
    <p style="color:var(--muted);margin-top:12px">
      The field, group draw and ratings are a reproducible model projection, not the official FIFA draw —
      swap in official numbers and re-run <code>model.py</code> to update every figure on this page.
    </p>
  </section>

  <p class="foot">Generated by <b>worldcup/model.py</b> — {meta['model']}.</p>
</div>

<div id="wc-tip"></div>
<script>
  (function () {{
    var tip = document.getElementById('wc-tip');
    function show(e, text) {{
      tip.textContent = text; tip.style.opacity = '1';
      var x = e.clientX + 14, y = e.clientY + 14;
      if (x + 270 > window.innerWidth) x = e.clientX - 270;
      tip.style.left = x + 'px'; tip.style.top = y + 'px';
    }}
    function hide() {{ tip.style.opacity = '0'; }}
    document.querySelectorAll('.bar-row').forEach(function (el) {{
      var t = el.getAttribute('data-tip');
      el.addEventListener('mousemove', function (e) {{ show(e, t); }});
      el.addEventListener('mouseleave', hide);
      el.addEventListener('focus', function () {{
        var r = el.getBoundingClientRect();
        show({{clientX: r.left + 40, clientY: r.top}}, t);
      }});
      el.addEventListener('blur', hide);
    }});
  }})();
</script>
"""


def main() -> None:
    inner = build_inner()
    champ = DATA["predictions"][0]["team"]

    standalone = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>World Cup 2026 — ML Prediction</title>
</head>
<body style="margin:0;background:#f2f2ef">
{inner}
</body>
</html>
"""
    (HERE / "dashboard.html").write_text(standalone)
    (HERE / "artifact.html").write_text(inner)
    print(f"Wrote dashboard.html and artifact.html (favourite: {champ})")


if __name__ == "__main__":
    main()
