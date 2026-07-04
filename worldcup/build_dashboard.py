"""Turn predictions.json into a readable, live World Cup knockout dashboard.

Produces:
  * dashboard.html  — a full standalone HTML document (committed to the repo)
  * artifact.html   — body-only content for publishing as a Claude Artifact
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).parent
DATA = json.loads((HERE / "predictions.json").read_text())

CONF_COLORS = {
    "UEFA": "#2a78d6",       # blue
    "CONMEBOL": "#1baf7a",   # aqua
    "CAF": "#eda100",        # yellow
    "AFC": "#4a3aa7",        # violet
    "CONCACAF": "#e34948",   # red
    "OFC": "#eb6834",        # orange
}
CONF_COLORS_DARK = {
    "UEFA": "#3987e5", "CONMEBOL": "#199e70", "CAF": "#c98500",
    "AFC": "#9085e9", "CONCACAF": "#e66767", "OFC": "#d95926",
}
CONF_FULL = {
    "UEFA": "Europe", "CONMEBOL": "South America", "CAF": "Africa",
    "AFC": "Asia / Australia", "CONCACAF": "North America", "OFC": "Oceania",
}


def implied_from_american(odds: str) -> float:
    n = int(odds)
    if n > 0:
        return 100.0 / (n + 100.0) * 100.0
    return -n / (-n + 100.0) * 100.0


def build_inner() -> str:
    preds = DATA["predictions"]
    meta = DATA["meta"]
    bracket = DATA["bracket"]
    champ = preds[0]
    conf_of = {p["team"]: p["confederation"] for p in preds}
    champ_pct = {p["team"]: p["champion_pct"] for p in preds}

    conf_vars_light = "\n".join(
        f"    --conf-{k.lower()}: {v};" for k, v in CONF_COLORS.items()
    )
    conf_vars_dark = "\n".join(
        f"      --conf-{k.lower()}: {v};" for k, v in CONF_COLORS_DARK.items()
    )

    # ---- podium (top 3) ----
    podium_order = [1, 0, 2]
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

    # ---- bar chart (all 16 remaining) ----
    alive = [p for p in preds if p["champion_pct"] > 0] or preds[:8]
    vmax = alive[0]["champion_pct"]
    bars = ""
    for t in preds:
        w = max(0.6, 100 * t["champion_pct"] / vmax)
        conf = t["confederation"].lower()
        bars += f"""
        <div class="bar-row" tabindex="0"
             data-tip="{t['team']} — {CONF_FULL[t['confederation']]} · Elo {t['elo']:.0f}&#10;Champion {t['champion_pct']:.1f}% · Final {t['final_pct']:.1f}% · Semi {t['semifinal_pct']:.1f}% · Quarter {t['quarterfinal_pct']:.1f}%">
          <div class="bar-name">{t['team']}</div>
          <div class="bar-track">
            <div class="bar-fill" style="width:{w:.2f}%;background:var(--conf-{conf})"></div>
          </div>
          <div class="bar-val">{t['champion_pct']:.1f}%</div>
        </div>"""

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

    # ---- bracket (two halves, four QFs, eight R16 ties) ----
    def tie_html(m):
        a, b = m["home"], m["away"]
        pa, pb = champ_pct.get(a, 0), champ_pct.get(b, 0)
        fav = a if pa >= pb else b
        def team_line(name):
            conf = conf_of[name].lower()
            strong = ' class="fav"' if name == fav else ""
            return f'<div class="tie-team"><span class="dot" style="background:var(--conf-{conf})"></span><span{strong}>{name}</span><span class="tie-pct">{champ_pct.get(name,0):.0f}%</span></div>'
        return f'<div class="tie">{team_line(a)}{team_line(b)}</div>'

    halves = {"Top half → Semifinal 1": [], "Bottom half → Semifinal 2": []}
    # group ties by QF label preserving order
    qf_groups: dict[str, list] = {}
    qf_half: dict[str, str] = {}
    for m in bracket:
        qf_groups.setdefault(m["qf"], []).append(m)
        qf_half[m["qf"]] = m["half"]
    top_html, bot_html = "", ""
    for qf, ms in qf_groups.items():
        block = f'<div class="qf-block"><div class="qf-label">{qf}</div>{"".join(tie_html(m) for m in ms)}</div>'
        if qf_half[qf].startswith("Top"):
            top_html += block
        else:
            bot_html += block

    # ---- market comparison ----
    market_rows = ""
    for mo in meta.get("market_odds", []):
        team = mo["team"]
        imp = implied_from_american(mo["odds"])
        model = champ_pct.get(team, 0)
        diff = model - imp
        sign = "＋" if diff >= 0 else "－"
        cls = "up" if diff >= 0 else "down"
        market_rows += f"""
        <tr>
          <td class="t-team">{team}</td>
          <td class="t-num">{mo['odds']}</td>
          <td class="t-num">{imp:.0f}%</td>
          <td class="t-num t-champ">{model:.0f}%</td>
          <td class="t-num delta {cls}">{sign}{abs(diff):.0f} pts</td>
        </tr>"""

    coefs = meta["learned_coefficients"]

    return f"""
