#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Step 3 — Unified Executive HTML & Google Material 3 Infographic Renderer ('site' and 'device' modes)."""

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyBboxPatch

from common import fmt_curr, fmt_dec, fmt_int, fmt_pct, get_mode, img_to_b64, load_config, resolve_path

SHELL_CSS = """
:root {
  --g-blue: #4285F4; --g-blue-dark: #1A73E8; --g-blue-tint: #E8F0FE; --g-blue-border: #D2E3FC;
  --g-green: #188038; --g-green-bright: #34A853; --g-green-tint: #E6F4EA; --g-green-border: #CEEAD6;
  --g-yellow: #F9AB00; --g-yellow-dark: #B06000; --g-yellow-tint: #FEF7E0; --g-yellow-border: #FDE293;
  --g-red: #C5221F; --g-red-bright: #EA4335; --g-red-tint: #FCE8E6; --g-red-border: #FAD2CF;
  --g-bg: #F8F9FA; --g-surface: #FFFFFF; --g-surface-alt: #F1F3F4;
  --g-ink: #202124; --g-body: #3C4043; --g-muted: #5F6368; --g-border: #DADCE0;
  --font-display: 'Google Sans', 'Product Sans', Roboto, Arial, sans-serif;
  --font-sans: 'Roboto', -apple-system, BlinkMacSystemFont, Arial, sans-serif;
  --font-mono: 'Roboto Mono', monospace;
  --radius-lg: 16px; --radius-md: 12px;
  --shadow-sm: 0 1px 2px 0 rgba(60,64,67,0.15), 0 1px 3px 1px rgba(60,64,67,0.08);
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: var(--font-sans); background: var(--g-bg); color: var(--g-ink); line-height: 1.55; -webkit-font-smoothing: antialiased; }
h1, h2, h3 { font-family: var(--font-display); }
code { font-family: var(--font-mono); font-size: 0.88em; background: var(--g-surface-alt); padding: 2px 6px; border-radius: 4px; border: 1px solid var(--g-border); color: var(--g-ink); }
.google-color-bar { position: fixed; top: 0; left: 0; right: 0; height: 4px; z-index: 100; background: linear-gradient(90deg, #4285F4 0% 25%, #EA4335 25% 50%, #FBBC04 50% 75%, #34A853 75% 100%); }
.app-shell { display: flex; min-height: 100vh; padding-top: 4px; }
.sidebar { width: 298px; background: var(--g-surface); border-right: 1px solid var(--g-border); display: flex; flex-direction: column; justify-content: space-between; position: fixed; top: 4px; left: 0; bottom: 0; z-index: 40; padding: 22px 16px; overflow-y: auto; }
.brand-box { padding: 0 10px 16px; border-bottom: 1px solid var(--g-border); margin-bottom: 14px; }
.google-badge { display: inline-flex; font-family: var(--font-display); font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: var(--g-blue-dark); background: var(--g-blue-tint); padding: 4px 10px; border-radius: 999px; margin-bottom: 10px; }
.google-badge.green { color: var(--g-green); background: var(--g-green-tint); }
.brand-title { font-family: var(--font-display); font-size: 16px; font-weight: 700; line-height: 1.3; }
.brand-sub { font-size: 12px; color: var(--g-muted); margin-top: 4px; }
.nav-section-label { font-family: var(--font-display); font-size: 10.5px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: var(--g-muted); padding: 0 12px; margin-bottom: 8px; }
.nav-list { display: flex; flex-direction: column; gap: 4px; }
.nav-item { display: flex; align-items: center; gap: 10px; width: 100%; text-align: left; padding: 9px 12px; border-radius: 999px; border: none; background: transparent; color: var(--g-body); font-family: var(--font-display); font-size: 12.8px; font-weight: 500; cursor: pointer; }
.nav-item:hover { background: var(--g-surface-alt); }
.nav-item.active { background: var(--g-blue-tint); color: var(--g-blue-dark); font-weight: 700; }
.nav-num { display: inline-flex; align-items: center; justify-content: center; width: 22px; height: 22px; border-radius: 50%; font-size: 11px; font-weight: 700; background: var(--g-surface-alt); color: var(--g-muted); flex-shrink: 0; }
.nav-item.active .nav-num { background: var(--g-blue-dark); color: #FFF; }
.sidebar-footer { padding-top: 14px; border-top: 1px solid var(--g-border); display: flex; flex-direction: column; gap: 8px; }
.sidebar-btn { width: 100%; padding: 9px 14px; border-radius: 999px; border: 1px solid var(--g-border); background: var(--g-surface); color: var(--g-body); font-family: var(--font-display); font-size: 12px; font-weight: 600; cursor: pointer; }
.sidebar-btn:hover { background: var(--g-surface-alt); }
.main-stage { flex: 1; margin-left: 298px; padding: 24px 36px 48px; max-width: 1420px; }
.top-bar { display: flex; align-items: center; justify-content: space-between; background: var(--g-surface); border: 1px solid var(--g-border); border-radius: var(--radius-md); padding: 10px 20px; margin-bottom: 20px; box-shadow: var(--shadow-sm); }
.progress-wrap { display: flex; align-items: center; gap: 14px; flex: 1; }
.progress-track { width: 180px; height: 6px; background: var(--g-surface-alt); border-radius: 999px; overflow: hidden; }
.progress-fill { height: 100%; background: var(--g-blue-dark); width: 12.5%; transition: width 0.25s ease; }
.step-indicator { font-family: var(--font-display); font-size: 12.8px; font-weight: 700; color: var(--g-body); }
.nav-btns { display: flex; gap: 8px; }
.btn-nav { padding: 8px 16px; border-radius: 999px; border: 1px solid var(--g-border); background: var(--g-surface); color: var(--g-body); font-family: var(--font-display); font-size: 12.5px; font-weight: 600; cursor: pointer; }
.btn-nav.primary { background: var(--g-blue-dark); color: #FFF; border-color: var(--g-blue-dark); }
.slide-card { background: var(--g-surface); border: 1px solid var(--g-border); border-radius: var(--radius-lg); padding: 30px 34px; box-shadow: var(--shadow-sm); margin-bottom: 26px; }
.slide-hidden { display: none !important; }
.slide-meta { display: flex; align-items: center; justify-content: space-between; padding-bottom: 12px; margin-bottom: 18px; border-bottom: 1px solid var(--g-border); flex-wrap: wrap; gap: 8px; }
.slide-kicker { font-family: var(--font-display); font-size: 11.5px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.07em; color: var(--g-blue-dark); }
.slide-scope { font-family: var(--font-mono); font-size: 11.5px; color: var(--g-muted); }
.slide-title { font-size: 24px; font-weight: 700; line-height: 1.28; margin-bottom: 10px; }
.slide-lead { font-size: 14.5px; color: var(--g-body); margin-bottom: 22px; max-width: 1060px; }
.grid-2 { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; margin-bottom: 20px; }
.grid-3 { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 18px; margin-bottom: 20px; }
.card { background: var(--g-bg); border: 1px solid var(--g-border); border-radius: var(--radius-md); padding: 20px; display: flex; flex-direction: column; justify-content: space-between; gap: 10px; }
.card.top-blue { border-top: 4px solid var(--g-blue); } .card.top-green { border-top: 4px solid var(--g-green-bright); }
.card.top-yellow { border-top: 4px solid var(--g-yellow); } .card.top-red { border-top: 4px solid var(--g-red-bright); }
.card.bg-blue { background: var(--g-blue-tint); border-color: var(--g-blue-border); }
.card.bg-green { background: var(--g-green-tint); border-color: var(--g-green-border); }
.card.bg-yellow { background: var(--g-yellow-tint); border-color: var(--g-yellow-border); }
.card.bg-red { background: var(--g-red-tint); border-color: var(--g-red-border); }
.badge { display: inline-block; padding: 4px 10px; border-radius: 999px; font-family: var(--font-display); font-size: 11px; font-weight: 700; text-transform: uppercase; margin-bottom: 8px; }
.badge.blue { background: #D2E3FC; color: #174EA6; } .badge.green { background: #CEEAD6; color: #0D652D; }
.badge.yellow { background: #FDE293; color: #B06000; } .badge.red { background: #FAD2CF; color: #A50E0E; }
.kpi-huge { font-family: var(--font-display); font-size: 28px; font-weight: 700; line-height: 1.15; margin-bottom: 4px; }
.kpi-sub { font-family: var(--font-display); font-size: 12.8px; font-weight: 700; margin-bottom: 8px; }
.card-text { font-size: 13.2px; color: var(--g-body); line-height: 1.55; }
.math-foot { margin-top: auto; padding-top: 10px; border-top: 1px dashed var(--g-border); font-family: var(--font-mono); font-size: 11px; color: var(--g-muted); }
.formula-box { background: var(--g-blue-tint); border: 1.5px solid var(--g-blue-border); border-radius: var(--radius-md); padding: 16px 20px; text-align: center; margin-bottom: 20px; }
.formula-label { font-family: var(--font-display); font-size: 11px; font-weight: 700; text-transform: uppercase; color: var(--g-blue-dark); margin-bottom: 6px; }
.formula-code { display: inline-block; background: #FFF; border: 1px solid var(--g-blue-border); padding: 9px 16px; border-radius: 8px; font-family: var(--font-mono); font-size: 13px; font-weight: 700; }
.table-box { border: 1px solid var(--g-border); border-radius: var(--radius-md); overflow: hidden; margin-bottom: 18px; background: #FFF; }
.table-head-bar { background: var(--g-surface-alt); padding: 11px 16px; border-bottom: 1px solid var(--g-border); display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; }
.table-head-title { font-family: var(--font-display); font-size: 12px; font-weight: 700; text-transform: uppercase; }
.table-scroll { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; text-align: left; font-size: 12.5px; }
th { background: var(--g-bg); color: var(--g-muted); font-family: var(--font-display); font-weight: 700; padding: 10px 12px; border-bottom: 1px solid var(--g-border); white-space: nowrap; }
td { padding: 10px 12px; border-bottom: 1px solid var(--g-border); color: var(--g-body); vertical-align: middle; }
tr:last-child td { border-bottom: none; }
.num { text-align: right; font-variant-numeric: tabular-nums; }
.row-subtotal td { background: var(--g-bg); font-weight: 700; color: var(--g-ink); border-top: 1.5px solid var(--g-border); }
.row-total td { background: var(--g-blue-tint); font-weight: 700; color: var(--g-blue-dark); border-top: 2px solid var(--g-blue-border); }
.row-raw td { background: var(--g-green-tint); font-weight: 700; color: var(--g-green); border-top: 1.5px dashed var(--g-green); }
.cell-highlight-blue { background: rgba(232,240,254,0.55); font-weight: 700; color: var(--g-blue-dark); }
.cell-highlight-green { background: rgba(230,244,234,0.7); font-weight: 700; color: var(--g-green); }
.cell-sub { display: block; font-size: 10.8px; color: var(--g-muted); font-weight: 400; margin-top: 2px; }
.bar-track { width: 100%; max-width: 110px; height: 6px; background: var(--g-surface-alt); border-radius: 999px; overflow: hidden; margin: 4px 0 0 auto; }
.bar-fill { height: 100%; border-radius: 999px; }
.pill-ctv { display: inline-block; padding: 2px 7px; border-radius: 999px; font-size: 10px; font-weight: 700; background: var(--g-blue-tint); color: var(--g-blue-dark); margin-left: 6px; }
.pill-nonctv { display: inline-block; padding: 2px 7px; border-radius: 999px; font-size: 10px; font-weight: 500; background: var(--g-surface-alt); color: var(--g-muted); margin-left: 6px; }
.table-foot-math { padding: 10px 16px; background: var(--g-bg); border-top: 1px solid var(--g-border); font-family: var(--font-mono); font-size: 11px; color: var(--g-muted); }
.vis-tabs { display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }
.vis-tab { padding: 8px 16px; border-radius: 999px; border: 1px solid var(--g-border); background: var(--g-bg); color: var(--g-body); font-family: var(--font-display); font-size: 12.5px; font-weight: 600; cursor: pointer; }
.vis-tab.active { background: var(--g-blue-dark); color: #FFF; border-color: var(--g-blue-dark); }
.vis-panel { background: var(--g-bg); border: 1px solid var(--g-border); border-radius: var(--radius-md); padding: 16px; margin-bottom: 16px; }
.vis-img { width: 100%; height: auto; display: block; border-radius: 10px; border: 1px solid var(--g-border); background: #FFF; }
.takeaway-bar { background: var(--g-blue-tint); border: 1px solid var(--g-blue-border); border-radius: var(--radius-md); padding: 15px 20px; display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-top: 12px; }
.takeaway-text { font-size: 13.2px; color: #174EA6; line-height: 1.5; }
.mode-switch-bar { display: flex; align-items: center; justify-content: space-between; gap: 12px; background: var(--g-surface); border: 1.5px solid var(--g-blue-border); border-radius: var(--radius-md); padding: 10px 18px; margin-bottom: 14px; box-shadow: var(--shadow-sm); flex-wrap: wrap; }
.mode-switch-label { font-family: var(--font-display); font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: var(--g-muted); }
.mode-switch-pills { display: flex; gap: 8px; flex-wrap: wrap; }
.mode-pill { padding: 8px 16px; border-radius: 999px; border: 1px solid var(--g-border); background: var(--g-bg); color: var(--g-body); font-family: var(--font-display); font-size: 12.8px; font-weight: 700; cursor: pointer; }
.mode-pill.active { background: var(--g-blue-dark); color: #FFF; border-color: var(--g-blue-dark); }
.mode-pill.active.green { background: var(--g-green); border-color: var(--g-green); }
.fallback-banner { background: var(--g-yellow-tint); border: 1px solid var(--g-yellow-border); border-left: 4px solid var(--g-yellow); border-radius: var(--radius-md); padding: 12px 18px; margin-bottom: 16px; font-size: 13.2px; color: #5F370E; }
ul.clean-list { list-style: none; display: flex; flex-direction: column; gap: 8px; }
ul.clean-list li { font-size: 13px; color: var(--g-body); padding-left: 16px; position: relative; }
ul.clean-list li::before { content: "•"; color: var(--g-blue-dark); font-weight: 900; position: absolute; left: 0; }
@media (max-width: 1024px) { .sidebar { position: static; width: 100%; height: auto; } .app-shell { flex-direction: column; } .main-stage { margin-left: 0; padding: 16px; } .grid-3, .grid-2 { grid-template-columns: 1fr; } }
@media print { .sidebar, .top-bar, .no-print { display: none !important; } .main-stage { margin-left: 0 !important; padding: 0 !important; } .deck-container.slide-hidden { display: none !important; } .deck-container:not(.slide-hidden) .slide-card { display: block !important; page-break-after: always; box-shadow: none !important; } }
"""


def _render_shell(page_title: str, meta: dict, decks: list[dict], default_deck: int = 0, auto_fallback_msg: str = "") -> str:
    d0 = decks[default_deck]
    decks_meta_js = json.dumps(
        [{"badge_label": d["badge_label"], "badge_cls": d["badge_cls"], "titles": d["titles"]} for d in decks],
        ensure_ascii=False,
    )
    switcher_html = ""
    if len(decks) > 1:
        pills = "".join(
            f'<button onclick="switchDeck({i})" class="mode-pill{" active" if i == default_deck else ""}{" " + d["badge_cls"] if d["badge_cls"] else ""}" data-mode-pill="{i}">{d["tab_label"]}</button>'
            for i, d in enumerate(decks)
        )
        switcher_html = f'<div class="mode-switch-bar no-print"><span class="mode-switch-label">Critério de Identificação de CTV:</span><div class="mode-switch-pills">{pills}</div></div>'
    fallback_html = f'<div class="fallback-banner">{auto_fallback_msg}</div>' if auto_fallback_msg else ""
    decks_body_html = "\n".join(
        f'<div class="deck-container{" slide-hidden" if i != default_deck else ""}" data-deck="{i}">{d["slides_html"]}</div>'
        for i, d in enumerate(decks)
    )
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{page_title}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Google+Sans:wght@400;500;700&family=Roboto+Mono:wght@400;500;700&family=Roboto:wght@400;500;700&display=swap" rel="stylesheet">
  <style>{SHELL_CSS}</style>
</head>
<body>
  <div class="google-color-bar"></div>
  <div class="app-shell">
    <aside class="sidebar">
      <div>
        <div class="brand-box">
          <span class="google-badge {d0['badge_cls']}" id="brandBadge">{d0['badge_label']}</span>
          <div class="brand-title">{meta['brand_name']}</div>
          <div class="brand-sub">Agência: {meta['agency_name']} • Campanha <code>{meta['campaign_id']}</code></div>
          <div class="brand-sub">Janela: {meta['start_date']} a {meta['end_date']}</div>
        </div>
        <div class="nav-section-label" id="navSectionLabel">Narrativa Linear ({len(d0['titles'])} Passos)</div>
        <div class="nav-list" id="sidebarNav"></div>
      </div>
      <div class="sidebar-footer">
        <button onclick="toggleViewMode()" class="sidebar-btn" id="viewBtnLabel">Modo Rolagem Contínua ({len(d0['titles'])} Páginas)</button>
        <button onclick="window.print()" class="sidebar-btn">Imprimir / Exportar PDF</button>
      </div>
    </aside>
    <main class="main-stage">
      {switcher_html}
      {fallback_html}
      <div class="top-bar" id="topControlBar">
        <div class="progress-wrap">
          <div class="progress-track"><div class="progress-fill" id="progressBar"></div></div>
          <span class="step-indicator" id="slideCounter"></span>
        </div>
        <div class="nav-btns">
          <button onclick="changeSlide(-1)" class="btn-nav">← Anterior</button>
          <button onclick="changeSlide(1)" class="btn-nav primary">Próximo Passo →</button>
        </div>
      </div>
      {decks_body_html}
    </main>
  </div>
  <script>
    const decksMeta = {decks_meta_js};
    let activeDeck = {default_deck}, currentSlide = 0, isScrollMode = false;
    const deckEls = document.querySelectorAll('.deck-container');
    const sidebarNav = document.getElementById('sidebarNav');
    const brandBadge = document.getElementById('brandBadge');
    const navSectionLabel = document.getElementById('navSectionLabel');
    const counter = document.getElementById('slideCounter');
    const progressBar = document.getElementById('progressBar');
    const viewBtnLabel = document.getElementById('viewBtnLabel');
    const topControlBar = document.getElementById('topControlBar');

    function activeSlides() {{ return deckEls[activeDeck].querySelectorAll('.slide-card'); }}
    function rebuildSidebar() {{
      const dm = decksMeta[activeDeck];
      brandBadge.textContent = dm.badge_label;
      brandBadge.className = 'google-badge' + (dm.badge_cls ? ' ' + dm.badge_cls : '');
      navSectionLabel.textContent = 'Narrativa Linear (' + dm.titles.length + ' Passos)';
      sidebarNav.innerHTML = dm.titles.map((t, i) =>
        '<button onclick="goToSlide(' + i + ')" class="nav-item' + (i === currentSlide ? ' active' : '') + '"><span class="nav-num">' + (i + 1) + '</span><span>' + t + '</span></button>'
      ).join('');
      document.querySelectorAll('[data-mode-pill]').forEach((p, idx) => p.classList.toggle('active', idx === activeDeck));
    }}
    function updateSlideView() {{
      const slides = activeSlides();
      const titles = decksMeta[activeDeck].titles;
      if (isScrollMode) {{
        slides.forEach(s => s.classList.remove('slide-hidden'));
        topControlBar.style.display = 'none';
        viewBtnLabel.textContent = 'Modo Apresentação (Slide a Slide)';
        showVisTab(3);
      }} else {{
        slides.forEach((s, idx) => s.classList.toggle('slide-hidden', idx !== currentSlide));
        topControlBar.style.display = 'flex';
        counter.textContent = 'Página ' + (currentSlide + 1) + ' de ' + slides.length + ' — ' + titles[currentSlide];
        progressBar.style.width = (((currentSlide + 1) / slides.length) * 100) + '%';
        viewBtnLabel.textContent = 'Modo Rolagem Contínua (' + slides.length + ' Páginas)';
      }}
      sidebarNav.querySelectorAll('.nav-item').forEach((item, idx) => item.classList.toggle('active', idx === currentSlide));
    }}
    function switchDeck(dIdx) {{
      activeDeck = dIdx; currentSlide = 0;
      deckEls.forEach((d, idx) => d.classList.toggle('slide-hidden', idx !== activeDeck));
      rebuildSidebar(); updateSlideView();
      window.scrollTo({{ top: 0, behavior: 'smooth' }});
    }}
    function goToSlide(idx) {{
      const slides = activeSlides();
      currentSlide = idx; updateSlideView();
      if (isScrollMode) slides[idx].scrollIntoView({{ behavior: 'smooth', block: 'start' }});
      else window.scrollTo({{ top: 0, behavior: 'smooth' }});
    }}
    function changeSlide(d) {{ const slides = activeSlides(); const n = currentSlide + d; if (n >= 0 && n < slides.length) goToSlide(n); }}
    function toggleViewMode() {{ isScrollMode = !isScrollMode; updateSlideView(); }}
    function showVisTab(tabIdx) {{
      const root = deckEls[activeDeck];
      const panels = root.querySelectorAll('.vis-panel');
      const btns = root.querySelectorAll('.vis-tab');
      btns.forEach((b, i) => b.classList.toggle('active', i === tabIdx));
      panels.forEach((p, i) => p.classList.toggle('slide-hidden', tabIdx !== 3 && i !== tabIdx));
    }}
    document.addEventListener('keydown', (e) => {{
      if (!isScrollMode && e.key === 'ArrowRight') changeSlide(1);
      if (!isScrollMode && e.key === 'ArrowLeft') changeSlide(-1);
    }});
    rebuildSidebar(); updateSlideView();
  </script>