<style>
  .wc-root {{
    --surface-1: #fcfcfb; --surface-2: #ffffff; --page: #f2f2ef;
    --ink: #0b0b0b; --ink-2: #52514e; --muted: #898781;
    --grid: #e1e0d9; --border: rgba(11,11,11,0.10);
    --gold: #eda100; --live: #d03b3b; --up: #0ca30c; --down: #898781;
{conf_vars_light}
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    color: var(--ink); background: var(--page); line-height: 1.5;
    -webkit-font-smoothing: antialiased;
    padding: clamp(16px, 4vw, 40px); max-width: 1120px; margin: 0 auto;
  }}
  @media (prefers-color-scheme: dark) {{
    .wc-root {{
      --surface-1: #1a1a19; --surface-2: #202020; --page: #0d0d0d;
      --ink: #ffffff; --ink-2: #c3c2b7; --muted: #898781;
      --grid: #2c2c2a; --border: rgba(255,255,255,0.10);
      --gold: #f0b73a; --live: #e66767; --up: #0ca30c;
{conf_vars_dark}
    }}
  }}
  :root[data-theme="light"] .wc-root {{
    --surface-1:#fcfcfb;--surface-2:#fff;--page:#f2f2ef;--ink:#0b0b0b;--ink-2:#52514e;
    --grid:#e1e0d9;--border:rgba(11,11,11,0.10);--gold:#eda100;--live:#d03b3b;--up:#0ca30c;--down:#898781;
{conf_vars_light}
  }}
  :root[data-theme="dark"] .wc-root {{
    --surface-1:#1a1a19;--surface-2:#202020;--page:#0d0d0d;--ink:#fff;--ink-2:#c3c2b7;
    --grid:#2c2c2a;--border:rgba(255,255,255,0.10);--gold:#f0b73a;--live:#e66767;--up:#0ca30c;
{conf_vars_dark}
  }}
  .wc-root * {{ box-sizing: border-box; }}
  .live-pill {{
    display:inline-flex; align-items:center; gap:7px; font-size:.72rem; font-weight:700;
    text-transform:uppercase; letter-spacing:.1em; color:var(--live);
    background:color-mix(in srgb, var(--live) 12%, transparent); padding:5px 11px; border-radius:999px;
  }}
  .live-dot {{ width:8px; height:8px; border-radius:50%; background:var(--live); animation:pulse 1.8s infinite; }}
  @keyframes pulse {{ 0%,100%{{opacity:1}} 50%{{opacity:.35}} }}
  @media (prefers-reduced-motion: reduce) {{ .live-dot {{ animation:none; }} }}
  .wc-title {{ font-size: clamp(1.6rem, 4.5vw, 2.5rem); font-weight: 800; margin:.5rem 0 0; letter-spacing:-.02em; }}
  .wc-sub {{ color: var(--ink-2); margin:.5rem 0 0; max-width:64ch; font-size:.98rem; }}

  .card {{
    background: var(--surface-1); border:1px solid var(--border); border-radius:16px;
    padding: clamp(18px,3vw,28px); margin-top:22px; box-shadow:0 1px 2px rgba(0,0,0,.04);
  }}
  .sec-title {{ font-size:1.06rem; font-weight:700; margin:0 0 4px; }}
  .sec-note {{ font-size:.85rem; color:var(--muted); margin:0 0 18px; }}

  .champ-banner {{
    display:flex; align-items:center; gap:clamp(16px,3vw,28px); flex-wrap:wrap;
    background: linear-gradient(135deg, color-mix(in srgb, var(--gold) 16%, var(--surface-1)), var(--surface-1) 70%);
    border-color: color-mix(in srgb, var(--gold) 35%, var(--border));
  }}
  .champ-trophy {{ font-size:clamp(3rem,9vw,4.6rem); line-height:1; filter:drop-shadow(0 3px 6px rgba(0,0,0,.18)); }}
  .champ-info {{ flex:1 1 220px; }}
  .champ-kicker {{ text-transform:uppercase; letter-spacing:.12em; font-size:.72rem; font-weight:700; color:var(--muted); }}
  .champ-name {{ font-size:clamp(2rem,6vw,3.1rem); font-weight:800; letter-spacing:-.02em; margin:2px 0; }}
  .champ-meta {{ color:var(--ink-2); font-size:.95rem; }}
  .champ-figure {{ text-align:right; }}
  .champ-big {{ font-size:clamp(2.6rem,8vw,3.8rem); font-weight:800; color:var(--gold); letter-spacing:-.03em; }}
  .champ-big small {{ font-size:.9rem; color:var(--muted); font-weight:600; display:block; letter-spacing:normal; }}

  .podium {{ display:grid; grid-template-columns:repeat(3,1fr); gap:14px; align-items:end; }}
  .podium-card {{ background:var(--surface-2); border:1px solid var(--border); border-radius:14px; padding:18px 12px; text-align:center; }}
  .podium-card.rank-0 {{ border-color:color-mix(in srgb, var(--gold) 45%, var(--border)); transform:translateY(-10px); box-shadow:0 6px 18px rgba(0,0,0,.08); }}
  .podium-medal {{ font-size:1.8rem; }}
  .podium-team {{ font-weight:700; font-size:1.05rem; margin-top:4px; }}
  .podium-conf {{ font-size:.78rem; font-weight:600; }}
  .podium-pct {{ font-size:1.7rem; font-weight:800; margin-top:6px; letter-spacing:-.02em; }}
  .podium-label {{ font-size:.72rem; color:var(--muted); }}

  .legend {{ display:flex; flex-wrap:wrap; gap:8px 16px; margin-bottom:16px; }}
  .lg-item {{ display:inline-flex; align-items:center; gap:6px; font-size:.8rem; color:var(--ink-2); }}
  .lg-swatch {{ width:12px; height:12px; border-radius:3px; }}
  .bar-row {{ display:grid; grid-template-columns:104px 1fr 52px; align-items:center; gap:12px; padding:4px; border-radius:8px; outline:none; }}
  .bar-row:hover, .bar-row:focus {{ background:color-mix(in srgb, var(--ink) 5%, transparent); }}
  .bar-name {{ font-size:.88rem; font-weight:600; text-align:right; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
  .bar-track {{ background:color-mix(in srgb, var(--grid) 60%, transparent); border-radius:5px; height:20px; overflow:hidden; }}
  .bar-fill {{ height:100%; border-radius:4px; min-width:3px; transition:width .2s; }}
  .bar-val {{ font-size:.85rem; font-weight:700; font-variant-numeric:tabular-nums; text-align:right; }}

  .table-wrap {{ overflow-x:auto; }}
  table {{ width:100%; border-collapse:collapse; font-size:.88rem; min-width:560px; }}
  thead th {{ text-align:right; font-size:.72rem; text-transform:uppercase; letter-spacing:.05em; color:var(--muted); font-weight:700; padding:8px 10px; border-bottom:1px solid var(--grid); }}
  thead th.l {{ text-align:left; }}
  tbody td {{ padding:8px 10px; border-bottom:1px solid var(--grid); font-variant-numeric:tabular-nums; }}
  tbody tr:hover {{ background:color-mix(in srgb, var(--ink) 4%, transparent); }}
  .t-rank {{ color:var(--muted); width:32px; }}
  .t-team {{ font-weight:600; white-space:nowrap; }}
  .t-conf {{ color:var(--ink-2); }}
  .t-num {{ text-align:right; }}
  .t-champ {{ font-weight:800; color:var(--gold); }}
  .delta.up {{ color:var(--up); }} .delta.down {{ color:var(--muted); }}
  .dot {{ display:inline-block; width:9px; height:9px; border-radius:50%; margin-right:8px; }}

  /* bracket */
  .bracket {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
  .half {{ background:var(--surface-2); border:1px solid var(--border); border-radius:14px; padding:14px; }}
  .half-title {{ font-size:.78rem; font-weight:700; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); margin-bottom:12px; }}
  .qf-block {{ margin-bottom:14px; }}
  .qf-label {{ font-size:.7rem; font-weight:700; color:var(--ink-2); margin-bottom:6px; letter-spacing:.04em; }}
  .tie {{ border:1px solid var(--border); border-radius:9px; overflow:hidden; margin-bottom:7px; }}
  .tie-team {{ display:flex; align-items:center; gap:2px; padding:7px 10px; font-size:.9rem; background:var(--surface-1); }}
  .tie-team + .tie-team {{ border-top:1px solid var(--grid); }}
  .tie-team .fav {{ font-weight:700; }}
  .tie-pct {{ margin-left:auto; color:var(--muted); font-size:.8rem; font-variant-numeric:tabular-nums; }}

  .method {{ font-size:.84rem; color:var(--ink-2); }}
  .method code {{ background:color-mix(in srgb, var(--ink) 7%, transparent); padding:1px 6px; border-radius:5px; font-size:.82rem; }}
  .method b {{ color:var(--ink); }}
  .foot {{ text-align:center; color:var(--muted); font-size:.78rem; margin-top:26px; }}

  #wc-tip {{ position:fixed; pointer-events:none; z-index:50; opacity:0; transition:opacity .12s;
    background:var(--ink); color:var(--page); padding:8px 11px; border-radius:8px; font-size:.78rem;
    line-height:1.45; max-width:280px; white-space:pre-line; box-shadow:0 6px 20px rgba(0,0,0,.28); }}
  @media (max-width:620px) {{
    .bracket {{ grid-template-columns:1fr; }}
    .bar-row {{ grid-template-columns:84px 1fr 46px; gap:8px; }}
  }}