</body>
</html>
"""


def _setup_mpl():
    plt.rcParams["font.sans-serif"] = "DejaVu Sans"
    plt.rcParams["axes.edgecolor"] = "#DADCE0"
    plt.rcParams["axes.linewidth"] = 0.9
    plt.rcParams["text.parse_math"] = False


def _generate_site_infographics(res: dict, out_dir: Path) -> tuple[str, str, str]:
    _setup_mpl()
    meta, tot, blk = res["meta"], res["campaign_totals"], res["ctv_block_consolidated"]
    ctrl_all = res["p2c_control_vs_ctv"]["control_multi_no_ctv_all"]
    ctrl_camp = res["p2c_control_vs_ctv"]["control_multi_no_ctv_camp"]
    combo_blk = res["p2c_control_vs_ctv"]["ctv_combo_block_all"]
    ctv_chans = res["ctv_channels"]
    non_ctv_names = [s["site"] for s in res["all_sites"] if not s["is_ctv"]][:3]
    fl_labels = meta.get("purchase_activity_labels") or {}
    clean_fl = []
    for lbl in list(fl_labels.values())[:3]:
        low = str(lbl).lower()
        if low.startswith("web"):
            clean_fl.append("• Web E-commerce (Compra Oficial)")
        elif low.startswith("ios"):
            clean_fl.append("• App iOS (in_app_purchase)")
        elif low.startswith("android"):
            clean_fl.append("• App Android (in_app_purchase)")
        else:
            clean_fl.append(f"• {str(lbl)[:34]}")
    fl_lines = "\n".join(clean_fl) or "• 1 Tag Oficial de Compra por Plataforma"

    img1 = out_dir / "ilustracao_1_jornada_ctv.png"
    fig, ax = plt.subplots(figsize=(15, 6.2), dpi=220)
    ax.set_xlim(0, 15); ax.set_ylim(0, 6.2); ax.axis("off"); fig.patch.set_facecolor("#FFFFFF")
    ax.text(0.4, 5.75, f"ILUSTRAÇÃO 1 • A JORNADA REAL EM CTV vs. O PONTO CEGO DE ATRIBUIÇÃO ({meta['brand_name'].upper()})", fontsize=12.8, fontweight="bold", color="#1A73E8")
    ax.text(0.4, 5.32, "Na Smart TV ninguém clica (100% View-Through). O impacto começa na tela grande da sala e a compra fecha no celular.", fontsize=10, color="#5F6368")

    ax.add_patch(FancyBboxPatch((0.4, 1.75), 4.1, 3.2, boxstyle="round,pad=0.12,rounding_size=0.2", ec="#1A73E8", fc="#E8F0FE", lw=2))
    ax.text(2.45, 4.55, "1. IMPACTO NA SMART TV (SALA)", fontsize=10.5, fontweight="bold", color="#1A73E8", ha="center")
    ax.text(2.45, 4.08, "Canais com CTV no Nome na Campanha:", fontsize=9, fontweight="bold", color="#202124", ha="center")
    site_lines = "\n".join(f"• {c['site']} ({fmt_pct(c['overlap_pct_campaign'])} overlap)" for c in ctv_chans[:4]) or "• Nenhum Site com 'CTV' no nome\n  (Consulte a visão Device Type)"
    ax.text(2.45, 3.32, site_lines, fontsize=8.4, color="#3C4043", ha="center", va="center", linespacing=1.5)
    ax.text(2.45, 2.22, f"100% View-Through (Zero Clique)\nCo-Viewing Médio: {fmt_dec(tot['coview_factor_campaign'])}x pessoas/tela", fontsize=8.5, fontweight="bold", color="#1A73E8", ha="center", va="center", bbox=dict(boxstyle="round,pad=0.35", facecolor="#FFF", edgecolor="#D2E3FC"))

    ax.annotate("", xy=(5.45, 3.35), xytext=(4.65, 3.35), arrowprops=dict(arrowstyle="->,head_width=0.35,head_length=0.35", color="#1A73E8", lw=3))
    ax.text(5.05, 3.85, "Mudança\nde Tela", fontsize=8.5, fontweight="bold", color="#1A73E8", ha="center")

    ax.add_patch(FancyBboxPatch((5.55, 1.75), 4.1, 3.2, boxstyle="round,pad=0.12,rounding_size=0.2", ec="#F9AB00", fc="#FEF7E0", lw=2))
    ax.text(7.6, 4.55, "2. BUSCA E CLIQUE NO CELULAR", fontsize=10.5, fontweight="bold", color="#B06000", ha="center")
    ax.text(7.6, 4.08, "Canais de Ação / Performance:", fontsize=9, fontweight="bold", color="#202124", ha="center")
    ax.text(7.6, 3.32, "\n".join([f"• {s}" for s in non_ctv_names] + ["• Paid Search / Performance"]), fontsize=8.5, color="#3C4043", ha="center", va="center", linespacing=1.5)
    ax.text(7.6, 2.22, f"Consumidor clica no anúncio mobile\ne conclui o pedido ({meta['brand_name']})", fontsize=8.3, fontweight="bold", color="#B06000", ha="center", va="center", bbox=dict(boxstyle="round,pad=0.35", facecolor="#FFF", edgecolor="#FDE293"))

    ax.annotate("", xy=(10.6, 3.35), xytext=(9.8, 3.35), arrowprops=dict(arrowstyle="->,head_width=0.35,head_length=0.35", color="#188038", lw=3))
    ax.text(10.2, 3.85, "Último\nClique", fontsize=8.5, fontweight="bold", color="#188038", ha="center")

    ax.add_patch(FancyBboxPatch((10.7, 1.75), 3.9, 3.2, boxstyle="round,pad=0.12,rounding_size=0.2", ec="#188038", fc="#E6F4EA", lw=2))
    ax.text(12.65, 4.55, "3. COMPRA FEITA (WEB / APP)", fontsize=10.5, fontweight="bold", color="#188038", ha="center")
    ax.text(12.65, 4.08, "Tags Transacionais Oficiais (1/Plat.):", fontsize=9, fontweight="bold", color="#202124", ha="center")
    ax.text(12.65, 3.32, fl_lines, fontsize=8.0, color="#3C4043", ha="center", va="center", linespacing=1.5)
    ax.text(12.65, 2.22, f"Total P2C: {fmt_int(tot['p2c_total_conversions'])} compras\nReceita: {fmt_curr(tot['p2c_total_revenue'])}", fontsize=8.5, fontweight="bold", color="#188038", ha="center", va="center", bbox=dict(boxstyle="round,pad=0.35", facecolor="#FFF", edgecolor="#CEEAD6"))

    ax.add_patch(FancyBboxPatch((0.4, 0.25), 6.85, 1.15, boxstyle="round,pad=0.1,rounding_size=0.15", ec="#FAD2CF", fc="#FCE8E6", lw=1.5))
    ax.text(3.82, 1.05, "LEITURA TRADICIONAL DE ÚLTIMO TOQUE (STANDARD):", fontsize=9, fontweight="bold", color="#C5221F", ha="center")
    bad_desc = (
        f"Sub-atribui vídeo {ctv_chans[0]['site']} ({fmt_int(ctv_chans[0]['std_conversions'])} comp.) e infla banner IP ({fmt_int(ctv_chans[1]['std_conversions'])} comp.)"
        if (blk["std_conversions"] > blk["total_attributed_conversions"] and len(ctv_chans) >= 2)
        else f"Perde o elo entre TV e Celular → Credita apenas {fmt_int(blk['std_conversions'])} compras ({fmt_pct(blk['std_share_pct'])}) ao Bloco CTV"
    )
    ax.text(3.82, 0.58, bad_desc, fontsize=8.2, color="#A50E0E", ha="center")

    ax.add_patch(FancyBboxPatch((7.65, 0.25), 6.95, 1.15, boxstyle="round,pad=0.1,rounding_size=0.15", ec="#CEEAD6", fc="#E6F4EA", lw=1.5))
    ax.text(11.12, 1.05, "METODOLOGIA DE INTERSEÇÃO DE ALCANCE (1+) & GANHO MARGINAL:", fontsize=9, fontweight="bold", color="#188038", ha="center")
    ax.text(11.12, 0.58, f"Reconecta a interseção Cross-Device ({fmt_pct(blk['overlap_pct_campaign_sum'])}) → {fmt_dec(blk['total_attributed_conversions'], 1)} compras ({fmt_pct(blk['share_campaign_attributed_pct'])}) | {fmt_curr(blk['total_attributed_revenue'])}", fontsize=8.3, color="#0D652D", ha="center")
    plt.tight_layout(pad=0.3); plt.savefig(img1, dpi=220); plt.close(fig)

    f_eff = res["funnel_cvr_efficiency"]
    f_non, f_blk = f_eff["non_ctv_base"], f_eff["ctv_block"]
    is_cvr_mode = f_eff["metric_source"] == "cvr_produto_compra"
    cap_tag = " [teto 50%]" if f_blk["cap_applied"] else ""

    img2 = out_dir / "ilustracao_2_venn_intersecao.png"
    fig, ax = plt.subplots(figsize=(15, 6.4), dpi=220)
    ax.set_xlim(0, 15); ax.set_ylim(0, 6.4); ax.axis("off"); fig.patch.set_facecolor("#FFFFFF")
    ax.text(0.4, 5.95, f"ILUSTRAÇÃO 2 • DIAGRAMA DE VENN DAS 3 COORTES DE ALCANCE (1+) — {meta['brand_name'].upper()}", fontsize=13, fontweight="bold", color="#1A73E8")
    ax.text(0.4, 5.52, f"Universo Total da Campanha ({meta['campaign_id']}): {fmt_int(tot['reach_devices'])} dispositivos ({fmt_int(tot['reach_coviewed'])} espectadores c/ Co-Viewing) e {fmt_int(tot['p2c_total_conversions'])} compras:", fontsize=10, color="#5F6368")
    ax.add_patch(Circle((6.1, 3.25), 1.85, facecolor="#4285F4", alpha=0.14, edgecolor="#1A73E8", lw=2.5))
    ax.add_patch(Circle((8.6, 3.25), 2.05, facecolor="#34A853", alpha=0.14, edgecolor="#188038", lw=2.5))
    ax.text(5.1, 3.95, "COORTE 1\nSó Canais CTV", fontsize=9.5, fontweight="bold", color="#1A73E8", ha="center", va="center")
    ax.text(5.1, 3.05, f"Alcance Exclusivo:\n{fmt_pct(blk['exclusive_pct_campaign_sum'])} da campanha\n\nVendas Solo P2C:\n{fmt_int(blk['p2c_solo_conversions'])} compras ({fmt_curr(blk['p2c_solo_revenue'])})", fontsize=8.2, color="#202124", ha="center", va="center")
    ax.text(7.25, 4.15, "COORTE 3\nINTERSEÇÃO (1+)", fontsize=9.5, fontweight="bold", color="#188038", ha="center", va="center")
    ax.text(7.25, 3.20, f"Alcance Compartilhado:\n{fmt_pct(blk['overlap_pct_campaign_sum'])} da campanha\n\nVolume na Interseção:\n{fmt_dec(blk['intersecao_compras_1plus'], 1)} compras", fontsize=8.3, fontweight="bold", color="#202124", ha="center", va="center")
    ax.text(7.25, 2.15, "Compras Assistidas =\nInterseção × AF_e (CVR)", fontsize=8, fontweight="bold", color="#188038", ha="center", va="center", bbox=dict(boxstyle="round,pad=0.25", facecolor="#E6F4EA", edgecolor="#188038"))
    ax.text(9.6, 3.95, "COORTE 2\nSó Outros Canais", fontsize=9.5, fontweight="bold", color="#3C4043", ha="center", va="center")
    ax.text(9.6, 3.05, f"Grupo de Controle\n(Sem toque de CTV)\n\n{fmt_int(ctrl_all['conversions'])} pedidos multi\nAOV Camp: {fmt_curr(ctrl_camp['aov'])}", fontsize=8.2, color="#202124", ha="center", va="center")
    ax.add_patch(FancyBboxPatch((0.4, 1.65), 3.3, 3.2, boxstyle="round,pad=0.12,rounding_size=0.18", ec="#1A73E8", fc="#F8F9FA", lw=1.8))
    ax.text(2.05, 4.45, "PASSO 1: SOLO (P2C)", fontsize=9.5, fontweight="bold", color="#1A73E8", ha="center")
    ax.text(2.05, 3.05, f"Não extrapolamos o\nalcance exclusivo.\nContamos apenas as\nvendas Solo reais\nobservadas no P2C:\n• {fmt_int(blk['p2c_solo_conversions'])} compras Solo\n• {fmt_curr(blk['p2c_solo_revenue'])}", fontsize=8.4, color="#3C4043", ha="center", va="center")
    ax.add_patch(FancyBboxPatch((11.3, 1.65), 3.3, 3.2, boxstyle="round,pad=0.12,rounding_size=0.18", ec="#188038", fc="#F8F9FA", lw=1.8))
    ax.text(12.95, 4.45, "PASSO 2 & 3: VOLUME + R$", fontsize=9.5, fontweight="bold", color="#188038", ha="center")
    ax.text(12.95, 3.05, f"1) Volume (Compras):\nFração Atribuível AF_e\ndo CVR Produto→Compra\n({fmt_pct(f_blk['capped_afe_pct'])}{cap_tag}).\n2) Valor (R$ Ticket Médio):\nPrêmio de AOV (+{fmt_pct(combo_blk['lift_valor_pct'])})\nsomado em R$ na receita.", fontsize=8.1, color="#3C4043", ha="center", va="center")
    ax.add_patch(FancyBboxPatch((0.4, 0.25), 14.2, 0.95, boxstyle="round,pad=0.1,rounding_size=0.15", ec="#1A73E8", fc="#E8F0FE", lw=1.8))
    ax.text(7.5, 0.72, "EQUAÇÃO UNIFICADA:  Compras = Solo P2C + (Interseção 1+ × AF_e CVR Produto→Compra)   |   Receita (R$) = Solo + Base Assistida + Prêmio AOV (R$)", fontsize=8.8, fontweight="bold", color="#202124", ha="center", va="center")
    plt.tight_layout(pad=0.3); plt.savefig(img2, dpi=220); plt.close(fig)

    img3 = out_dir / "ilustracao_3_lifts_marginais.png"
    fig = plt.figure(figsize=(15.6, 6.3), dpi=220); fig.patch.set_facecolor("#FFFFFF")
    fig.text(0.028, 0.94, f"ILUSTRAÇÃO 3 • EVIDÊNCIAS EMPÍRICAS: FUNIL (CVR), TICKET MÉDIO (AOV) & ACELERAÇÃO DE TOQUES — {meta['brand_name'].upper()}", fontsize=11.9, fontweight="bold", color="#1A73E8")
    fig.text(0.028, 0.885, "Atribuição usa CVR Produto→Compra (AF_e, teto 50%) p/ volume e Δ AOV p/ prêmio em R$; a redução de toques no P2C é exibida como diagnóstico comportamental:", fontsize=9.3, color="#5F6368")
    ax1 = fig.add_axes([0.048, 0.14, 0.272, 0.62])
    ax2 = fig.add_axes([0.380, 0.14, 0.272, 0.62])
    ax3 = fig.add_axes([0.712, 0.14, 0.268, 0.62])
    top_chans = [c for c in ctv_chans if c.get("prod_views", 0) >= 30 and c.get("purc_std_for_cvr", 0) >= 5][:2] or ctv_chans[:2]
    short_names = [c["site"].replace("DV360_", "").replace("DV360-", "") for c in top_chans]
    if is_cvr_mode:
        cats1 = [f"{sn}\n(Funil Std)" for sn in short_names] + ["Bloco CTV\n(Funil Std)"]
        ctrl_v = [f_non["cvr_pct"]] * (len(top_chans) + 1)
        ctv_v = [c["cvr_prod_to_purc_pct"] for c in top_chans] + [f_blk["cvr_pct"]]
        lifts1 = [f"AF_e: {fmt_pct(c['lift_lente2_efic_pct'])}{' *' if c.get('afe_cap_applied') else ''}" for c in top_chans] + [f"AF_e: {fmt_pct(f_blk['capped_afe_pct'])}{' *' if f_blk['cap_applied'] else ''}"]
        ttl1, ylbl1 = "1. CVR Produto→Compra (Volume Assistido)", "CVR Produto → Compra (%)"
    else:
        cats1 = [f"{sn}\n(Fallback)" for sn in short_names] + ["Bloco CTV\n(Fallback)"]
        ctrl_v = [0.0] * (len(top_chans) + 1)
        ctv_v = [c["lift_lente2_efic_pct"] for c in top_chans] + [f_blk["capped_afe_pct"]]
        lifts1 = [f"AF_e: {fmt_pct(v)}" for v in ctv_v]
        ttl1, ylbl1 = "1. Fração AF_e (Fallback s/ Tag Produto)", "Fração Atribuível AF_e (%)"
    x, w = list(range(len(cats1))), 0.33
    b1 = ax1.bar([i - w / 2 for i in x], ctrl_v, width=w, color="#9AA0A6", label="Base Sem CTV")
    b2 = ax1.bar([i + w / 2 for i in x], ctv_v, width=w, color="#34A853", label="Expostos CTV")
    ax1.set_title(ttl1, fontsize=9.6, fontweight="bold", pad=11)
    ax1.set_xticks(x); ax1.set_xticklabels(cats1, fontsize=8.1, fontweight="bold"); ax1.set_ylabel(ylbl1, fontsize=8.5)
    max_v = max(ctrl_v + ctv_v + [0.5]); ax1.set_ylim(0, max_v * 1.45); ax1.grid(axis="y", linestyle="--", alpha=0.4); ax1.legend(loc="upper right", fontsize=7.8)
    for bar in b1:
        ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max_v * 0.025, fmt_pct(bar.get_height()), ha="center", fontsize=7.9, fontweight="bold", color="#5F6368")
    for idx, bar in enumerate(b2):
        ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max_v * 0.025, fmt_pct(bar.get_height()), ha="center", fontsize=7.9, fontweight="bold", color="#188038")
        ax1.text(x[idx], max(ctrl_v[idx], bar.get_height()) + max_v * 0.15, lifts1[idx], ha="center", fontsize=7.6, fontweight="bold", color="#188038", bbox=dict(boxstyle="round,pad=0.22", facecolor="#E6F4EA", edgecolor="#34A853"))

    cats2 = [f"{sn}\n(Campanha)" for sn in short_names] + ["Bloco CTV\n(Campanha)"]
    ctrl_aov = [c["base_ctrl_aov"] for c in top_chans] + [ctrl_camp["aov"]]
    ctv_aov = [c["aov_valuation"] for c in top_chans] + [combo_blk["aov"]]
    lifts2 = [f"+{fmt_curr(c['aov_delta_brl'])}" for c in top_chans] + [f"+{fmt_curr(max(0.0, combo_blk['aov'] - ctrl_camp['aov']))}"]
    b3 = ax2.bar([i - w / 2 for i in x], ctrl_aov, width=w, color="#9AA0A6", label="Controle Sem CTV")
    b4 = ax2.bar([i + w / 2 for i in x], ctv_aov, width=w, color="#4285F4", label="Com CTV")
    ax2.set_title("2. Ticket Médio / AOV (Prêmio em R$)", fontsize=9.6, fontweight="bold", pad=11)
    ax2.set_xticks(x); ax2.set_xticklabels(cats2, fontsize=8.1, fontweight="bold"); ax2.set_ylabel("Ticket Médio (R$)", fontsize=8.5)
    max_a = max(ctrl_aov + ctv_aov + [150.0]); ax2.set_ylim(0, max_a * 1.45); ax2.grid(axis="y", linestyle="--", alpha=0.4); ax2.legend(loc="upper right", fontsize=7.8)
    for bar in b3:
        ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 2.5, f"R$ {bar.get_height():.0f}", ha="center", fontsize=8.0, fontweight="bold", color="#5F6368")
    for idx, bar in enumerate(b4):
        ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 2.5, f"R$ {bar.get_height():.0f}", ha="center", fontsize=8.0, fontweight="bold", color="#1A73E8")
        ax2.text(x[idx], max(ctrl_aov[idx], bar.get_height()) + max_a * 0.15, lifts2[idx], ha="center", fontsize=7.6, fontweight="bold", color="#1A73E8", bbox=dict(boxstyle="round,pad=0.22", facecolor="#E8F0FE", edgecolor="#4285F4"))

    t_chans = [c for c in ctv_chans if c.get("p2c_combo_all_conversions", 0) > 0][:2]
    cats3 = [f"{c['site'].replace('DV360_', '').replace('DV360-', '')}\n(P2C 14d)" for c in t_chans] + ["Bloco CTV\n(P2C 14d)"]
    x3 = list(range(len(cats3)))
    base_t = ctrl_all["avg_non_ctv_touches"]
    ctrl_t = [base_t] * len(cats3)
    ctv_t = [c["p2c_combo_all_nonctv_touches"] for c in t_chans] + [combo_blk["avg_non_ctv_touches"]]
    lifts3 = [f"{fmt_pct(((t - base_t) / base_t * 100.0) if base_t > 0 else 0.0, 1)}" if t <= base_t else f"+{fmt_pct(((t - base_t) / base_t * 100.0), 1)}" for t in ctv_t]
    b5 = ax3.bar([i - w / 2 for i in x3], ctrl_t, width=w, color="#9AA0A6", label="Controle Sem CTV")
    b6 = ax3.bar([i + w / 2 for i in x3], ctv_t, width=w, color="#F9AB00", label="Jornadas Com CTV")
    ax3.set_title("3. Toques Não-CTV (Diagnóstico P2C)", fontsize=9.6, fontweight="bold", pad=11)
    ax3.set_xticks(x3); ax3.set_xticklabels(cats3, fontsize=8.1, fontweight="bold"); ax3.set_ylabel("Média Toques Não-CTV", fontsize=8.5)
    max_t = max(ctrl_t + ctv_t + [2.0]); ax3.set_ylim(0, max_t * 1.45); ax3.grid(axis="y", linestyle="--", alpha=0.4); ax3.legend(loc="upper right", fontsize=7.8)
    for bar in b5:
        ax3.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max_t * 0.025, fmt_dec(bar.get_height()), ha="center", fontsize=8.0, fontweight="bold", color="#5F6368")
    for idx, bar in enumerate(b6):
        ax3.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max_t * 0.025, fmt_dec(bar.get_height()), ha="center", fontsize=8.0, fontweight="bold", color="#B06000")
        ax3.text(x3[idx], max(ctrl_t[idx], bar.get_height()) + max_t * 0.15, f"{lifts3[idx]} toques", ha="center", fontsize=7.6, fontweight="bold", color="#B06000", bbox=dict(boxstyle="round,pad=0.22", facecolor="#FEF7E0", edgecolor="#F9AB00"))
    plt.savefig(img3, dpi=220); plt.close(fig)
    return img_to_b64(img1), img_to_b64(img2), img_to_b64(img3)


def _build_site_deck(res: dict, out_dir: Path) -> dict:
    b64_1, b64_2, b64_3 = _generate_site_infographics(res, out_dir)
    meta, tot, blk = res["meta"], res["campaign_totals"], res["ctv_block_consolidated"]
    f_eff = res["funnel_cvr_efficiency"]
    f_non, f_blk = f_eff["non_ctv_base"], f_eff["ctv_block"]
    is_cvr_mode = f_eff["metric_source"] == "cvr_produto_compra"
    ctrl_all = res["p2c_control_vs_ctv"]["control_multi_no_ctv_all"]
    ctrl_camp = res["p2c_control_vs_ctv"]["control_multi_no_ctv_camp"]
    combo_blk = res["p2c_control_vs_ctv"]["ctv_combo_block_all"]
    ctv_chans, all_sites, dv_rec = res["ctv_channels"], res["all_sites"], res["dv360_reconciliation"]

    reach_rows = "".join(
        f"""<tr>
          <td><strong>{i}. <code>{c['site']}</code></strong></td>
          <td class="num">{fmt_int(c['impressions'])}</td><td class="num">{fmt_curr(c['cost'])}</td>
          <td class="num">{fmt_int(c['unique_reach'])}</td>
          <td class="num">{fmt_int(c['coviewed_reach'])} <span class="cell-sub">({fmt_dec(c['coview_factor'])}x)</span></td>
          <td class="num">{fmt_int(c['exclusive_reach_1plus'])} <span class="cell-sub">({fmt_pct(c['exclusive_pct_campaign'])} camp.)</span></td>
          <td class="num"><strong>{fmt_int(c['duplicate_reach_1plus'])}</strong> <span class="cell-sub">({fmt_pct(c['duplicate_pct_site'])} conect.)</span></td>
          <td class="num"><strong>{fmt_pct(c['overlap_pct_campaign'])}</strong><div class="bar-track"><div class="bar-fill" style="width:{min(100, max(3, int(round(c['overlap_pct_campaign']*2.2))))}%;background:var(--g-blue);"></div></div></td>
          <td class="num cell-highlight-blue">{fmt_dec(c['intersecao_compras_1plus'], 1)} comp.</td>
        </tr>"""
        for i, c in enumerate(ctv_chans, 1)
    ) or '<tr><td colspan="9" style="text-align:center;color:var(--g-muted);">Nenhum Site com CTV no nome detectado — utilize a visão Device Type (Smart TV + STB).</td></tr>'

    lifts_rows = f"""<tr class="row-subtotal">
      <td><strong>Base Sem CTV (Não-CTV)</strong><div class="cell-sub">Funil Standard Não-CTV | Controle P2C s/ CTV: {fmt_int(ctrl_camp['conversions'])} ped. camp. ({fmt_int(ctrl_all['conversions'])} jornada)</div></td>
      <td class="num">{fmt_int(f_non['product_views']) if is_cvr_mode else '—'}</td>
      <td class="num">{fmt_int(f_non['purchases'])}</td>
      <td class="num">{fmt_pct(f_non['cvr_pct']) if is_cvr_mode else '—'}</td>
      <td class="num">Base (0,00%)</td>
      <td class="num">{fmt_curr(ctrl_camp['aov'])}<div class="cell-sub">Jornada: {fmt_curr(ctrl_all['aov'])}</div></td>
      <td class="num">Base (R$ 0,00)</td>
    </tr>""" + "".join(
        f"""<tr>
          <td><strong><code>{c['site']}</code></strong><div class="cell-sub">P2C: {fmt_int(c['p2c_solo_conversions'])} Solo + {fmt_int(c['p2c_combo_all_conversions'])} Combo{' • AF_e bloco (amostra <30/5)' if (is_cvr_mode and c.get('lift_calibration_source') != 'cvr_direto_canal') else ''}</div></td>
          <td class="num">{fmt_int(c['prod_views']) if is_cvr_mode else '—'}</td>
          <td class="num">{fmt_int(c['purc_std_for_cvr'])}</td>
          <td class="num">{f"<strong>{fmt_pct(c['cvr_prod_to_purc_pct'])}</strong>" if (is_cvr_mode and c.get('prod_views', 0) > 0) else '—'}</td>
          <td class="num cell-highlight-green">{fmt_pct(c['lift_lente2_efic_pct'])}{f'<div class="cell-sub">Teto 50% (bruto {fmt_pct(c["raw_afe_pct"])})</div>' if c.get('afe_cap_applied') else ''}</td>
          <td class="num"><strong>{fmt_curr(c['aov_valuation'])}</strong><div class="cell-sub">Base: {fmt_curr(c['base_ctrl_aov'])}</div></td>
          <td class="num cell-highlight-blue">+{fmt_curr(c['aov_delta_brl'])} / ped.<div class="cell-sub">(+{fmt_pct(c['lift_lente1_specific_pct'])})</div></td>
        </tr>"""
        for c in ctv_chans
    ) + f"""<tr class="row-total">
      <td><strong>BLOCO CTV CONSOLIDADO</strong></td>
      <td class="num">{fmt_int(f_blk['product_views']) if is_cvr_mode else '—'}</td>
      <td class="num">{fmt_int(f_blk['purchases'])}</td>
      <td class="num">{f"{fmt_pct(f_blk['cvr_pct'])} ({fmt_dec(f_blk['cvr_lift_mult'])}x)" if is_cvr_mode else 'Fallback AOV'}</td>
      <td class="num">{fmt_pct(f_blk['capped_afe_pct'])}{f" (teto 50% | bruto {fmt_pct(f_blk['raw_afe_pct'])})" if f_blk['cap_applied'] else ''}</td>
      <td class="num">{fmt_curr(combo_blk['aov'])}</td>
      <td class="num">+{fmt_curr(max(0.0, combo_blk['aov'] - ctrl_camp['aov']))} / ped. (+{fmt_pct(combo_blk['lift_valor_pct'])})</td>
    </tr>"""

    base_t = ctrl_all["avg_non_ctv_touches"]
    blk_t = combo_blk["avg_non_ctv_touches"]
    blk_t_pct = ((blk_t - base_t) / base_t * 100.0) if base_t > 0 else 0.0
    touch_rows = f"""<tr class="row-subtotal">
      <td><strong>Grupo de Controle: Jornadas Multi-Canal Sem CTV</strong><div class="cell-sub">Pedidos no P2C sem nenhum toque de CTV ({fmt_int(ctrl_camp['conversions'])} restrito à camp.)</div></td>
      <td class="num">—</td>
      <td class="num">{fmt_int(ctrl_all['conversions'])}</td>
      <td class="num"><strong>{fmt_dec(base_t)} toques</strong><div class="cell-sub">Camp: {fmt_dec(ctrl_camp['avg_non_ctv_touches'])} toques</div></td>
      <td class="num">Base (0,00)</td>
      <td class="num">Base (0,00%)</td>
    </tr>""" + "".join(
        f"""<tr>
          <td><strong>Jornadas Com <code>{c['site']}</code></strong><div class="cell-sub">{'Com compras multi-canal observadas no P2C' if c['p2c_combo_all_conversions'] > 0 else 'Apenas venda Solo observada no P2C'}</div></td>
          <td class="num">{fmt_int(c['p2c_solo_conversions'])}</td>
          <td class="num">{fmt_int(c['p2c_combo_all_conversions'])}</td>
          <td class="num">{f"<strong>{fmt_dec(c['p2c_combo_all_nonctv_touches'])} toques</strong><div class='cell-sub'>Camp: {fmt_dec(c['p2c_combo_camp_nonctv_touches'])} toques</div>" if c['p2c_combo_all_conversions'] > 0 else '—'}</td>
          <td class="num">{f"{fmt_dec(c['p2c_combo_all_nonctv_touches'] - base_t, sign=True)} toques" if c['p2c_combo_all_conversions'] > 0 else '—'}</td>
          <td class="num{' cell-highlight-green' if (c['p2c_combo_all_conversions'] > 0 and c['p2c_combo_all_nonctv_touches'] < base_t) else ''}">{f"{fmt_pct((c['p2c_combo_all_nonctv_touches'] - base_t) / base_t * 100.0, sign=True)}" if (c['p2c_combo_all_conversions'] > 0 and base_t > 0) else '—'}</td>
        </tr>"""
        for c in ctv_chans if (c["p2c_combo_all_conversions"] > 0 or c["p2c_solo_conversions"] > 0)
    ) + f"""<tr class="row-total">
      <td><strong>BLOCO CTV CONSOLIDADO (Jornadas Multi-Canal Com CTV)</strong></td>
      <td class="num">{fmt_int(blk['p2c_solo_conversions'])}</td>
      <td class="num">{fmt_int(combo_blk['conversions'])}</td>
      <td class="num">{fmt_dec(blk_t)} toques</td>
      <td class="num">{fmt_dec(blk_t - base_t, sign=True)} toques</td>
      <td class="num">{fmt_pct(blk_t_pct, sign=True) if combo_blk['conversions'] > 0 else '—'}</td>
    </tr>"""

    res_rows = ""
    for i, c in enumerate(ctv_chans, 1):
        rc = "var(--g-green)" if (c["roas_attributed"] or 0) >= 1.0 else ("var(--g-red)" if c["cost"] > 0 else "var(--g-muted)")
        rs = f"ROAS: {fmt_dec(c['roas_attributed'])}x" if c["roas_attributed"] is not None else "Entrega s/ custo"
        cs = f"CPA: {fmt_curr(c['cpa_attributed'])}" if c["cpa_attributed"] is not None else "—"
        res_rows += f"""<tr>
          <td><strong>{i}. <code>{c['site']}</code></strong><div class="cell-sub">Overlap 1+: {fmt_pct(c['overlap_pct_campaign'])} ({fmt_pct(c['duplicate_pct_site'])} conect.)</div></td>
          <td class="num">{fmt_curr(c['cost'])}<div class="cell-sub">{fmt_pct(c['cost_share_pct'])} do budget</div></td>
          <td class="num">{fmt_int(c['std_conversions'])} comp.<div class="cell-sub">{fmt_curr(c['std_revenue'])}</div></td>
          <td class="num"><strong>{fmt_int(c['p2c_solo_conversions'])} comp.</strong><div class="cell-sub">{fmt_curr(c['p2c_solo_revenue'])}</div></td>
          <td class="num"><strong>{fmt_dec(c['intersecao_compras_1plus'], 1)} comp.</strong><div class="cell-sub">AF_e: {fmt_pct(c['lift_lente2_efic_pct'])}{' (teto 50%)' if c.get('afe_cap_applied') else ''}</div></td>
          <td class="num cell-highlight-green">{fmt_dec(c['total_attributed_conversions'], 1)} comp. ({fmt_pct(c['share_campaign_attributed_pct'])})<div class="cell-sub">{fmt_int(c['p2c_solo_conversions'])} Solo + {fmt_dec(c['assisted_conversions'], 1)} Assist.</div></td>
          <td class="num cell-highlight-blue">+{fmt_curr(c['aov_premium_revenue'])}<div class="cell-sub">AOV {fmt_curr(c['aov_valuation'])} (+{fmt_curr(c['aov_delta_brl'])}/ped.)</div></td>
          <td class="num" style="font-weight:700;color:{rc};">{fmt_curr(c['total_attributed_revenue'])}<div class="cell-sub" style="font-weight:700;color:{rc};">{rs} | {cs}</div></td>
        </tr>"""

    all_sites_rows = "".join(
        f"""<tr>
          <td><strong><code>{s['site']}</code></strong> {'<span class="pill-ctv">CTV</span>' if s['is_ctv'] else '<span class="pill-nonctv">Ação / Outros</span>'}</td>
          <td class="num">{fmt_curr(s['cost'])}</td><td class="num">{fmt_pct(s['cost_share_pct'])}</td>
          <td class="num">{fmt_int(s['impressions'])}</td><td class="num">{fmt_int(s['clicks'])}</td>
          <td class="num">{fmt_int(s['unique_reach']) if s['unique_reach'] else '—'}</td>
          <td class="num">{fmt_int(s['std_conversions'])} <span class="cell-sub">({fmt_pct((s['std_vt_conversions']/s['std_conversions']*100.0) if s['std_conversions']>0 else 0, 0)} VT)</span></td>
          <td class="num">{fmt_curr(s['std_revenue'])}</td>
          <td class="num">{f"{fmt_dec(s['std_revenue']/s['cost'])}x" if s['cost']>0 else '—'}</td>
        </tr>"""
        for s in all_sites
    )

    dv_badge = (
        f"Reconciliação Nativa CM360 + DV360 Ativa: {len(dv_rec.get('ios', []))} IOs ({fmt_curr(dv_rec['total_revenue_adv'])})"
        if dv_rec.get("enabled")
        else "Modo Somente CM360 Ativo: Custos extraídos diretamente de DV360 Cost / Media Cost no CM360"
    )
    c_main = ctv_chans[0] if ctv_chans else None
    c_sec = ctv_chans[1] if len(ctv_chans) > 1 else None
    blk_vt = blk.get("std_vt_conversions", blk["std_conversions"])
    blk_vt_pct = (blk_vt / blk["std_conversions"] * 100.0) if blk["std_conversions"] > 0 else 100.0
    tot_vt = tot.get("std_vt_conversions", sum(s.get("std_vt_conversions", 0.0) for s in all_sites))
    tot_vt_pct = (tot_vt / tot["std_conversions"] * 100.0) if tot["std_conversions"] > 0 else 0.0
    paid_pos_roas = [c for c in ctv_chans if (c.get("roas_attributed") or 0) >= 1.0]
    roas_clause = (
        f"alcançando ROAS equivalente de <strong>{fmt_dec(c_main['roas_attributed'])}x</strong> (supera 1,0x de ROAS, gerando mais receita atribuída do que o custo de mídia investido no veículo)"
        if (c_main and (c_main.get("roas_attributed") or 0) >= 1.0)
        else (f"com ROAS equivalente de <strong>{fmt_dec(c_main['roas_attributed'])}x</strong> e CPA de <code>{fmt_curr(c_main['cpa_attributed'])}</code>" if (c_main and c_main.get("roas_attributed") is not None) else "com entrega complementar de alcance")
    )
    sec_roas_note = (
        f" Já <code>{paid_pos_roas[0]['site']}</code> alcança <strong>{fmt_dec(paid_pos_roas[0]['roas_attributed'])}x</strong> de ROAS ({fmt_curr(paid_pos_roas[0]['total_attributed_revenue'])} ÷ {fmt_curr(paid_pos_roas[0]['cost'])}; supera 1,0x de ROAS, gerando mais receita atribuída do que o custo de mídia investido no veículo)."
        if (paid_pos_roas and c_main and paid_pos_roas[0]["site"] != c_main["site"])
        else ""
    )
    step2_card_text = (
        f"Mede o ganho na conversão pós-visualização de produto (<code>CVR Produto → Compra</code>: <code>{fmt_pct(f_blk['cvr_pct'])}</code> c/ CTV vs. <code>{fmt_pct(f_non['cvr_pct'])}</code> s/ CTV), definindo a Fração Atribuível entre Expostos (<code>AF_e = {fmt_pct(f_blk['capped_afe_pct'])}</code>, teto simétrico de 50%)."
        if is_cvr_mode
        else f"Sem tags de visualização de produto no anunciante, a Fração Atribuível (<code>AF_e = {fmt_pct(f_blk['capped_afe_pct'])}</code>, teto simétrico de 50%) utiliza o ganho relativo de valor como proxy conservador."
    )
    step2_card_math = (
        f"Cálculo: ({fmt_pct(f_blk['cvr_pct'])} - {fmt_pct(f_non['cvr_pct'])}) ÷ {fmt_pct(f_blk['cvr_pct'])} = {fmt_pct(f_blk['raw_afe_pct'])} → AF_e: {fmt_pct(f_blk['capped_afe_pct'])}"
        if is_cvr_mode
        else f"Cálculo: min(50,00%; Δ% AOV {fmt_pct(combo_blk['lift_valor_pct'])}) = {fmt_pct(f_blk['capped_afe_pct'])}"
    )

    slides_html = f"""
      <section class="slide-card">
        <div class="slide-meta"><span class="slide-kicker">PASSO 01 • O DESAFIO DE NEGÓCIO EM {meta['brand_name'].upper()}</span><span class="slide-scope">Escopo por Site (CM360) e Campanha</span></div>
        <h1 class="slide-title">Por Que os Relatórios de Último Toque Sub-Atribuem o Papel Real da CTV?</h1>
        <p class="slide-lead">Na campanha <strong>{meta['brand_name']}</strong> (<code>{meta['campaign_name']}</code> • ID <code>{meta['campaign_id']}</code>), os canais de CTV receberam <strong>{fmt_curr(blk['cost'])} ({fmt_pct(blk['cost_share_pct'])} do investimento)</strong> e entregaram <strong>{fmt_int(blk['impressions'])} impressões ({fmt_pct(blk['impressions_share_pct'])})</strong>:</p>
        <div class="grid-3">
          <div class="card top-blue"><div><span class="badge blue">1. Comportamento Cross-Device</span><div class="kpi-huge" style="color:var(--g-blue-dark);">100% View-Through</div><div class="kpi-sub">Co-Viewing: {fmt_dec(tot['coview_factor_campaign'])}x pessoas/tela</div><p class="card-text">Na Smart TV não há clique direto. O consumidor assiste na tela da sala e usa o celular ou computador depois para buscar a marca e fechar o pedido.</p></div><div class="math-foot">Cálculo: Co-Viewing: {fmt_int(tot['reach_coviewed'])} ÷ {fmt_int(tot['reach_devices'])} = {fmt_dec(tot['coview_factor_campaign'])}x</div></div>
          <div class="card top-red bg-red"><div><span class="badge red">2. Viés de Último Toque (Standard)</span><div class="kpi-huge" style="color:var(--g-red);">{fmt_pct(blk['std_share_pct'])}</div><div class="kpi-sub" style="color:var(--g-red);">{fmt_int(blk['std_conversions'])} compras Std ({fmt_pct(blk_vt_pct, 0)} View-Through | {fmt_curr(blk['std_revenue'])})</div><p class="card-text">Canais de clique no celular capturam a última interação antes do checkout, distorcendo a leitura isolada do relatório Standard sobre o papel real do vídeo na sala.</p></div><div class="math-foot">Cálculo: Standard CTV: {fmt_int(blk['std_conversions'])} ÷ {fmt_int(tot['std_conversions'])} = {fmt_pct(blk['std_share_pct'])} ({fmt_int(blk_vt)} VT / {fmt_int(blk['std_conversions'] - blk_vt)} CT)</div></div>
          <div class="card top-yellow bg-yellow"><div><span class="badge yellow">3. Perda de Sinal no CSV do P2C</span><div class="kpi-huge" style="color:var(--g-yellow-dark);">{fmt_pct(blk['overlap_pct_campaign_sum'])}</div><div class="kpi-sub" style="color:var(--g-yellow-dark);">de interseção real no Reach Overlap (1+)</div><p class="card-text">Enquanto o arquivo bruto do P2C exige vínculo determinístico por toque, o <code>Reach Overlap</code> do CM360 dimensiona a audiência exata que viu CTV e outros canais da campanha.</p></div><div class="math-foot">Cálculo: Overlap 1+ Bloco CTV: {fmt_int(blk['duplicate_reach_1plus_sum'])} ÷ {fmt_int(tot['reach_devices'])} = {fmt_pct(blk['overlap_pct_campaign_sum'])}</div></div>
        </div>
      </section>

      <section class="slide-card slide-hidden">
        <div class="slide-meta"><span class="slide-kicker">PASSO 02 • METODOLOGIA DE MENSURAÇÃO INTEGRADA</span><span class="slide-scope">Triangulação Nativa CM360: Standard + Unique Reach Overlap (1+) + Path to Conversion (14d)</span></div>
        <h2 class="slide-title">Decomposição Auditável em 3 Passos: Vendas Solo + Volume Assistido + Prêmio de AOV (R$)</h2>
        <div class="formula-box"><div class="formula-label">Equações Unificadas da Metodologia</div><div class="formula-code">Compras Atribuídas = Solo P2C + (Interseção 1+ × AF_e CVR Produto→Compra) &nbsp;|&nbsp; Receita (R$) = Solo + Base Assistida + Prêmio AOV (R$)</div></div>
        <div class="grid-3">
          <div class="card top-blue"><div><span class="badge blue">Passo 1 • Vendas Solo (P2C)</span><p class="card-text">Contabilizamos integralmente apenas os pedidos observados no <code>Path to Conversion</code> em que a CTV foi o único canal da jornada, sem extrapolar o alcance exclusivo.</p></div><div class="math-foot">Cálculo: Observado P2C: {fmt_int(blk['p2c_solo_conversions'])} vendas Solo ({fmt_curr(blk['p2c_solo_revenue'])})</div></div>
          <div class="card top-green"><div><span class="badge green">Passo 2 • Volume (AF_e Funil)</span><p class="card-text">{step2_card_text}</p></div><div class="math-foot">{step2_card_math}</div></div>
          <div class="card top-yellow"><div><span class="badge yellow">Passo 3 • Valor em R$ (Δ AOV)</span><p class="card-text">Expansão de Ticket Médio entra exclusivamente em Reais por pedido assistido (<code>+{fmt_curr(max(0.0, combo_blk['aov'] - ctrl_camp['aov']))}/ped.</code>), gerando <code>+{fmt_curr(blk['aov_premium_revenue'])}</code> em prêmio de cesta.</p></div><div class="math-foot">Cálculo: {fmt_curr(combo_blk['aov'])} - {fmt_curr(ctrl_camp['aov'])} = +{fmt_curr(max(0.0, combo_blk['aov'] - ctrl_camp['aov']))}/ped.</div></div>
        </div>
      </section>

      <section class="slide-card slide-hidden">
        <div class="slide-meta"><span class="slide-kicker">PASSO 03 • GUIA VISUAL ILUSTRADO</span><span class="slide-scope">3 Infográficos populados dinamicamente com os dados de {meta['brand_name']}</span></div>
        <h2 class="slide-title">Visualizando a Jornada Cross-Device, as 3 Coortes de Venn e os Ganhos Empíricos</h2>
        <div class="vis-tabs no-print">
          <button onclick="showVisTab(0)" class="vis-tab active">1. Jornada Cross-Device</button>
          <button onclick="showVisTab(1)" class="vis-tab">2. Diagrama de Venn (1+)</button>
          <button onclick="showVisTab(2)" class="vis-tab">3. Funil (CVR), AOV &amp; Toques</button>
          <button onclick="showVisTab(3)" class="vis-tab">Exibir Todos os 3</button>
        </div>
        <div class="vis-panel"><img src="{b64_1}" alt="Ilustração 1" class="vis-img"></div>
        <div class="vis-panel slide-hidden"><img src="{b64_2}" alt="Ilustração 2" class="vis-img"></div>
        <div class="vis-panel slide-hidden"><img src="{b64_3}" alt="Ilustração 3" class="vis-img"></div>
      </section>

      <section class="slide-card slide-hidden">
        <div class="slide-meta"><span class="slide-kicker">PASSO 04 • ETAPA 1 DO CÁLCULO (ALCANCE E INTERSEÇÃO 1+)</span><span class="slide-scope">CM360 Unique Reach &amp; Reach Overlap</span></div>
        <h2 class="slide-title">Alcance Único, Co-Viewing e Interseção Cross-Device (1+) por Canal CTV</h2>
        <div class="table-box">
          <div class="table-head-bar"><span class="table-head-title">Abertura de Alcance e Overlap 1+ — {meta['brand_name']}</span><span>Universo: {fmt_int(tot['reach_devices'])} disp. | {fmt_int(tot['p2c_total_conversions'])} compras P2C</span></div>
          <div class="table-scroll"><table><thead><tr><th>Canal CTV</th><th class="num">Impressões</th><th class="num">Custo</th><th class="num">Unique Reach</th><th class="num">Co-Viewed</th><th class="num">Exclusivo</th><th class="num">Interseção 1+</th><th class="num">% Overlap Camp.</th><th class="num cell-highlight-blue">Compras Interseção</th></tr></thead>
          <tbody>{reach_rows}<tr class="row-total"><td>BLOCO CTV ({len(ctv_chans)} Canais)</td><td class="num">{fmt_int(blk['impressions'])}</td><td class="num">{fmt_curr(blk['cost'])}</td><td class="num">—</td><td class="num">—</td><td class="num">{fmt_int(blk['exclusive_reach_1plus_sum'])}</td><td class="num">{fmt_int(blk['duplicate_reach_1plus_sum'])}</td><td class="num">{fmt_pct(blk['overlap_pct_campaign_sum'])}</td><td class="num">{fmt_dec(blk['intersecao_compras_1plus'], 1)} comp.</td></tr></tbody></table></div>
          <div class="table-foot-math">Como calculamos: % Overlap = Duplicate Impression Reach (1+) ÷ {fmt_int(tot['reach_devices'])} disp. | Compras Interseção = {fmt_int(tot['p2c_total_conversions'])} × (% Overlap).</div>
        </div>
      </section>

      <section class="slide-card slide-hidden">
        <div class="slide-meta"><span class="slide-kicker">PASSO 05 • ETAPA 2 DO CÁLCULO (CVR &amp; AOV) + DIAGNÓSTICO DE TOQUES NO P2C</span><span class="slide-scope">Comparativo Simétrico Expostos CTV vs. Base Sem CTV</span></div>
        <h2 class="slide-title">Funil Produto → Compra (AF_e), Ticket Médio (R$) e Aceleração de Toques na Jornada</h2>
        <div class="table-box">
          <div class="table-head-bar"><span class="table-head-title">1. Parâmetros da Atribuição: Funil Produto → Compra (Standard) &amp; Ticket Médio P2C (14d)</span><span>Teto Simétrico AF_e: 50,00% | Base P2C: {fmt_int(tot['p2c_total_conversions'])} Compras ({fmt_curr(tot['p2c_total_revenue'])})</span></div>
          <div class="table-scroll"><table><thead><tr><th>Coorte / Canal</th><th class="num">Views de Produto</th><th class="num">Compras (Funil Std)</th><th class="num">CVR Produto → Compra</th><th class="num cell-highlight-green">Fração AF_e (Teto 50%)</th><th class="num">Ticket Médio P2C (AOV)</th><th class="num cell-highlight-blue">Prêmio AOV (R$)</th></tr></thead><tbody>{lifts_rows}</tbody></table></div>
          <div class="table-foot-math">Como calculamos (entra na fórmula de atribuição): CVR Produto → Compra = Compras Oficiais ÷ Views de Produto Oficiais | AF_e = min(50%, max(0%, (CVR_CTV - CVR_Base) ÷ CVR_CTV)) | Canais com amostra &lt; 30 views ou &lt; 5 compras herdam o AF_e consolidado do bloco | Prêmio AOV = max(0, AOV Com CTV - AOV Controle).</div>
        </div>
        <div class="table-box">
          <div class="table-head-bar"><span class="table-head-title">2. Diagnóstico Comportamental no P2C (14d): Aceleração de Toques Não-CTV até a Compra</span><span style="color:var(--g-yellow-dark);font-weight:700;">Indicador Diagnóstico (não usado como proxy de compras)</span></div>
          <div class="table-scroll"><table><thead><tr><th>Coorte de Jornada (P2C 14d)</th><th class="num">Vendas Solo P2C</th><th class="num">Compras Combo</th><th class="num">Média Toques Não-CTV</th><th class="num">Δ vs. Controle</th><th class="num">Variação de Toques (%)</th></tr></thead><tbody>{touch_rows}</tbody></table></div>
          <div class="table-foot-math">Como calculamos (evidência comportamental complementar): Δ Toques = Média Toques Não-CTV Com CTV - Média Toques Controle Sem CTV ({fmt_dec(blk_t)} - {fmt_dec(base_t)} = {fmt_dec(blk_t - base_t, sign=True)} toques; {fmt_pct(blk_t_pct, sign=True)}). Nota metodológica: esta análise demonstra quantos impactos de mídia de performance são poupados quando o consumidor é exposto à CTV, sem entrar no cálculo de Compras Assistidas.</div>
        </div>
      </section>

      <section class="slide-card slide-hidden">
        <div class="slide-meta"><span class="slide-kicker">PASSO 06 • RESULTADO FINAL UNIFICADO DOS CANAIS DE CTV</span><span class="slide-scope">{dv_badge}</span></div>
        <h2 class="slide-title">{meta['brand_name']}: Bloco CTV Responde por {fmt_dec(blk['total_attributed_conversions'], 1)} Compras ({fmt_pct(blk['share_campaign_attributed_pct'])}) e {fmt_curr(blk['total_attributed_revenue'])}</h2>
        <div class="table-box">
          <div class="table-head-bar"><span class="table-head-title">Resultado Final por Canal CTV e Consolidado</span><span>ROAS Bloco: {fmt_dec(blk['roas_attributed'])}x | CPA: {fmt_curr(blk['cpa_attributed'])}</span></div>
          <div class="table-scroll"><table><thead><tr><th>Canal CTV</th><th class="num">Custo</th><th class="num">Standard</th><th class="num">Vendas Solo</th><th class="num">Interseção 1+</th><th class="num cell-highlight-green">Compras Atribuídas</th><th class="num cell-highlight-blue">Prêmio AOV (R$)</th><th class="num">Receita, ROAS &amp; CPA</th></tr></thead>
          <tbody>{res_rows}<tr class="row-total"><td>TOTAL BLOCO CTV ({len(ctv_chans)} Veículos)</td><td class="num">{fmt_curr(blk['cost'])}<div class="cell-sub">{fmt_pct(blk['cost_share_pct'])} da camp.</div></td><td class="num">{fmt_int(blk['std_conversions'])} comp.<div class="cell-sub">{fmt_curr(blk['std_revenue'])}</div></td><td class="num">{fmt_int(blk['p2c_solo_conversions'])} comp.<div class="cell-sub">{fmt_curr(blk['p2c_solo_revenue'])}</div></td><td class="num">{fmt_dec(blk['intersecao_compras_1plus'], 1)} comp.</td><td class="num">{fmt_dec(blk['total_attributed_conversions'], 1)} comp. ({fmt_pct(blk['share_campaign_attributed_pct'])})</td><td class="num">+{fmt_curr(blk['aov_premium_revenue'])}</td><td class="num">{fmt_curr(blk['total_attributed_revenue'])}<div class="cell-sub">ROAS: {fmt_dec(blk['roas_attributed'])}x | CPA: {fmt_curr(blk['cpa_attributed'])}</div></td></tr></tbody></table></div>
          <div class="table-foot-math">Como calculamos: Compras Atribuídas = Solo P2C + (Interseção 1+ × AF_e CVR Produto→Compra, teto 50%) | Receita Atribuída = Receita Solo + (Compras Assistidas × AOV Base Controle) + Prêmio AOV (R$) | ROAS = Receita ÷ Custo | CPA = Custo ÷ Compras. Nota financeira: superar 1,0x de ROAS significa gerar mais receita atribuída do que o custo de mídia investido no veículo (não equivale a lucro líquido contábil).</div>
        </div>
        {f'<div class="takeaway-bar"><div class="takeaway-text"><strong>Destaque Principal (<code>{c_main["site"]}</code>):</strong> CPM de {fmt_curr(c_main["cpm"])} (eCPM Co-Viewed {fmt_curr(c_main["ecpm_coview"])}), {fmt_dec(c_main["total_attributed_conversions"], 1)} compras atribuídas e {fmt_curr(c_main["total_attributed_revenue"])}, {roas_clause}.{sec_roas_note}</div></div>' if c_main else ''}
      </section>

      <section class="slide-card slide-hidden">
        <div class="slide-meta"><span class="slide-kicker">PASSO 07 • VISÃO 360° DA CAMPANHA (100% RECONCILIADO)</span><span class="slide-scope">Trava 2: Soma == {fmt_curr(tot['std_cost'])} (100,00%)</span></div>
        <h2 class="slide-title">Reconciliação Completa de Todos os Sites da Campanha (CTV + Ação)</h2>
        <div class="table-box">
          <div class="table-scroll"><table><thead><tr><th>Site (CM360)</th><th class="num">Custo</th><th class="num">% Budget</th><th class="num">Impressões</th><th class="num">Cliques</th><th class="num">Unique Reach</th><th class="num">Compras Std</th><th class="num">Receita Std</th><th class="num">ROAS Std</th></tr></thead>
          <tbody>{all_sites_rows}<tr class="row-total"><td>TOTAL CAMPANHA ({len(all_sites)} Sites)</td><td class="num">{fmt_curr(tot['std_cost'])}</td><td class="num">100,00%</td><td class="num">{fmt_int(tot['std_impressions'])}</td><td class="num">{fmt_int(tot['std_clicks'])}</td><td class="num">{fmt_int(tot['reach_devices'])}</td><td class="num">{fmt_int(tot['std_conversions'])} <span class="cell-sub">({fmt_pct(tot_vt_pct, 0)} VT)</span></td><td class="num">{fmt_curr(tot['std_revenue'])}</td><td class="num">{fmt_dec(tot['std_roas'])}x</td></tr></tbody></table></div>
          <div class="table-foot-math">Como calculamos: % Budget = Custo Site ÷ {fmt_curr(tot['std_cost'])} | ROAS Std = Receita Std ÷ Custo ({fmt_curr(tot['std_revenue'])} ÷ {fmt_curr(tot['std_cost'])} = {fmt_dec(tot['std_roas'])}x). Pedidos únicos participantes no P2C: {fmt_int(tot['p2c_total_conversions'])} ({fmt_curr(tot['p2c_total_revenue'])}; {fmt_int(tot['p2c_shared_other_agency_journeys'])} compartilhados entre campanhas da marca deduplicados).</div>
        </div>
      </section>

      <section class="slide-card slide-hidden">
        <div class="slide-meta"><span class="slide-kicker">PASSO 08 • GOVERNANÇA TÉCNICA E PRÓXIMOS PASSOS</span><span class="slide-scope">Recomendações Executivas para {meta['agency_name']} &amp; {meta['brand_name']}</span></div>
        <h2 class="slide-title">Confiabilidade Metodológica e Plano de Ação</h2>
        <div class="grid-3">
          <div class="card top-green"><div><span class="badge green">1. Ponte Cross-Device &amp; Aceleração</span><ul class="clean-list"><li>Ambientes logados conectam Smart TV e smartphone no <code>Reach Overlap</code> sem depender de clique na TV.</li><li>Volume assistido (via <code>CVR Produto → Compra</code>) e prêmio de AOV são reportados em suas unidades exatas, enquanto a queda de toques Não-CTV no P2C (<code>{fmt_dec(blk_t)}</code> vs. <code>{fmt_dec(base_t)}</code>; <code>{fmt_pct(blk_t_pct, sign=True)}</code>) entra como evidência comportamental de aceleração de jornada.</li></ul></div></div>
          <div class="card top-yellow"><div><span class="badge yellow">2. Cautelas em Inventários Externos</span><ul class="clean-list"><li>Parceiros externos sem login unificado concentram maior parcela de alcance isolado ({fmt_pct(c_sec['exclusive_pct_site'] if c_sec else 0)} em <code>{c_sec['site'] if c_sec else 'Outros'}</code>).</li><li>Evitar misturar Mobile e Smart TV no mesmo Placement para preservar rastreio determinístico no P2C.</li></ul></div></div>
          <div class="card top-blue"><div><span class="badge blue">3. Próximos Passos</span><ul class="clean-list"><li>Conectar audiências de CTV ao retargeting de performance para elevar a conectividade Cross-Device.</li><li>Complementar com estudos incrementais (Conversion Lift / Geo-Lift) em voos de alta escala.</li></ul></div></div>
        </div>
      </section>
    """
    titles = [
        "O Desafio de Medir CTV", "Metodologia Integrada", "Guia Visual Ilustrado", "Passo 1: Alcance & Interseção",
        "Passo 2: CVR, AOV & Toques", "Resultado Final CTV", "Visão 360° da Campanha", "Governança & Plano de Ação",
    ]
    return {
        "id": "site",
        "tab_label": "1. Visão por Naming do Site ('CTV')",
        "badge_label": "Google Marketing Platform • Naming Site",
        "badge_cls": "",
        "titles": titles,
        "slides_html": slides_html,
    }


def _render_site_html(cfg: dict, res: dict, out_dir: Path) -> str:
    deck = _build_site_deck(res, out_dir)
    out_html = out_dir / f"Relatorio_Executivo_CTV_{cfg['case_slug']}.html"
    out_html.write_text(_render_shell(f"Relatório Executivo CTV — {res['meta']['brand_name']}", res["meta"], [deck]), encoding="utf-8")
    return str(out_html)


def _generate_device_infographics(res: dict, out_dir: Path) -> tuple[str, str, str]:
    _setup_mpl()
    meta, tot, blk, ie = res["meta"], res["campaign_totals"], res["ctv_block_consolidated"], res["exact_inclusion_exclusion_block"]
    ctrl_all = res["p2c_control_vs_ctv"]["control_multi_no_ctv_all"]
    ctrl_camp = res["p2c_control_vs_ctv"]["control_multi_no_ctv_camp"]
    ctv_chans = [c for c in res["ctv_channels"] if not c.get("is_residual_bucket")]
    comp = res.get("comparison_vs_site_method", {})
    sb = comp.get("site_block", {})

    img1 = out_dir / "device_ilustracao_1_jornada.png"
    fig, ax = plt.subplots(figsize=(15, 6.3), dpi=220)
    ax.set_xlim(0, 15); ax.set_ylim(0, 6.3); ax.axis("off"); fig.patch.set_facecolor("#FFFFFF")
    ax.text(0.4, 5.85, f"ILUSTRAÇÃO 1 • IDENTIFICAÇÃO POR DEVICE TYPE (SMART TV + SET-TOP BOX) — {meta['brand_name'].upper()}", fontsize=12.4, fontweight="bold", color="#1A73E8")
    ax.text(0.4, 5.42, f"Classificando CTV pelo hardware físico (Connected TV [30004] + Set top box [30006]) em todos os {len(res['all_sites_device_split'])} Sites da campanha:", fontsize=9.9, color="#5F6368")
    ax.add_patch(FancyBboxPatch((0.4, 1.80), 4.25, 3.25, boxstyle="round,pad=0.12,rounding_size=0.2", ec="#1A73E8", fc="#E8F0FE", lw=2))
    ax.text(2.52, 4.65, "1. TELA GRANDE (SMART TV + STB)", fontsize=10.2, fontweight="bold", color="#1A73E8", ha="center")
    ax.text(2.52, 4.20, f"Verba Física TV: {fmt_curr(blk['cost'])} ({fmt_pct(blk['cost_share_pct'])})", fontsize=8.7, fontweight="bold", ha="center")
    ax.text(2.52, 3.35, "\n".join(f"• {c['site']}: {fmt_curr(c['cost'])} ({fmt_pct(c['overlap_pct_campaign'])} ovl)" for c in ctv_chans[:4]), fontsize=7.9, color="#3C4043", ha="center", va="center", linespacing=1.45)
    ax.text(2.52, 2.25, f"Smart TV (30004): {fmt_curr(blk['smart_tv_cost'])}\nSet-top Box (30006): {fmt_curr(blk['stb_cost'])}", fontsize=8.2, fontweight="bold", color="#1A73E8", ha="center", va="center", bbox=dict(boxstyle="round,pad=0.30", facecolor="#FFF", edgecolor="#D2E3FC"))

    ax.annotate("", xy=(5.55, 3.42), xytext=(4.80, 3.42), arrowprops=dict(arrowstyle="->,head_width=0.35,head_length=0.35", color="#1A73E8", lw=3))
    ax.text(5.17, 3.92, "Ponte Pura\nTV → Mobile", fontsize=8.2, fontweight="bold", color="#1A73E8", ha="center")

    ax.add_patch(FancyBboxPatch((5.65, 1.80), 4.0, 3.25, boxstyle="round,pad=0.12,rounding_size=0.2", ec="#F9AB00", fc="#FEF7E0", lw=2))
    ax.text(7.65, 4.65, "2. AÇÃO EM TELAS PESSOAIS", fontsize=10.2, fontweight="bold", color="#B06000", ha="center")
    ax.text(7.65, 3.35, f"• Reach Non-CTV: {fmt_int(ie['non_ctv_devices_reach_dedup'])} disp.\n• Interseção Pura (TV ∩ Mobile/PC):\n  {fmt_int(ie['exact_cross_device_overlap_1plus'])} disp. ({fmt_pct(ie['exact_overlap_pct_campaign'])})\n• Expurgado TV ∩ TV: {fmt_int(ie['tv_tv_and_multisite_purged_devices'])} disp.", fontsize=8.0, color="#3C4043", ha="center", va="center", linespacing=1.42)
    ax.text(7.65, 2.22, f"Conectividade Cross-Device Real:\n{fmt_pct(ie['exact_connectivity_pct_of_ctv'])} da audiência de Smart TV", fontsize=8.2, fontweight="bold", color="#B06000", ha="center", va="center", bbox=dict(boxstyle="round,pad=0.30", facecolor="#FFF", edgecolor="#FDE293"))

    ax.annotate("", xy=(10.6, 3.42), xytext=(9.8, 3.42), arrowprops=dict(arrowstyle="->,head_width=0.35,head_length=0.35", color="#188038", lw=3))
    ax.text(10.2, 3.92, "Checkout\nWeb/App", fontsize=8.2, fontweight="bold", color="#188038", ha="center")

    ax.add_patch(FancyBboxPatch((10.7, 1.80), 3.9, 3.25, boxstyle="round,pad=0.12,rounding_size=0.2", ec="#188038", fc="#E6F4EA", lw=2))
    ax.text(12.65, 4.65, "3. DISPOSITIVO DA COMPRA (P2C)", fontsize=10.2, fontweight="bold", color="#188038", ha="center")
    ax.text(12.65, 4.20, f"Onde os {fmt_int(tot['p2c_total_conversions'])} pedidos fecharam:", fontsize=8.7, fontweight="bold", ha="center")
    chk_lines = "\n".join(f"• {d['platform_type'][:26]}: {fmt_int(d['conversions'])} ({fmt_pct(d['share_pct'])})" for d in res["checkout_device_breakdown"][:4])
    ax.text(12.65, 3.30, chk_lines, fontsize=7.8, color="#3C4043", ha="center", va="center", linespacing=1.42)
    ax.text(12.65, 2.22, f"Total P2C: {fmt_int(tot['p2c_total_conversions'])} compras\nReceita: {fmt_curr(tot['p2c_total_revenue'])}", fontsize=8.2, fontweight="bold", color="#188038", ha="center", va="center", bbox=dict(boxstyle="round,pad=0.30", facecolor="#FFF", edgecolor="#CEEAD6"))

    ax.add_patch(FancyBboxPatch((0.4, 0.25), 7.0, 1.18, boxstyle="round,pad=0.1,rounding_size=0.15", ec="#D2E3FC", fc="#E8F0FE", lw=1.5))
    ax.text(3.9, 1.05, "SENSIBILIDADE SOMA BRUTA SITES (C/ OVERLAP TV∩TV):", fontsize=8.5, fontweight="bold", color="#1A73E8", ha="center")
    ax.text(3.9, 0.58, f"{fmt_curr(blk['cost'])} | {fmt_dec(blk['raw_total_attributed_conversions'], 1)} comp. | {fmt_curr(blk['raw_total_attributed_revenue'])} (ROAS {fmt_dec(blk['raw_roas_attributed'])}x)", fontsize=8.1, color="#174EA6", ha="center")
    ax.add_patch(FancyBboxPatch((7.6, 0.25), 7.0, 1.18, boxstyle="round,pad=0.1,rounding_size=0.15", ec="#CEEAD6", fc="#E6F4EA", lw=1.5))
    ax.text(11.1, 1.05, "DEVICE PURO CROSS-DEVICE (SEM TV∩TV — EXATO):", fontsize=8.5, fontweight="bold", color="#188038", ha="center")
    ax.text(11.1, 0.58, f"{fmt_curr(blk['cost'])} | {fmt_dec(blk['total_attributed_conversions'], 1)} comp. | {fmt_curr(blk['total_attributed_revenue'])} (ROAS {fmt_dec(blk['roas_attributed'])}x)", fontsize=8.1, color="#0D652D", ha="center")
    plt.tight_layout(pad=0.3); plt.savefig(img1, dpi=220); plt.close(fig)

    img2 = out_dir / "device_ilustracao_2_venn.png"
    fig, ax = plt.subplots(figsize=(15, 6.4), dpi=220)
    ax.set_xlim(0, 15); ax.set_ylim(0, 6.4); ax.axis("off"); fig.patch.set_facecolor("#FFFFFF")
    ax.text(0.4, 5.95, f"ILUSTRAÇÃO 2 • LEI DA INCLUSÃO-EXCLUSÃO EXATA POR DEVICE TYPE — {meta['brand_name'].upper()}", fontsize=12.6, fontweight="bold", color="#1A73E8")
    ax.text(0.4, 5.52, f"|TV/STB ∩ Outros| = Reach(CTV: {fmt_int(ie['ctv_devices_reach_dedup'])}) + Reach(Non-CTV: {fmt_int(ie['non_ctv_devices_reach_dedup'])}) - Reach(Total: {fmt_int(ie['campaign_total_reach_dedup'])})", fontsize=9.5, color="#5F6368")
    ax.add_patch(Circle((6.0, 3.25), 1.85, facecolor="#4285F4", alpha=0.14, edgecolor="#1A73E8", lw=2.5))
    ax.add_patch(Circle((8.55, 3.25), 2.05, facecolor="#34A853", alpha=0.14, edgecolor="#188038", lw=2.5))
    iso_pct = 100.0 - ie["exact_connectivity_pct_of_ctv"]
    ax.text(4.92, 4.05, "SÓ SMART TV / STB", fontsize=9.0, fontweight="bold", color="#1A73E8", ha="center")
    ax.text(4.92, 3.05, f"{fmt_int(ie['exact_exclusive_ctv_1plus'])} disp.\n({fmt_pct(iso_pct)} do público TV)\n\nSolo P2C: {fmt_int(blk['p2c_solo_conversions'])} comp.\n({fmt_curr(blk['p2c_solo_revenue'])})", fontsize=8.0, ha="center", va="center")
    ax.text(7.22, 4.25, "INTERSEÇÃO PURA\n(TV/STB ∩ Mobile/PC)", fontsize=9.0, fontweight="bold", color="#188038", ha="center", va="center")
    ax.text(7.22, 3.25, f"{fmt_int(ie['exact_cross_device_overlap_1plus'])} disp.\n({fmt_pct(ie['exact_overlap_pct_campaign'])} da camp.)\n{fmt_pct(ie['exact_connectivity_pct_of_ctv'])} conect. TV", fontsize=8.0, fontweight="bold", ha="center", va="center")
    ax.text(7.22, 2.05, f"{fmt_dec(blk['intersecao_compras_1plus'], 1)} comp. interseção\n→ +{fmt_dec(blk['assisted_conversions'], 1)} assistidas", fontsize=7.9, fontweight="bold", color="#188038", ha="center", va="center", bbox=dict(boxstyle="round,pad=0.25", facecolor="#E6F4EA", edgecolor="#188038"))
    ax.text(9.68, 4.05, "SÓ MOBILE / DESKTOP", fontsize=9.0, fontweight="bold", color="#3C4043", ha="center")
    ax.text(9.68, 3.05, f"{fmt_int(max(0.0, ie['non_ctv_devices_reach_dedup'] - ie['exact_cross_device_overlap_1plus']))} disp.\nControle Puro:\n{fmt_int(ctrl_all['conversions'])} pedidos multi\nAOV {fmt_curr(ctrl_camp['aov'])}", fontsize=8.0, ha="center", va="center")
    ax.add_patch(FancyBboxPatch((0.4, 0.25), 14.2, 0.95, boxstyle="round,pad=0.1,rounding_size=0.15", ec="#1A73E8", fc="#E8F0FE", lw=1.8))
    ax.text(7.5, 0.72, f"TRAVA DE RECONCILIAÇÃO:  Soma Alocada dos Canais TV ({fmt_int(blk['duplicate_reach_1plus_sum'])} disp. | {fmt_dec(blk['intersecao_compras_1plus'], 1)} comp.) == Inclusão-Exclusão Exata |CTV ∩ Non-CTV|", fontsize=8.8, fontweight="bold", ha="center", va="center")
    plt.tight_layout(pad=0.3); plt.savefig(img2, dpi=220); plt.close(fig)

    img3 = out_dir / "device_ilustracao_3_comparativo.png"
    fig = plt.figure(figsize=(15, 6.3), dpi=220); fig.patch.set_facecolor("#FFFFFF")
    fig.text(0.03, 0.94, f"ILUSTRAÇÃO 3 • INVESTIMENTO E RECEITA ATRIBUÍDA POR CANAL DE SMART TV + STB — {meta['brand_name'].upper()}", fontsize=12.2, fontweight="bold", color="#1A73E8")
    ax1, ax2 = fig.add_axes([0.06, 0.16, 0.41, 0.66]), fig.add_axes([0.55, 0.16, 0.41, 0.66])
    psc = [r for r in comp.get("per_site_comparison", []) if (r["site_method_cost"] > 1000 or r["device_method_cost"] > 1000)]
    if psc and sb:
        labels = [r["site"].replace("DV360_", "").replace("DV360-", "") for r in psc] + ["TOTAL CTV"]
        x, w, w3 = list(range(len(labels))), 0.34, 0.25
        sc = [r["site_method_cost"] / 1000.0 for r in psc] + [sb["cost"] / 1000.0]
        dc = [r["device_method_cost"] / 1000.0 for r in psc] + [blk["cost"] / 1000.0]
        ax1.bar([i - w / 2 for i in x], sc, width=w, color="#9AA0A6", label="Por Site ('CTV')")
        ax1.bar([i + w / 2 for i in x], dc, width=w, color="#4285F4", label="Por Device (TV+STB)")
        sr = [r["site_method_rev"] / 1000.0 for r in psc] + [sb["total_attributed_revenue"] / 1000.0]
        rr = [r["device_raw_rev"] / 1000.0 for r in psc] + [blk["raw_total_attributed_revenue"] / 1000.0]
        pr = [r["device_method_rev"] / 1000.0 for r in psc] + [blk["total_attributed_revenue"] / 1000.0]
        ax2.bar([i - w3 for i in x], sr, width=w3, color="#9AA0A6", label="Por Site ('CTV')")
        ax2.bar(x, rr, width=w3, color="#8AB4F8", label="Device Bruto (c/ TV∩TV)")
        ax2.bar([i + w3 for i in x], pr, width=w3, color="#34A853", label="Device Puro (s/ TV∩TV)")
    else:
        labels = [c["site"].replace("DV360_", "").replace("DV360-", "") for c in ctv_chans[:5]]
        x = list(range(len(labels)))
        ax1.bar(x, [c["cost"] / 1000.0 for c in ctv_chans[:5]], width=0.45, color="#4285F4", label="Custo TV+STB (R$ Mil)")
        ax2.bar([i - 0.18 for i in x], [c["raw_total_attributed_revenue"] / 1000.0 for c in ctv_chans[:5]], width=0.35, color="#8AB4F8", label="Receita Bruta")
        ax2.bar([i + 0.18 for i in x], [c["total_attributed_revenue"] / 1000.0 for c in ctv_chans[:5]], width=0.35, color="#34A853", label="Receita Pura")
    for ax, ttl in [(ax1, "1. Investimento em CTV (R$ Mil)"), (ax2, "2. Receita Atribuída em CTV (R$ Mil)")]:
        ax.set_title(ttl, fontsize=10.5, fontweight="bold", pad=10); ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=8.3, fontweight="bold", rotation=8)
        ax.grid(axis="y", linestyle="--", alpha=0.4); ax.legend(loc="upper left", fontsize=8)
    plt.savefig(img3, dpi=220); plt.close(fig)
    return img_to_b64(img1), img_to_b64(img2), img_to_b64(img3)


def _build_device_deck(res: dict, out_dir: Path) -> dict:
    b64_1, b64_2, b64_3 = _generate_device_infographics(res, out_dir)
    meta, tot, blk, ie = res["meta"], res["campaign_totals"], res["ctv_block_consolidated"], res["exact_inclusion_exclusion_block"]
    f_eff = res["funnel_cvr_efficiency"]
    f_non, f_blk = f_eff["non_ctv_base"], f_eff["ctv_block"]
    is_cvr_mode = f_eff["metric_source"] == "cvr_produto_compra"
    has_ev_plat = bool(meta.get("has_event_platform_type"))
    ctrl_all = res["p2c_control_vs_ctv"]["control_multi_no_ctv_all"]
    ctrl_camp = res["p2c_control_vs_ctv"]["control_multi_no_ctv_camp"]
    combo_blk = res["p2c_control_vs_ctv"]["ctv_combo_block_all"]
    ctv_chans, plat_list, sites_split = res["ctv_channels"], res["platform_breakdown"], res["all_sites_device_split"]
    comp = res.get("comparison_vs_site_method", {})
    sb = comp.get("site_block", {})

    plat_rows = "".join(
        f"""<tr>
          <td><strong><code>{p['platform_type']}</code></strong> {'<span class="pill-ctv">CTV Device</span>' if p['is_ctv_device'] else '<span class="pill-nonctv">Não-CTV</span>'}</td>
          <td class="num">{fmt_curr(p['cost'])}</td><td class="num">{fmt_pct(p['cost_share_pct'])}</td><td class="num">{fmt_int(p['impressions'])}</td>
          <td class="num">{fmt_int(p['unique_reach'])}</td><td class="num">{fmt_int(p['coviewed_reach'])} <span class="cell-sub">({fmt_dec(p['coview_factor'])}x)</span></td>
          <td class="num cell-highlight-blue">{fmt_dec(p['std_conversions'], 1)} <span class="cell-sub">VT: {fmt_dec(p['std_vt_conversions'], 1)}</span></td>
          <td class="num">{fmt_curr(p['std_revenue'])}</td><td class="num">{fmt_int(p['checkout_std_conversions'])}</td>
        </tr>"""
        for p in plat_list
    )
    split_rows = "".join(
        f"""<tr>
          <td><strong><code>{s['site']}</code></strong> {'<span class="pill-ctv">Nome CTV</span>' if s['had_ctv_in_name'] else '<span class="pill-nonctv">Nome Não-CTV</span>'}</td>
          <td class="num">{fmt_curr(s['total_cost'])}</td>
          <td class="num"{' class="cell-highlight-blue"' if (not s['had_ctv_in_name'] and s['ctv_device_cost']>1) else ''}>{fmt_curr(s['ctv_device_cost'])}<span class="cell-sub">TV: {fmt_curr(s['smart_tv_cost'])} | STB: {fmt_curr(s['stb_cost'])}</span></td>
          <td class="num">{fmt_curr(s['non_ctv_device_cost'])}</td><td class="num"><strong>{fmt_pct(s['ctv_cost_pct_of_site'])}</strong></td>
          <td class="num">{fmt_int(s['ctv_device_impressions'])}<span class="cell-sub">{fmt_pct(s['ctv_imps_pct_of_site'])} imps</span></td>
          <td class="num">{fmt_dec(s['ctv_device_std_conversions'], 1)} / {fmt_int(s['total_std_conversions'])}</td>
        </tr>"""
        for s in sites_split
    )
    reach_rows = "".join(
        f"""<tr>
          <td><strong>{i}. <code>{c['site']}</code></strong><span class="cell-sub">{fmt_pct(c['ctv_share_of_site_imps_pct'])} imps TV/STB | CPM {fmt_curr(c['cpm'])}</span></td>
          <td class="num">{fmt_curr(c['cost'])}</td><td class="num">{fmt_int(c['unique_reach'])}<span class="cell-sub">Co-View: {fmt_int(c['coviewed_reach'])}</span></td>
          <td class="num">{fmt_int(c['raw_duplicate_reach_1plus'])}<span class="cell-sub">{fmt_pct(c['raw_overlap_pct_campaign'])} bruto</span></td>
          <td class="num cell-highlight-green"><strong>{fmt_int(c['duplicate_reach_1plus'])}</strong><span class="cell-sub">{fmt_pct(c['duplicate_pct_site'])} conect.</span></td>
          <td class="num"><strong>{fmt_pct(c['overlap_pct_campaign'])}</strong></td>
          <td class="num cell-highlight-blue">{fmt_dec(c['intersecao_compras_1plus'], 1)} comp.</td>
        </tr>"""
        for i, c in enumerate(ctv_chans, 1)
    )
    base_t = ctrl_all["avg_non_ctv_touches"]
    blk_t = combo_blk["avg_non_ctv_touches"]
    blk_t_pct = ((blk_t - base_t) / base_t * 100.0) if base_t > 0 else 0.0
    dev_touch_rows = f"""<tr class="row-subtotal">
      <td><strong>Grupo de Controle: Jornadas Multi-Canal Sem TV/STB</strong><div class="cell-sub">Pedidos no P2C sem toque puro de TV/STB ({fmt_int(ctrl_camp['conversions'])} restrito à camp.)</div></td>
      <td class="num">—</td>
      <td class="num">{fmt_int(ctrl_all['conversions'])}</td>
      <td class="num"><strong>{fmt_dec(base_t)} toques</strong><div class="cell-sub">Camp: {fmt_dec(ctrl_camp['avg_non_ctv_touches'])} toques</div></td>
      <td class="num">Base (0,00)</td>
      <td class="num">Base (0,00%)</td>
    </tr>""" + "".join(
        f"""<tr>
          <td><strong>Jornadas Com TV/STB em <code>{c['site']}</code></strong><div class="cell-sub">{f"{fmt_int(c.get('p2c_combo_camp_conversions', 0))} compras restritas à camp." if c['p2c_combo_all_conversions'] > 0 else 'Apenas venda Solo pura TV/STB observada'}</div></td>
          <td class="num">{fmt_int(c['p2c_solo_conversions'])}</td>
          <td class="num">{fmt_int(c['p2c_combo_all_conversions'])}</td>
          <td class="num">{f"<strong>{fmt_dec(c['p2c_combo_all_nonctv_touches'])} toques</strong>" if c['p2c_combo_all_conversions'] > 0 else '—'}</td>
          <td class="num">{f"{fmt_dec(c['p2c_combo_all_nonctv_touches'] - base_t, sign=True)} toques" if c['p2c_combo_all_conversions'] > 0 else '—'}</td>
          <td class="num{' cell-highlight-green' if (c['p2c_combo_all_conversions'] > 0 and c['p2c_combo_all_nonctv_touches'] < base_t) else ''}">{f"{fmt_pct((c['p2c_combo_all_nonctv_touches'] - base_t) / base_t * 100.0, sign=True)}" if (c['p2c_combo_all_conversions'] > 0 and base_t > 0) else '—'}</td>
        </tr>"""
        for c in ctv_chans if (not c.get("is_residual_bucket") and (c["p2c_combo_all_conversions"] > 0 or c["p2c_solo_conversions"] > 0))
    ) + f"""<tr class="row-total">
      <td><strong>BLOCO TV + STB CONSOLIDADO (Jornadas Multi-Canal Com TV Pura ≥95%)</strong></td>
      <td class="num">{fmt_int(blk['p2c_solo_conversions'])}</td>
      <td class="num">{fmt_int(combo_blk['conversions'])}</td>
      <td class="num">{fmt_dec(blk_t)} toques</td>
      <td class="num">{fmt_dec(blk_t - base_t, sign=True)} toques</td>
      <td class="num">{fmt_pct(blk_t_pct, sign=True) if combo_blk['conversions'] > 0 else '—'}</td>
    </tr>"""

    res_rows = "".join(
        f"""<tr>
          <td><strong>{i}. <code>{c['site']}</code></strong><span class="cell-sub">Overlap Puro: {fmt_pct(c['overlap_pct_campaign'])}</span></td>
          <td class="num">{fmt_curr(c['cost'])}<span class="cell-sub">{fmt_pct(c['cost_share_pct'])} budget</span></td>
          <td class="num">{fmt_dec(c['std_conversions'], 1)} comp.<span class="cell-sub">{fmt_curr(c['std_revenue'])}</span></td>
          <td class="num">{fmt_int(c['p2c_solo_conversions'])} comp.<span class="cell-sub">{fmt_curr(c['p2c_solo_revenue'])}</span></td>
          <td class="num">{fmt_dec(c['intersecao_compras_1plus'], 1)} comp.<span class="cell-sub">AF_e: {fmt_pct(c['lift_lente2_efic_pct'])}{' (teto 50%)' if c.get('afe_cap_applied') else ''}</span></td>
          <td class="num cell-highlight-green">{fmt_dec(c['total_attributed_conversions'], 1)} comp. ({fmt_pct(c['share_campaign_attributed_pct'])})</td>
          <td class="num cell-highlight-blue">+{fmt_curr(c['aov_premium_revenue'])}</td>
          <td class="num"><strong>{fmt_curr(c['total_attributed_revenue'])}</strong><span class="cell-sub">{f"ROAS: {fmt_dec(c['roas_attributed'])}x | CPA: {fmt_curr(c['cpa_attributed'])}" if c['roas_attributed'] is not None else 'Entrega s/ custo'}</span></td>
        </tr>"""
        for i, c in enumerate(ctv_chans, 1)
    )
    comp_rows = "".join(
        f"""<tr>
          <td><strong><code>{r['site']}</code></strong></td>
          <td class="num">{fmt_curr(r['site_method_cost'])}</td>
          <td class="num"><strong>{fmt_curr(r['device_method_cost'])}</strong><span class="cell-sub">{fmt_curr(r['delta_cost'], sign=True)}</span></td>
          <td class="num">{fmt_pct(r['site_method_overlap_pct'])} → {fmt_pct(r['device_raw_overlap_pct'])} → <strong>{fmt_pct(r['device_method_overlap_pct'])}</strong></td>
          <td class="num">{fmt_dec(r['site_method_convs'], 1)} comp.<span class="cell-sub">{fmt_curr(r['site_method_rev'])}</span></td>
          <td class="num">{fmt_dec(r['device_raw_convs'], 1)} comp.<span class="cell-sub">{fmt_curr(r['device_raw_rev'])}</span></td>
          <td class="num cell-highlight-green"><strong>{fmt_dec(r['device_method_convs'], 1)} comp.</strong><span class="cell-sub">{fmt_dec(r['delta_convs'], 1, sign=True)}</span></td>
          <td class="num cell-highlight-blue"><strong>{fmt_curr(r['device_method_rev'])}</strong><span class="cell-sub">{fmt_curr(r['delta_rev'], sign=True)}</span></td>
        </tr>"""
        for r in comp.get("per_site_comparison", [])
    )

    comp_total_row = (
        f"""<tr class="row-total">
          <td><strong>TOTAL BLOCO CTV RECONCILIADO</strong></td>
          <td class="num">{fmt_curr(sb['cost'])}</td>
          <td class="num"><strong>{fmt_curr(blk['cost'])}</strong><span class="cell-sub">{fmt_curr(blk['cost'] - sb['cost'], sign=True)}</span></td>
          <td class="num">{fmt_pct(sb.get('overlap_pct_campaign_sum', sb.get('overlap_pct_sum', 0.0)))} → {fmt_pct(blk['raw_overlap_pct_campaign_sum'])} → <strong>{fmt_pct(blk['overlap_pct_campaign_sum'])}</strong></td>
          <td class="num">{fmt_dec(sb['total_attributed_conversions'], 1)} comp.<span class="cell-sub">{fmt_curr(sb['total_attributed_revenue'])} (ROAS {fmt_dec(sb['roas_attributed'])}x)</span></td>
          <td class="num">{fmt_dec(blk['raw_total_attributed_conversions'], 1)} comp.<span class="cell-sub">{fmt_curr(blk['raw_total_attributed_revenue'])} (ROAS {fmt_dec(blk['raw_roas_attributed'])}x)</span></td>
          <td class="num"><strong>{fmt_dec(blk['total_attributed_conversions'], 1)} comp.</strong><span class="cell-sub">{fmt_dec(blk['total_attributed_conversions'] - sb['total_attributed_conversions'], 1, sign=True)} vs. Site</span></td>
          <td class="num"><strong>{fmt_curr(blk['total_attributed_revenue'])}</strong><span class="cell-sub">ROAS {fmt_dec(blk['roas_attributed'])}x ({fmt_curr(blk['total_attributed_revenue'] - sb['total_attributed_revenue'], sign=True)})</span></td>
        </tr>"""
        if sb else ""
    )

    extra_cost = sum(c["cost"] for c in ctv_chans if not c["had_ctv_in_site_name"])
    iso_pct = 100.0 - ie["exact_connectivity_pct_of_ctv"]
    non_ctv_cost_tot = tot["std_cost"] - blk["cost"]
    dev_card2_badge = "2. Dimensão eventPlatformType &amp; Funil CVR" if has_ev_plat else "2. Ponderação Floodlight &amp; Funil CVR"
    if has_ev_plat and is_cvr_mode:
        dev_card2_text = f"Extraímos <code>Attributed Event Platform Type</code> no CM360 para medir no dispositivo da impressão tanto as compras Standard TV/STB (<code>{fmt_int(blk['std_conversions'])}</code> comp.) quanto o funil <code>CVR Produto → Compra</code> (<code>{fmt_pct(f_blk['cvr_pct'])}</code> vs. <code>{fmt_pct(f_non['cvr_pct'])}</code>; <code>AF_e = {fmt_pct(f_blk['capped_afe_pct'])}</code>)."
        dev_card2_math = f"Cálculo: CVR TV/STB: {fmt_int(f_blk['purchases'])} ÷ {fmt_int(f_blk['product_views'])} = {fmt_pct(f_blk['cvr_pct'])} | AF_e (teto 50%): {fmt_pct(f_blk['capped_afe_pct'])}"
    elif is_cvr_mode:
        dev_card2_text = f"Nas linhas Floodlight sem <code>eventPlatformType</code>, ponderamos compras e views de produto pelo share de impressões TV/STB de cada <code>Placement ID</code> ({fmt_dec(blk['std_conversions'], 1)} comp.; <code>CVR = {fmt_pct(f_blk['cvr_pct'])}</code> vs. <code>{fmt_pct(f_non['cvr_pct'])}</code>; <code>AF_e = {fmt_pct(f_blk['capped_afe_pct'])}</code>)."
        dev_card2_math = f"Cálculo: CVR TV/STB: {fmt_pct(f_blk['cvr_pct'])} vs. Base {fmt_pct(f_non['cvr_pct'])} | AF_e (teto 50%): {fmt_pct(f_blk['capped_afe_pct'])}"
    else:
        dev_card2_text = f"Nas linhas Floodlight, apuramos as compras Standard TV/STB ({fmt_dec(blk['std_conversions'], 1)} comp.) e aplicamos o fallback conservador de valor na Fração Atribuível (<code>AF_e = {fmt_pct(f_blk['capped_afe_pct'])}</code>, teto de 50%)."
        dev_card2_math = f"Cálculo: VT TV Std: {fmt_dec(blk['std_vt_conversions'], 1)} de {fmt_dec(blk['std_conversions'], 1)} | AF_e: {fmt_pct(f_blk['capped_afe_pct'])}"
    std_imp_note = (
        "apuradas diretamente via dimensão Attributed Event Platform Type no CM360 (dispositivo onde o anúncio foi exibido)"
        if has_ev_plat
        else "ponderadas pela participação exata de impressões de cada Placement ID por plataforma (ou cliques em placements click-tracker sem impressões)"
    )
    std_col_hdr = "Std (Imp. TV)" if has_ev_plat else "Std (Pond. TV)"

    slides_html = f"""
      <section class="slide-card">
        <div class="slide-meta"><span class="slide-kicker">PÁGINA 01 • AUDITORIA POR HARDWARE FÍSICO (SMART TV + SET-TOP BOX)</span><span class="slide-scope">platformType IN ('Connected TV' [30004], 'Set top box' [30006])</span></div>
        <h1 class="slide-title">Descobertas ao Identificar CTV por Dispositivo (<code>Smart TV + Set-top Box</code>)</h1>
        <p class="slide-lead">Auditoria da campanha <strong>{meta['brand_name']}</strong> (ID <code>{meta['campaign_id']}</code> • <code>{meta['start_date']}</code> a <code>{meta['end_date']}</code>) classificando CTV pelo dispositivo físico em todos os {len(sites_split)} sites:</p>
        <div class="grid-3">
          <div class="card top-blue bg-blue"><div><span class="badge blue">1. Investimento Físico em TV/STB</span><div class="kpi-huge" style="color:var(--g-blue-dark);">{fmt_curr(blk['cost'])}</div><div class="kpi-sub">{fmt_pct(blk['cost_share_pct'])} do budget (+{fmt_curr(extra_cost)} fora de sites 'CTV')</div><p class="card-text">Captura toda a entrega em <code>Connected TV</code> ({fmt_curr(blk['smart_tv_cost'])}) e <code>Set top box</code> ({fmt_curr(blk['stb_cost'])}), inclusive em canais multi-tela sem <code>CTV</code> no nome.</p></div><div class="math-foot">Cálculo: {fmt_curr(blk['cost'])} ÷ {fmt_curr(tot['std_cost'])} = {fmt_pct(blk['cost_share_pct'])}</div></div>
          <div class="card top-yellow bg-yellow"><div><span class="badge yellow">2. Interseção Pura s/ TV ∩ TV</span><div class="kpi-huge" style="color:var(--g-yellow-dark);">{fmt_pct(ie['exact_overlap_pct_campaign'])}</div><div class="kpi-sub">{fmt_int(ie['exact_cross_device_overlap_1plus'])} disp. ({fmt_pct(ie['exact_connectivity_pct_of_ctv'])} conect. TV)</div><p class="card-text">Pela Lei da Inclusão-Exclusão Exata, expurgamos {fmt_int(ie['tv_tv_and_multisite_purged_devices'])} disp. de sobreposição <code>TV ∩ TV</code>; {fmt_pct(iso_pct)} da audiência TV ficou sem reimpacto pessoal.</p></div><div class="math-foot">Cálculo: {fmt_int(ie['ctv_devices_reach_dedup'])} + {fmt_int(ie['non_ctv_devices_reach_dedup'])} - {fmt_int(ie['campaign_total_reach_dedup'])} = {fmt_int(ie['exact_cross_device_overlap_1plus'])}</div></div>
          <div class="card top-green bg-green"><div><span class="badge green">3. Resultado Puro vs. Bruto</span><div class="kpi-huge" style="color:var(--g-green);">{fmt_dec(blk['total_attributed_conversions'], 1)} comp.</div><div class="kpi-sub">{fmt_curr(blk['total_attributed_revenue'])} s/ TV∩TV ({fmt_dec(blk['raw_total_attributed_conversions'], 1)} c/ TV∩TV)</div><p class="card-text">Fechamento reconciliado (Travas 1 e 2) com ROAS consolidado de <code>{fmt_dec(blk['roas_attributed'])}x</code> e CPA de <code>{fmt_curr(blk['cpa_attributed'])}</code>.</p></div><div class="math-foot">Cálculo: {fmt_int(blk['p2c_solo_conversions'])} Solo + {fmt_dec(blk['assisted_conversions'], 1)} Assist. = {fmt_dec(blk['total_attributed_conversions'], 1)} comp.</div></div>
        </div>
      </section>

      <section class="slide-card slide-hidden">
        <div class="slide-meta"><span class="slide-kicker">PÁGINA 02 • ARQUITETURA MATEMÁTICA POR DISPOSITIVO</span><span class="slide-scope">3 Soluções Algébricas para o Schema CM360 v5</span></div>
        <h2 class="slide-title">Três Soluções Matemáticas para Medir Hardware de TV no CM360</h2>
        <div class="grid-3">
          <div class="card top-blue"><div><span class="badge blue">1. Inclusão-Exclusão Exata</span><p class="card-text">Como o CM360 bloqueia <code>Duplicate Reach</code> filtrado por <code>platformType</code>, extraímos Universo Total (<code>|U|</code>), Bloco TV/STB (<code>|A|</code>) e Bloco Não-CTV (<code>|B|</code>), obtendo <code>|A ∩ B| = |A| + |B| - |U|</code> com exatidão.</p></div><div class="math-foot">Cálculo: Fator Cross-Device: {fmt_int(ie['exact_cross_device_overlap_1plus'])} ÷ {fmt_int(blk['raw_duplicate_reach_1plus_sum'])} = {fmt_dec(ie['pure_cross_device_scale_factor'], 4)}</div></div>
          <div class="card top-yellow"><div><span class="badge yellow">{dev_card2_badge}</span><p class="card-text">{dev_card2_text}</p></div><div class="math-foot">{dev_card2_math}</div></div>
          <div class="card top-green"><div><span class="badge green">3. Pureza P2C ≥95% (Solo, AOV &amp; Toques)</span><p class="card-text">Isolamos {fmt_int(res['p2c_touch_purity_audit']['pure_ctv_touches_ge_95pct'])} toques determinísticos puros de TV (≥95%) no P2C para apurar Vendas Solo reais ({fmt_int(blk['p2c_solo_conversions'])} ped.), preservar o Controle do AOV ({fmt_curr(ctrl_camp['aov'])}) e medir a aceleração comportamental de toques Não-CTV (<code>{fmt_dec(blk_t)}</code> vs. <code>{fmt_dec(base_t)}</code>; <code>{fmt_pct(blk_t_pct, sign=True)}</code>).</p></div><div class="math-foot">Cálculo: Toques mistos isolados (5%–95%): {fmt_int(res['p2c_touch_purity_audit']['mixed_touches_5_to_95pct'])} | Δ Toques P2C: {fmt_dec(blk_t - base_t, sign=True)}</div></div>
        </div>
      </section>

      <section class="slide-card slide-hidden">
        <div class="slide-meta"><span class="slide-kicker">PÁGINA 03 • GUIA VISUAL POR DEVICE TYPE</span><span class="slide-scope">3 Infográficos gerados dinamicamente</span></div>
        <h2 class="slide-title">Visualizando a Jornada Física, a Inclusão-Exclusão Exata e o Comparativo</h2>
        <div class="vis-tabs no-print">
          <button onclick="showVisTab(0)" class="vis-tab active">1. Jornada TV + STB → Checkout</button>
          <button onclick="showVisTab(1)" class="vis-tab">2. Inclusão-Exclusão Exata</button>
          <button onclick="showVisTab(2)" class="vis-tab">3. Investimento &amp; Receita</button>
          <button onclick="showVisTab(3)" class="vis-tab">Exibir Todos os 3</button>
        </div>
        <div class="vis-panel"><img src="{b64_1}" alt="Ilustração 1" class="vis-img"></div>
        <div class="vis-panel slide-hidden"><img src="{b64_2}" alt="Ilustração 2" class="vis-img"></div>
        <div class="vis-panel slide-hidden"><img src="{b64_3}" alt="Ilustração 3" class="vis-img"></div>
      </section>

      <section class="slide-card slide-hidden">
        <div class="slide-meta"><span class="slide-kicker">PÁGINA 04 • RAIO-X DE PLATAFORMAS E SITES (100% RECONCILIADO)</span><span class="slide-scope">Trava 2: Soma == {fmt_curr(tot['std_cost'])} (100,00%)</span></div>
        <h2 class="slide-title">Entrega Exata em Smart TV (30004) e Set-top Box (30006) por Plataforma e Site</h2>
        <div class="table-box"><div class="table-head-bar"><span class="table-head-title">1. Abertura por Platform Type (CM360)</span></div><div class="table-scroll"><table><thead><tr><th>Platform Type</th><th class="num">Custo</th><th class="num">% Budget</th><th class="num">Impressões</th><th class="num">Unique Reach</th><th class="num">Co-Viewed</th><th class="num cell-highlight-blue">Compras Std (Imp.)</th><th class="num">Receita Std</th><th class="num">Checkouts Std</th></tr></thead><tbody>{plat_rows}<tr class="row-total"><td>TOTAL CAMPANHA</td><td class="num">{fmt_curr(tot['std_cost'])}</td><td class="num">100,00%</td><td class="num">{fmt_int(tot['std_impressions'])}</td><td class="num">{fmt_int(tot['reach_devices'])}</td><td class="num">{fmt_int(tot['reach_coviewed'])}</td><td class="num">{fmt_dec(tot['std_conversions'], 1)}</td><td class="num">{fmt_curr(tot['std_revenue'])}</td><td class="num">{fmt_int(tot['std_conversions'])}</td></tr></tbody></table></div><div class="table-foot-math">Como calculamos: % Budget = Custo Plataforma ÷ {fmt_curr(tot['std_cost'])} | Compras Std (Imp.) {std_imp_note}.</div></div>
        <div class="table-box"><div class="table-head-bar"><span class="table-head-title">2. Decomposição dos {len(sites_split)} Sites (TV + STB vs. Outros Dispositivos)</span></div><div class="table-scroll"><table><thead><tr><th>Site (CM360)</th><th class="num">Custo Total</th><th class="num">Custo TV + STB</th><th class="num">Custo Mobile/PC</th><th class="num">% CTV no Site</th><th class="num">Imps TV + STB</th><th class="num">Compras Std (TV/Tot)</th></tr></thead><tbody>{split_rows}<tr class="row-total"><td>TOTAL CAMPANHA ({len(sites_split)} Sites)</td><td class="num">{fmt_curr(tot['std_cost'])}</td><td class="num">{fmt_curr(blk['cost'])}</td><td class="num">{fmt_curr(non_ctv_cost_tot)}</td><td class="num">{fmt_pct(blk['cost_share_pct'])}</td><td class="num">{fmt_int(blk['impressions'])}</td><td class="num">{fmt_dec(blk['std_conversions'], 1)} / {fmt_int(tot['std_conversions'])}</td></tr></tbody></table></div><div class="table-foot-math">Como calculamos: Custo TV + STB + Custo Mobile/PC = {fmt_curr(tot['std_cost'])} (100,00% reconciliado) | % CTV no Site = Custo TV + STB ÷ Custo Total do Site.</div></div>
      </section>

      <section class="slide-card slide-hidden">
        <div class="slide-meta"><span class="slide-kicker">PÁGINA 05 • ALCANCE, INTERSEÇÃO CROSS-DEVICE (1+) E DIAGNÓSTICO DE TOQUES P2C</span><span class="slide-scope">Alocação Pura s/ TV∩TV vs. Soma Bruta Sites</span></div>
        <h2 class="slide-title">Alcance Único, Interseção Cross-Device Pura (<code>TV ∩ Mobile/PC</code>) e Aceleração de Toques</h2>
        <div class="table-box"><div class="table-head-bar"><span class="table-head-title">1. Abertura de Alcance e Interseção Cross-Device Pura (Sem TV ∩ TV)</span></div><div class="table-scroll"><table><thead><tr><th>Canal com Entrega TV/STB</th><th class="num">Custo TV+STB</th><th class="num">Reach TV+STB</th><th class="num">Overlap Bruto</th><th class="num cell-highlight-green">Overlap Puro</th><th class="num">% Overlap Puro</th><th class="num cell-highlight-blue">Compras Interseção</th></tr></thead><tbody>{reach_rows}
        <tr class="row-total"><td>BLOCO TV + STB EXATO (Sem TV ∩ TV)</td><td class="num">{fmt_curr(blk['cost'])}</td><td class="num">{fmt_int(ie['ctv_devices_reach_dedup'])}</td><td class="num">—</td><td class="num">{fmt_int(blk['duplicate_reach_1plus_sum'])}</td><td class="num">{fmt_pct(blk['overlap_pct_campaign_sum'])}</td><td class="num">{fmt_dec(blk['intersecao_compras_1plus'], 1)} comp.</td></tr>
        <tr class="row-raw"><td>SENSIBILIDADE: SOMA BRUTA SITES (Com TV ∩ TV)</td><td class="num">{fmt_curr(blk['cost'])}</td><td class="num">—</td><td class="num">{fmt_int(blk['raw_duplicate_reach_1plus_sum'])}</td><td class="num">—</td><td class="num">{fmt_pct(blk['raw_overlap_pct_campaign_sum'])}</td><td class="num">{fmt_dec(blk['raw_intersecao_compras_1plus'], 1)} comp.</td></tr>
        </tbody></table></div><div class="table-foot-math">Como calculamos: Overlap Puro = Overlap Bruto × {fmt_dec(ie['pure_cross_device_scale_factor'], 4)} | % Overlap Puro = Overlap Puro ÷ {fmt_int(tot['reach_devices'])} disp. | Compras Interseção = {fmt_int(tot['p2c_total_conversions'])} × (% Overlap Puro).</div></div>
        <div class="table-box"><div class="table-head-bar"><span class="table-head-title">2. Diagnóstico Comportamental no P2C (14d): Aceleração de Toques Não-CTV até a Compra</span><span style="color:var(--g-yellow-dark);font-weight:700;">Indicador Diagnóstico (não usado como proxy de compras)</span></div><div class="table-scroll"><table><thead><tr><th>Coorte de Jornada (P2C 14d • TV Pura ≥95%)</th><th class="num">Vendas Solo P2C</th><th class="num">Compras Combo</th><th class="num">Média Toques Não-CTV</th><th class="num">Δ vs. Controle</th><th class="num">Variação de Toques (%)</th></tr></thead><tbody>{dev_touch_rows}</tbody></table></div><div class="table-foot-math">Como calculamos (evidência comportamental complementar): Δ Toques = Média Toques Não-CTV Com TV/STB - Média Toques Controle Sem TV/STB ({fmt_dec(blk_t)} - {fmt_dec(base_t)} = {fmt_dec(blk_t - base_t, sign=True)} toques; {fmt_pct(blk_t_pct, sign=True)}). Nota metodológica: indicador de encurtamento da jornada; o volume de Compras Assistidas segue estritamente o AF_e de CVR Produto → Compra.</div></div>
      </section>

      <section class="slide-card slide-hidden">
        <div class="slide-meta"><span class="slide-kicker">PÁGINA 06 • RESULTADO FINAL POR DEVICE TYPE</span><span class="slide-scope">Fechamento Exato Trava 1 &amp; Trava 2</span></div>
        <h2 class="slide-title">Resultado Final Device CTV: {fmt_dec(blk['total_attributed_conversions'], 1)} Compras ({fmt_curr(blk['total_attributed_revenue'])})</h2>
        <div class="table-box"><div class="table-scroll"><table><thead><tr><th>Canal (Fatia TV+STB)</th><th class="num">Custo TV+STB</th><th class="num">{std_col_hdr}</th><th class="num">Solo P2C</th><th class="num">Interseção Pura</th><th class="num cell-highlight-green">Compras Atribuídas</th><th class="num cell-highlight-blue">Prêmio AOV (R$)</th><th class="num">Receita, ROAS &amp; CPA</th></tr></thead><tbody>{res_rows}
        <tr class="row-total"><td>CONSOLIDADO PURO CROSS-DEVICE (Sem TV ∩ TV)</td><td class="num">{fmt_curr(blk['cost'])}</td><td class="num">{fmt_dec(blk['std_conversions'], 1)} comp.</td><td class="num">{fmt_int(blk['p2c_solo_conversions'])} comp.</td><td class="num">{fmt_dec(blk['intersecao_compras_1plus'], 1)} comp.</td><td class="num">{fmt_dec(blk['total_attributed_conversions'], 1)} comp. ({fmt_pct(blk['share_campaign_attributed_pct'])})</td><td class="num">+{fmt_curr(blk['aov_premium_revenue'])}</td><td class="num">{fmt_curr(blk['total_attributed_revenue'])} (ROAS {fmt_dec(blk['roas_attributed'])}x)</td></tr>
        <tr class="row-raw"><td>SENSIBILIDADE: SOMA BRUTA SITES (Com TV ∩ TV)</td><td class="num">{fmt_curr(blk['cost'])}</td><td class="num">{fmt_dec(blk['std_conversions'], 1)} comp.</td><td class="num">{fmt_int(blk['p2c_solo_conversions'])} comp.</td><td class="num">{fmt_dec(blk['raw_intersecao_compras_1plus'], 1)} comp.</td><td class="num">{fmt_dec(blk['raw_total_attributed_conversions'], 1)} comp. ({fmt_pct(blk['raw_share_campaign_attributed_pct'])})</td><td class="num">—</td><td class="num">{fmt_curr(blk['raw_total_attributed_revenue'])} (ROAS {fmt_dec(blk['raw_roas_attributed'])}x)</td></tr>
        </tbody></table></div><div class="table-foot-math">Como calculamos: Compras Atribuídas = Solo P2C + (Interseção Pura × AF_e CVR Produto→Compra, teto 50%) | Receita = Receita Solo + (Compras Assistidas × AOV Base Controle) + Prêmio AOV (R$) | ROAS = Receita ÷ Custo TV+STB. Nota financeira: superar 1,0x de ROAS significa gerar mais receita atribuída do que o custo de mídia investido no veículo (não equivale a lucro líquido contábil).</div></div>
      </section>

      <section class="slide-card slide-hidden">
        <div class="slide-meta"><span class="slide-kicker">PÁGINA 07 • COMPARATIVO METODOLÓGICO</span><span class="slide-scope">Mesma janela ({meta['start_date']} a {meta['end_date']}) e campanha ({meta['campaign_id']})</span></div>
        <h2 class="slide-title">Comparação Canal a Canal: Critério Nome do Site vs. Device Bruto vs. Device Puro</h2>
        {f'<div class="table-box"><div class="table-scroll"><table><thead><tr><th>Canal</th><th class="num">Custo (Site)</th><th class="num">Custo (Device)</th><th class="num">% Overlap (Site→Bruto→Puro)</th><th class="num">1) Por Site</th><th class="num">2) Device Bruto</th><th class="num cell-highlight-green">3) Compras Puro</th><th class="num cell-highlight-blue">3) Receita Puro</th></tr></thead><tbody>{comp_rows}{comp_total_row}</tbody></table></div><div class="table-foot-math">Como calculamos: Δ Custo = Custo Device (TV+STB) - Custo Site | Δ Compras e Δ Receita = Resultado Device Puro (Sem TV∩TV) - Resultado Critério Site na mesma janela e Campaign ID.</div></div>' if comp_rows else '<div class="card bg-blue"><p class="card-text">Para habilitar a tabela comparativa Site vs. Device, defina <code>baseline_site_results_path</code> no JSON de configuração apontando para o estudo por Site da mesma campanha.</p></div>'}
      </section>

      <section class="slide-card slide-hidden">
        <div class="slide-meta"><span class="slide-kicker">PÁGINA 08 • DIAGNÓSTICO TÉCNICO E BOAS PRÁTICAS DE TRAFFICKING</span><span class="slide-scope">Síntese para {meta['agency_name']} &amp; {meta['brand_name']}</span></div>
        <h2 class="slide-title">Quando Usar <code>mode="site"</code> vs. <code>mode="device"</code> e Recomendações de Trafficking</h2>
        <div class="grid-3">
          <div class="card top-green"><div><span class="badge green">1. Vantagens do Modo Device</span><ul class="clean-list"><li>Descobre entrega real de Smart TV em campanhas multi-tela (ex.: Video Reach / Demand Gen).</li><li>Expurga sobreposição <code>TV ∩ TV</code> via Inclusão-Exclusão Exata, medindo conectividade Cross-Device pura.</li></ul></div></div>
          <div class="card top-yellow"><div><span class="badge yellow">2. Cuidados com Pixels 1x1 Externos</span><ul class="clean-list"><li>Parceiros CTV medidos apenas por pixel 1x1 sem User-Agent estruturado podem cair em <code>Unknown platform</code> no CM360.</li><li>Placements mistos (Mobile + TV juntos) diluem a pureza determinística por toque no CSV do P2C.</li></ul></div></div>
          <div class="card top-blue"><div><span class="badge blue">3. Boas Práticas para Agências</span><ul class="clean-list"><li>Trafegar Placements exclusivos para Smart TV mesmo dentro de Line Items multi-tela.</li><li>Vincular audiências de CTV ao retargeting mobile para elevar a ponte <code>TV → Smartphone</code>.</li></ul></div></div>
        </div>
      </section>
    """
    titles = [
        "Descobertas por Device Type", "Inclusão-Exclusão Exata", "Guia Visual (3 Diagramas)", "Raio-X Plataforma & Sites",
        "Alcance, Overlap & Toques", "Resultado Final Device CTV", "Comparativo Site vs. Device", "Diagnóstico & Boas Práticas",
    ]
    return {
        "id": "device",
        "tab_label": "2. Validação por Device Type (Smart TV + STB)",
        "badge_label": "Device Type • Smart TV + STB",
        "badge_cls": "green",
        "titles": titles,
        "slides_html": slides_html,
    }


def _render_device_html(cfg: dict, res: dict, out_dir: Path) -> str:
    deck = _build_device_deck(res, out_dir)
    out_html = out_dir / f"Relatorio_Teste_Device_CTV_{cfg['case_slug']}.html"
    out_html.write_text(_render_shell(f"Auditoria CTV Device Type — {res['meta']['brand_name']}", res["meta"], [deck]), encoding="utf-8")
    return str(out_html)


def _render_unified_html(cfg: dict, res_site: dict, res_dev: dict, out_dir: Path) -> str:
    d_site = _build_site_deck(res_site, out_dir)
    d_dev = _build_device_deck(res_dev, out_dir)
    naming_ok = bool(res_site["meta"].get("naming_detected", len(res_site.get("ctv_channels", [])) > 0))
    default_idx = 0 if naming_ok else 1
    fallback_msg = (
        ""
        if naming_ok
        else "<strong>Validação Automática por Device Type Ativada:</strong> Nenhum veículo com <code>CTV</code> no nome do Site foi identificado nesta campanha. Exibindo automaticamente os resultados pelo dispositivo físico (<code>Connected TV + Set top box</code>)."
    )
    out_html = out_dir / f"Relatorio_Unificado_CTV_{cfg['case_slug']}.html"
    out_html.write_text(
        _render_shell(
            f"Relatório Unificado CTV (Site + Device Type) — {res_dev['meta']['brand_name']}",
            res_dev["meta"],
            [d_site, d_dev],
            default_deck=default_idx,
            auto_fallback_msg=fallback_msg,
        ),
        encoding="utf-8",
    )
    return str(out_html)


def generate_html_report(config_path: str, mode_override: str | None = None) -> str:
    cfg = load_config(config_path, mode_override=mode_override)
    mode = get_mode(cfg)
    out_dir = Path(cfg["output_dir"])
    if mode == "both":
        site_candidates = [out_dir / "methodology_results.json"]
        if cfg.get("baseline_site_results_path"):
            site_candidates.append(resolve_path(cfg["baseline_site_results_path"], must_exist=True))
        site_file = next((p for p in site_candidates if p.exists()), None)
        dev_file = out_dir / "methodology_device_results.json"
        if not site_file or not dev_file.exists():
            raise FileNotFoundError(f"Resultados Site/Device ausentes em {out_dir}. Rode step2_compute_methodology.py --mode both primeiro.")
        res_site = json.loads(site_file.read_text(encoding="utf-8"))
        res_dev = json.loads(dev_file.read_text(encoding="utf-8"))
        _render_site_html(cfg, res_site, out_dir)
        _render_device_html(cfg, res_dev, out_dir)
        out_html = _render_unified_html(cfg, res_site, res_dev, out_dir)
        print(f"[ETAPA 3 - BOTH CONCLUÍDA] HTML Unificado (Site + Device Type) salvo em: {out_html}")
        return out_html

    res_file = out_dir / ("methodology_device_results.json" if mode == "device" else "methodology_results.json")
    res = json.loads(res_file.read_text(encoding="utf-8"))
    out_html = _render_device_html(cfg, res, out_dir) if mode == "device" else _render_site_html(cfg, res, out_dir)
    print(f"[ETAPA 3 - {mode.upper()} CONCLUÍDA] HTML salvo em: {out_html}")
    return out_html


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Gerador unificado do relatório HTML executivo e infográficos")
    p.add_argument("--config", required=True, help="Caminho para o JSON de configuração")
    p.add_argument("--mode", choices=["both", "site", "device"], default=None, help="Sobrescrever modo (both | site | device)")
    a = p.parse_args()
    generate_html_report(a.config, mode_override=a.mode)