</style>

<div class="wc-root">
  <header>
    <span class="live-pill"><span class="live-dot"></span>Live · Round of 16 · {meta['snapshot'].split(' ')[0]}</span>
    <h1 class="wc-title">Who will win the World Cup — from here?</h1>
    <p class="wc-sub">The group stage and Round of 32 are done. This model takes the <b>16 teams still
      standing</b> and their <b>real knockout bracket</b>, then plays it out <b>{meta['simulations']:,}</b>
      times with a machine-learning match engine. Percentages are each team's share of simulated titles.</p>
  </header>

  <section class="card champ-banner">
    <div class="champ-trophy">🏆</div>
    <div class="champ-info">
      <div class="champ-kicker">Model's Favourite to Lift the Cup</div>
      <div class="champ-name">{champ['team']}</div>
      <div class="champ-meta">{CONF_FULL[champ['confederation']]} · Elo {champ['elo']:.0f} · reaches the final in {champ['final_pct']:.0f}% of simulations</div>
    </div>
    <div class="champ-figure">
      <div class="champ-big">{champ['champion_pct']:.1f}%<small>chance to win it all</small></div>
    </div>
  </section>

  <section class="card">
    <h2 class="sec-title">The Podium</h2>
    <p class="sec-note">Three most likely champions from the current Round of 16.</p>
    <div class="podium">{podium_cards}
    </div>
  </section>

  <section class="card">
    <h2 class="sec-title">Title Odds — All 16 Survivors</h2>
    <p class="sec-note">Bar length is each team's probability of winning the tournament from here. Colour marks the confederation. Hover for full stage-by-stage odds.</p>
    <div class="legend">{legend}</div>
    <div class="bars">{bars}
    </div>
  </section>

  <section class="card">
    <h2 class="sec-title">Model vs. the Bookmakers</h2>
    <p class="sec-note">How the model's title odds compare with live betting-market prices (implied probability, vig included).</p>
    <div class="table-wrap">
      <table>
        <thead><tr><th class="l">Team</th><th>Market odds</th><th>Implied</th><th>Model</th><th>Edge</th></tr></thead>
        <tbody>{market_rows}
        </tbody>
      </table>
    </div>
  </section>

  <section class="card">
    <h2 class="sec-title">The Live Bracket — Path to the Final</h2>
    <p class="sec-note">The real Round-of-16 draw. Bold = model favourite in each tie; the % is that team's odds to win the whole thing.</p>
    <div class="bracket">
      <div class="half"><div class="half-title">Top half → Semifinal 1</div>{top_html}</div>
      <div class="half"><div class="half-title">Bottom half → Semifinal 2</div>{bot_html}</div>
    </div>
  </section>

  <section class="card">
    <h2 class="sec-title">Full Projection — How Far Each Team Goes</h2>
    <p class="sec-note">Probability of reaching each remaining stage. Sorted by title odds.</p>
    <div class="table-wrap">
      <table>
        <thead>
          <tr><th class="l">#</th><th class="l">Team</th><th class="l">Region</th>
          <th>Elo</th><th>Quarters</th><th>Semis</th><th>Final</th><th>Champion</th></tr>
        </thead>
        <tbody>{rows}
        </tbody>
      </table>
    </div>
  </section>

  <section class="card method">
    <h2 class="sec-title">How the model works</h2>
    <p style="margin-top:10px"><b>1. Live state.</b> The 16 remaining teams and the actual fixed knockout
      bracket as of <b>{meta['snapshot']}</b>. {meta['context']}</p>
    <p><b>2. Learned goal engine.</b> A scikit-learn <code>PoissonRegressor</code> predicts goals scored
      from attacking rating, defending rating and home advantage, with learned coefficients
      <code>attack {coefs['attack']:+.3f}</code>, <code>defence {coefs['defence']:+.3f}</code>,
      <code>home {coefs['home']:+.3f}</code> — hosts (USA, Mexico, Canada) get a real edge on home soil.</p>
    <p><b>3. Monte-Carlo knockout.</b> The bracket is played out <b>{meta['simulations']:,}</b> times — every
      tie decided by the model, with extra time and penalties on draws. Each team's share of simulated
      titles is its probability of winning.</p>
    <p style="color:var(--muted);margin-top:12px">Strength ratings reflect current form and market
      consensus; re-run <code>model.py</code> after each round to refresh every figure on this page.</p>
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
      if (x + 290 > window.innerWidth) x = e.clientX - 290;
      tip.style.left = x + 'px'; tip.style.top = y + 'px';
    }}
    function hide() {{ tip.style.opacity = '0'; }}
    document.querySelectorAll('.bar-row').forEach(function (el) {{
      var t = el.getAttribute('data-tip');
      el.addEventListener('mousemove', function (e) {{ show(e, t); }});
      el.addEventListener('mouseleave', hide);
      el.addEventListener('focus', function () {{
        var r = el.getBoundingClientRect(); show({{clientX:r.left+40, clientY:r.top}}, t);
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
<title>World Cup 2026 — Live ML Prediction</title>
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
