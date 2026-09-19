"""Generate a professional, self-contained HTML dashboard from real roster data."""
import json
import shutil
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
ROSTER_CSV = BASE_DIR / "dataset" / "processed" / "student_risk_scores.csv"

# Vite serves everything under `frontend/public` at the site root and copies it
# into `dist` on build, so generating there makes the preview reachable from
# `npm run dev`, `npm run preview` AND the Flask `/preview` route (which reads
# the same file). Nothing here is committed - it is all derived from the roster.
PUBLIC_DIR = BASE_DIR / "frontend" / "public"
OUTPUT_HTML = PUBLIC_DIR / "dashboard_preview.html"
PUBLIC_JS_DIR = PUBLIC_DIR / "js"
ASSET_FILES = ("theme.js", "i18n.js", "controls.js")


def copy_assets():
    """Place the page's same-origin scripts beside it so Vite will serve them."""
    source_js = BASE_DIR / "frontend" / "js"
    PUBLIC_JS_DIR.mkdir(parents=True, exist_ok=True)
    for name in ASSET_FILES:
        source = source_js / name
        if source.is_file():
            shutil.copyfile(source, PUBLIC_JS_DIR / name)
    # The preview header references /logo.svg, so keep a copy next to it for
    # Vite/static builds (Flask already serves it from the frontend root).
    logo = BASE_DIR / "frontend" / "logo.svg"
    if logo.is_file():
        shutil.copyfile(logo, PUBLIC_DIR / "logo.svg")
    # The preview (and all pages) reference /favicon.svg; copy it beside the
    # generated page too so Vite/static builds serve the same mark.
    favicon = BASE_DIR / "frontend" / "favicon.svg"
    if favicon.is_file():
        shutil.copyfile(favicon, PUBLIC_DIR / "favicon.svg")


def main():
    df = pd.read_csv(ROSTER_CSV)

    records = df.to_dict(orient="records")
    for r in records:
        r["Risk_Probability"] = round(float(r["Risk_Probability"]), 4)

    feats = ["Attendance_Rate", "GPA", "CGPA", "Stress_Index"]
    data = {
        "records": records,
        "departments": sorted(df["Department"].unique().tolist()),
        "semesters": ["Year 1", "Year 2", "Year 3", "Year 4"],
        "featureRange": {f: [float(df[f].min()), float(df[f].max())] for f in feats},
    }

    html = TEMPLATE.replace("/*__DATA__*/", json.dumps(data, separators=(",", ":")))

    OUTPUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_HTML.write_text(html, encoding="utf-8")
    copy_assets()
    print(f"Wrote {OUTPUT_HTML}")


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>EduGuard — Live Student Risk Dashboard</title>
<link rel="icon" type="image/svg+xml" href="/favicon.svg" />
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>
<script src="/js/theme.js"></script>
<script>/* The public preview always opens in the light theme: force it before the page paints so a saved dark/system preference (or the OS scheme) can't darken the landing and cause a flash. */ if (window.Theme) Theme.set("light");</script>
<script src="/js/i18n.js"></script>
<style>
:root {
  --bg: #08111f;
  --panel: rgba(13, 27, 45, 0.78);
  --panel-strong: rgba(11, 22, 37, 0.92);
  --text: #eaf2ff;
  --muted: #9bb0c9;
  --line: rgba(168, 194, 229, 0.18);
  --cyan: #61dfff;
  --cyan-2: #22c7d7;
  --amber: #ffcb6b;
  --green: #66e3a0;
  --red: #ff7d7d;
  --shadow: 0 24px 80px rgba(0, 0, 0, 0.38);
  --radius: 24px;
  --radius-s: 16px;
}
* { box-sizing: border-box; }
html, body {
  margin: 0; min-height: 100%;
  background:
    radial-gradient(circle at top left, rgba(97,223,255,0.14), transparent 28%),
    radial-gradient(circle at 85% 15%, rgba(102,227,160,0.12), transparent 22%),
    radial-gradient(circle at 30% 80%, rgba(255,203,107,0.10), transparent 24%),
    linear-gradient(180deg, #07101d 0%, #0a1526 56%, #07111d 100%);
  color: var(--text);
  font-family: "Segoe UI", "Inter", system-ui, -apple-system, sans-serif;
}
body::before {
  content: ""; position: fixed; inset: 0; pointer-events: none;
  background-image:
    linear-gradient(rgba(255,255,255,0.025) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,0.025) 1px, transparent 1px);
  background-size: 44px 44px;
  mask-image: linear-gradient(180deg, rgba(0,0,0,0.8), transparent 88%);
}
.shell { width: min(1200px, calc(100vw - 32px)); margin: 0 auto; padding: 28px 0 42px; position: relative; z-index: 1; }
.panel {
  border: 1px solid var(--line);
  background: var(--panel);
  backdrop-filter: blur(18px);
  box-shadow: var(--shadow);
  border-radius: var(--radius);
}
.topbar {
  display: flex; align-items: center; justify-content: space-between; gap: 16px;
  padding: 18px 22px; margin-bottom: 22px;
  border-radius: 999px;
  background: rgba(8, 17, 31, 0.55);
}
.brand { display: flex; align-items: center; gap: 14px; min-width: 0; }
.mark {
  width: 46px; height: 46px; border-radius: 14px;
  background: linear-gradient(145deg, var(--cyan), var(--cyan-2));
  box-shadow: 0 12px 28px rgba(34,199,215,0.28);
  display: grid; place-items: center; color: #06111d;
  font-weight: 900; letter-spacing: 0.04em; overflow: hidden;
}
.mark img { width: 100%; height: 100%; object-fit: cover; display: block; }
.brand h1 { margin: 0; font-size: clamp(1rem, 2vw, 1.25rem); letter-spacing: 0.08em; text-transform: uppercase; }
.brand p { margin: 2px 0 0; color: var(--muted); font-size: 0.95rem; }
.pill {
  padding: 10px 14px; border: 1px solid var(--line); border-radius: 999px;
  color: var(--muted); background: rgba(255,255,255,0.03); white-space: nowrap;
}
.topbar-actions { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.topbar-link {
  text-decoration: none; color: var(--text);
  transition: border-color 160ms ease, color 160ms ease;
}
.topbar-link:hover { border-color: var(--cyan); color: var(--cyan); }
.tabs { display: flex; flex-wrap: wrap; gap: 10px; margin: 0 0 22px; }
.tabs button {
  appearance: none; border: 1px solid var(--line);
  background: rgba(255,255,255,0.03); color: var(--text);
  padding: 12px 20px; border-radius: 999px; font: inherit; font-weight: 700;
  cursor: pointer; transition: transform 160ms ease, border-color 160ms ease, background 160ms ease, color 160ms ease;
}
.tabs button:hover { transform: translateY(-1px); border-color: rgba(255,255,255,0.28); }
.tabs button.active { background: linear-gradient(145deg, var(--cyan), var(--cyan-2)); color: #041019; border-color: transparent; }
.view { display: none; }
.view.active { display: block; animation: fade 220ms ease; }
@keyframes fade { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }
.grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 22px; }
.stat { padding: 18px; border-radius: 22px; background: var(--panel-strong); border: 1px solid var(--line); }
.stat .label { color: var(--muted); font-size: 0.85rem; margin-bottom: 12px; }
.stat .value { font-size: 1.9rem; font-weight: 800; line-height: 1; }
.stat .note { margin-top: 10px; color: var(--muted); font-size: 0.88rem; }
.double { display: grid; grid-template-columns: 1.1fr 0.9fr; gap: 18px; margin-bottom: 22px; }
.chart-panel { padding: 20px; }
.chart-panel h3 { margin: 0 0 14px; font-size: 1.05rem; }
.chart-panel .wrap { position: relative; height: 300px; }
table { width: 100%; border-collapse: collapse; }
th, td { text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--line); font-size: 0.92rem; }
th { color: var(--muted); font-weight: 600; }
tbody tr:hover { background: rgba(255,255,255,0.03); }
.badge { display: inline-block; padding: 4px 10px; border-radius: 999px; font-size: 0.78rem; font-weight: 700; }
.badge.high { background: rgba(255,125,125,0.16); color: var(--red); border: 1px solid rgba(255,125,125,0.3); }
.badge.medium { background: rgba(255,203,107,0.14); color: var(--amber); border: 1px solid rgba(255,203,107,0.26); }
.badge.low { background: rgba(102,227,160,0.14); color: var(--green); border: 1px solid rgba(102,227,160,0.26); }
.bar { height: 8px; border-radius: 999px; background: rgba(255,255,255,0.07); overflow: hidden; min-width: 90px; }
.bar > span { display: block; height: 100%; border-radius: inherit; }
.field { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 18px; }
select, input[type="text"], input[type="number"] {
  appearance: none; border: 1px solid var(--line); background: rgba(255,255,255,0.04);
  color: var(--text); padding: 11px 14px; border-radius: 999px; font: inherit; outline: none;
}
select:focus, input:focus { border-color: var(--cyan); }
.lookup { display: flex; gap: 10px; margin-bottom: 18px; }
.lookup input { flex: 1; max-width: 240px; }
.btn {
  appearance: none; border: 1px solid var(--line); background: rgba(255,255,255,0.03);
  color: var(--text); padding: 11px 18px; border-radius: 999px; font: inherit; font-weight: 700;
  cursor: pointer;
}
.btn.primary { background: linear-gradient(145deg, var(--cyan), var(--cyan-2)); color: #041019; border-color: transparent; }
.student-result { padding: 22px; margin-top: 6px; }
.student-result.hidden { display: none; }
.result-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.result-head h3 { margin: 0; font-size: 1.3rem; }
.result-meta { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 18px 0; }
.meta { padding: 14px; border-radius: var(--radius-s); background: rgba(255,255,255,0.03); border: 1px solid var(--line); }
.meta span { display: block; color: var(--muted); font-size: 0.8rem; margin-bottom: 6px; }
.meta strong { font-size: 1.05rem; }
.missing { color: var(--muted); padding: 30px; text-align: center; border: 1px dashed var(--line); border-radius: var(--radius-s); }
.pager { display: flex; justify-content: space-between; align-items: center; margin-top: 14px; gap: 12px; }
.pager .count { color: var(--muted); font-size: 0.9rem; }
.footer { margin-top: 20px; padding: 18px 22px; color: var(--muted); border-top: 1px solid var(--line); text-align: center; font-size: 0.95rem; }
@media (max-width: 980px) {
  .grid, .double, .result-meta { grid-template-columns: 1fr 1fr; }
  .topbar { border-radius: 24px; flex-direction: column; align-items: flex-start; }
}
@media (max-width: 620px) {
  .shell { width: min(100vw - 20px, 1200px); padding-top: 12px; }
  .grid, .double, .result-meta { grid-template-columns: 1fr; }
}
html[data-theme="light"], html[data-resolved-theme="light"] {
  --bg: #eef4fb;
  --panel: rgba(255, 255, 255, 0.82);
  --panel-strong: rgba(255, 255, 255, 0.92);
  --text: #0f1c2e;
  --muted: #56708d;
  --line: rgba(15, 28, 46, 0.14);
  --shadow: 0 24px 80px rgba(30, 60, 100, 0.18);
}
html[data-theme="light"] html, html[data-resolved-theme="light"] html,
html[data-theme="light"] body, html[data-resolved-theme="light"] body {
  background:
    radial-gradient(circle at top left, rgba(97,223,255,0.35), transparent 28%),
    radial-gradient(circle at 85% 15%, rgba(102,227,160,0.28), transparent 22%),
    radial-gradient(circle at 30% 80%, rgba(255,203,107,0.22), transparent 24%),
    linear-gradient(180deg, #f4f8fe 0%, #e9f1fb 56%, #f2f7fd 100%);
}
html[data-theme="light"] .topbar, html[data-resolved-theme="light"] .topbar { background: rgba(255, 255, 255, 0.65); }
html[data-theme="light"] .tabs button,
html[data-resolved-theme="light"] .tabs button,
html[data-theme="light"] .btn,
html[data-resolved-theme="light"] .btn,
html[data-theme="light"] .meta,
html[data-resolved-theme="light"] .meta,
html[data-theme="light"] select,
html[data-resolved-theme="light"] select,
html[data-theme="light"] input[type="text"],
html[data-resolved-theme="light"] input[type="text"],
html[data-theme="light"] input[type="number"],
html[data-resolved-theme="light"] input[type="number"] { background: rgba(15, 28, 46, 0.05); }
html[data-theme="light"] tbody tr:hover, html[data-resolved-theme="light"] tbody tr:hover { background: rgba(15, 28, 46, 0.05); }
html[data-theme="light"] .bar, html[data-resolved-theme="light"] .bar { background: rgba(15, 28, 46, 0.1); }
html[data-theme="light"] .pill, html[data-resolved-theme="light"] .pill { background: rgba(15, 28, 46, 0.05); }

/* Ocean / Sunset / Forest share the same light surface treatment as Light,
   each with its own accent palette. */
html[data-theme="ocean"], html[data-resolved-theme="ocean"] { --bg:#e8f4f8; --panel:rgba(255,255,255,0.82); --panel-strong:rgba(255,255,255,0.92); --text:#0c4a6e; --muted:#5a8fa8; --line:rgba(12,74,110,0.18); --cyan:#0891b2; --cyan-2:#0e7490; --amber:#d97706; --green:#16a34a; --red:#dc2626; --shadow:0 24px 80px rgba(8,145,178,0.18); }
html[data-theme="sunset"], html[data-resolved-theme="sunset"] { --bg:#fef2f2; --panel:rgba(255,255,255,0.82); --panel-strong:rgba(255,255,255,0.92); --text:#7f1d1d; --muted:#c2692f; --line:rgba(127,29,29,0.16); --cyan:#ea580c; --cyan-2:#c2410c; --amber:#f59e0b; --green:#16a34a; --red:#dc2626; --shadow:0 24px 80px rgba(234,88,12,0.18); }
html[data-theme="forest"], html[data-resolved-theme="forest"] { --bg:#f0fdf4; --panel:rgba(255,255,255,0.82); --panel-strong:rgba(255,255,255,0.92); --text:#14532d; --muted:#5e926e; --line:rgba(20,83,45,0.16); --cyan:#16a34a; --cyan-2:#15803d; --amber:#d97706; --green:#059669; --red:#dc2626; --shadow:0 24px 80px rgba(22,163,74,0.18); }
html[data-theme="ocean"] html, html[data-resolved-theme="ocean"] html,
html[data-theme="ocean"] body, html[data-resolved-theme="ocean"] body { background: radial-gradient(circle at top left, rgba(34,211,238,0.30), transparent 28%), radial-gradient(circle at 85% 15%, rgba(22,225,255,0.22), transparent 22%), radial-gradient(circle at 30% 80%, rgba(8,145,178,0.14), transparent 24%), linear-gradient(180deg, #f0fafd 0%, #e3f2fa 56%, #edf8fc 100%); }
html[data-theme="sunset"] html, html[data-resolved-theme="sunset"] html,
html[data-theme="sunset"] body, html[data-resolved-theme="sunset"] body { background: radial-gradient(circle at top left, rgba(251,146,60,0.28), transparent 28%), radial-gradient(circle at 85% 15%, rgba(244,63,94,0.18), transparent 22%), radial-gradient(circle at 30% 80%, rgba(245,158,11,0.16), transparent 24%), linear-gradient(180deg, #fff7f2 0%, #fdeee6 56%, #fef6f1 100%); }
html[data-theme="forest"] html, html[data-resolved-theme="forest"] html,
html[data-theme="forest"] body, html[data-resolved-theme="forest"] body { background: radial-gradient(circle at top left, rgba(74,222,128,0.26), transparent 28%), radial-gradient(circle at 85% 15%, rgba(22,163,74,0.16), transparent 22%), radial-gradient(circle at 30% 80%, rgba(5,150,105,0.14), transparent 24%), linear-gradient(180deg, #f7fdf8 0%, #ecf8ef 56%, #f5fbf7 100%); }
html[data-theme="ocean"] .topbar, html[data-resolved-theme="ocean"] .topbar,
html[data-theme="sunset"] .topbar, html[data-resolved-theme="sunset"] .topbar,
html[data-theme="forest"] .topbar, html[data-resolved-theme="forest"] .topbar { background: rgba(255, 255, 255, 0.65); }
html[data-theme="ocean"] .tabs button, html[data-resolved-theme="ocean"] .tabs button,
html[data-theme="sunset"] .tabs button, html[data-resolved-theme="sunset"] .tabs button,
html[data-theme="forest"] .tabs button, html[data-resolved-theme="forest"] .tabs button,
html[data-theme="ocean"] .btn, html[data-resolved-theme="ocean"] .btn,
html[data-theme="sunset"] .btn, html[data-resolved-theme="sunset"] .btn,
html[data-theme="forest"] .btn, html[data-resolved-theme="forest"] .btn,
html[data-theme="ocean"] .meta, html[data-resolved-theme="ocean"] .meta,
html[data-theme="sunset"] .meta, html[data-resolved-theme="sunset"] .meta,
html[data-theme="forest"] .meta, html[data-resolved-theme="forest"] .meta,
html[data-theme="ocean"] select, html[data-resolved-theme="ocean"] select,
html[data-theme="sunset"] select, html[data-resolved-theme="sunset"] select,
html[data-theme="forest"] select, html[data-resolved-theme="forest"] select,
html[data-theme="ocean"] input[type="text"], html[data-resolved-theme="ocean"] input[type="text"],
html[data-theme="sunset"] input[type="text"], html[data-resolved-theme="sunset"] input[type="text"],
html[data-theme="forest"] input[type="text"], html[data-resolved-theme="forest"] input[type="text"],
html[data-theme="ocean"] input[type="number"], html[data-resolved-theme="ocean"] input[type="number"],
html[data-theme="sunset"] input[type="number"], html[data-resolved-theme="sunset"] input[type="number"],
html[data-theme="forest"] input[type="number"], html[data-resolved-theme="forest"] input[type="number"] { background: rgba(15, 28, 46, 0.05); }
html[data-theme="ocean"] tbody tr:hover, html[data-resolved-theme="ocean"] tbody tr:hover,
html[data-theme="sunset"] tbody tr:hover, html[data-resolved-theme="sunset"] tbody tr:hover,
html[data-theme="forest"] tbody tr:hover, html[data-resolved-theme="forest"] tbody tr:hover { background: rgba(15, 28, 46, 0.05); }
html[data-theme="ocean"] .bar, html[data-resolved-theme="ocean"] .bar,
html[data-theme="sunset"] .bar, html[data-resolved-theme="sunset"] .bar,
html[data-theme="forest"] .bar, html[data-resolved-theme="forest"] .bar { background: rgba(15, 28, 46, 0.1); }
html[data-theme="ocean"] .pill, html[data-resolved-theme="ocean"] .pill,
html[data-theme="sunset"] .pill, html[data-resolved-theme="sunset"] .pill,
html[data-theme="forest"] .pill, html[data-resolved-theme="forest"] .pill { background: rgba(15, 28, 46, 0.05); }

/* Role dashboards (faculty watchlist / admin analytics) */
.toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin-bottom: 14px; }
.toolbar select { max-width: 220px; }
.toolbar .pill { font-size: 0.82rem; padding: 9px 13px; margin-left: auto; }
.r-table { overflow-x: auto; margin-top: 4px; }
.r-table table { min-width: 720px; }
.r-table th, .r-table td { white-space: nowrap; }
td.num, th.num { text-align: right; }
td strong { font-weight: 700; }

/* Settings control (single stable point for theme + language) */
#settings-controls { position: fixed; top: 1rem; right: 1rem; z-index: 10000; }
.settings-toggle {
  display: inline-flex; align-items: center; justify-content: center;
  width: 44px; height: 44px;
  background: var(--panel-strong); color: var(--text);
  border: 1px solid var(--line); border-radius: 50%;
  font-size: 1.15rem; cursor: pointer; box-shadow: var(--shadow);
  transition: transform 0.2s ease, border-color 0.15s ease;
}
.settings-toggle:hover { transform: rotate(30deg); border-color: var(--cyan); }
.settings-panel {
  position: fixed; top: 4.4rem; right: 1rem;
  width: 300px; max-height: calc(100vh - 6rem); overflow-y: auto;
  background: var(--panel-strong); border: 1px solid var(--line); border-radius: 16px;
  box-shadow: var(--shadow); padding: 1rem; z-index: 10001; color: var(--text);
}
.set-section { margin-bottom: 1rem; }
.set-section:last-child { margin-bottom: 0; }
.set-title { font-weight: 600; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); margin-bottom: 0.5rem; }
.set-theme-menu { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.4rem; }
.set-theme-menu button {
  background: transparent; border: 1px solid var(--line); border-radius: 10px;
  padding: 0.5rem 0.25rem; cursor: pointer; color: var(--text); font-size: 0.8rem; text-align: center;
}
.set-theme-menu button.active, .set-theme-menu button:hover { border-color: var(--cyan); background: rgba(97,223,255,0.2); }
.set-lang-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 0.35rem; }
.set-lang-grid button {
  background: transparent; border: 1px solid var(--line); border-radius: 8px;
  padding: 0.45rem 0.5rem; cursor: pointer; color: var(--text); font-size: 0.8rem; text-align: left;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.set-lang-grid button.active, .set-lang-grid button:hover { border-color: var(--cyan); background: rgba(97,223,255,0.2); }
.set-link { display: block; text-align: center; margin-top: 0.75rem; font-size: 0.85rem; color: var(--cyan); text-decoration: none; }
.set-link:hover { text-decoration: underline; }
.set-promo { display: grid; gap: 0.5rem; }
.promo-link {
  display: flex; flex-direction: column; gap: 2px; text-decoration: none;
  background: rgba(255,255,255,0.03); border: 1px solid var(--line);
  border-radius: 12px; padding: 0.7rem 0.85rem; color: var(--text);
  transition: border-color 150ms ease, transform 150ms ease;
}
.promo-link:hover { border-color: var(--cyan); transform: translateY(-1px); }
.promo-link strong { font-size: 0.92rem; }
.promo-link span { color: var(--muted); font-size: 0.8rem; }
.promo-lock { color: var(--muted); font-size: 0.72rem; margin-left: 0.4rem; }
.invite-modal {
  position: fixed; inset: 0; z-index: 11000; display: flex; align-items: center; justify-content: center;
  padding: 1rem; background: rgba(4,10,20,0.72); backdrop-filter: blur(4px);
}
.invite-card {
  position: relative; width: min(400px, 100%); color: var(--text);
  background: var(--panel-strong); border: 1px solid var(--line); border-radius: 16px;
  box-shadow: var(--shadow); padding: 1.4rem;
}
.invite-card h3 { margin: 0 0 0.35rem; }
.invite-card > p { color: var(--muted); font-size: 0.88rem; margin: 0 0 0.95rem; }
.invite-close {
  position: absolute; top: 0.55rem; right: 0.55rem; background: transparent; border: none;
  color: var(--muted); font-size: 1rem; line-height: 1; cursor: pointer; padding: 0.25rem;
}
.invite-close:hover { color: var(--text); }
.invite-label { display: block; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); margin-bottom: 0.35rem; }
.invite-input {
  width: 100%; box-sizing: border-box; background: rgba(255,255,255,0.04); border: 1px solid var(--line);
  border-radius: 10px; padding: 0.65rem 0.75rem; color: var(--text); font-size: 0.95rem;
}
.invite-input:focus { outline: none; border-color: var(--cyan); }
.invite-error { color: #ff8a8a; font-size: 0.83rem; margin: 0.55rem 0 0; }
.invite-actions { display: flex; justify-content: flex-end; gap: 0.5rem; margin-top: 1.1rem; }
.invite-btn { border-radius: 10px; padding: 0.55rem 0.95rem; font-size: 0.88rem; cursor: pointer; border: 1px solid var(--line); }
.invite-btn.ghost { background: transparent; color: var(--text); }
.invite-btn.primary { background: var(--cyan); border-color: var(--cyan); color: #041018; font-weight: 600; }
.invite-btn:disabled { opacity: 0.6; cursor: default; }
.settings-view-card { width: min(560px, 100%); }
.settings-desc { margin: 0 0 1.25rem; }
.hidden { display: none !important; }
.goog-te-banner-frame, .goog-te-balloon-frame, #goog-gt-tt, .goog-te-spinner-pos,
.goog-te-gadget { display: none !important; visibility: hidden !important; }
body { top: 0 !important; }
@media (max-width: 480px) { #settings-controls { top: 0.5rem; right: 0.5rem; } .settings-panel { top: 3.9rem; right: 0.5rem; width: min(300px, calc(100vw - 1rem)); } }
</style>
</head>
<body>
<main class="shell">
  <header class="topbar panel">
    <div class="brand">
      <div class="mark"><img src="/logo.svg" alt="EduGuard logo" /></div>
      <div>
        <h1>EduGuard</h1>
        <p>Student Risk Intelligence — live dashboard · real model output on the full 10,000-student roster</p>
      </div>
    </div>
    <div class="topbar-actions">
      <div class="pill" id="updated-pill">Live data</div>
      <a class="pill topbar-link" href="/login" target="_top">Sign in</a>
    </div>
  </header>

<nav class="tabs" id="tabs" aria-label="Views"></nav>

  <!-- OVERVIEW -->
  <section class="view active" id="view-overview">
    <div class="grid" id="overview-stats"></div>
    <div class="double">
      <div class="panel chart-panel">
        <h3>Risk tier distribution</h3>
        <div class="wrap"><canvas id="chart-tier"></canvas></div>
      </div>
      <div class="panel chart-panel">
        <h3>Risk probability distribution</h3>
        <div class="wrap"><canvas id="chart-hist"></canvas></div>
      </div>
    </div>
  </section>

  <!-- FACULTY -->
  <section class="view" id="view-faculty">
    <div class="grid" id="faculty-stats"></div>
    <div class="panel" style="padding:20px">
      <div class="toolbar">
        <select id="facultyDept" aria-label="Department"></select>
        <select id="facultyRisk" aria-label="Risk tier">
          <option value="">All risk tiers</option>
          <option>High</option>
          <option>Medium</option>
        </select>
        <input type="text" id="facultySearch" placeholder="Search student ID…" autocomplete="off" />
        <span class="pill" id="faculty-count"></span>
      </div>
      <div class="r-table" id="faculty-table"></div>
    </div>
  </section>

  <!-- ADMIN -->
  <section class="view" id="view-admin">
    <div class="grid" id="admin-stats"></div>
    <div class="double">
      <div class="panel chart-panel">
        <h3>Average risk by department</h3>
        <div class="wrap"><canvas id="chart-dept"></canvas></div>
      </div>
      <div class="panel" style="padding:20px">
        <h3 style="margin:0 0 14px">Highest risk students</h3>
        <div class="r-table" id="admin-top"></div>
      </div>
    </div>
    <div class="panel" style="padding:20px">
      <h3 style="margin:0 0 14px">Department breakdown</h3>
      <div class="r-table" id="admin-dept"></div>
    </div>
  </section>

  <!-- SETTINGS -->
  <section class="view" id="view-settings">
    <div class="panel settings-view-card" style="padding:24px">
      <h3 style="margin:0 0 6px">Settings</h3>
      <p style="color:var(--muted);margin:0 0 1.25rem">Theme and language apply to all pages. Your choice is saved automatically on this device.</p>
      <div style="margin-bottom:1rem">
        <div style="font-weight:600;font-size:0.78rem;text-transform:uppercase;letter-spacing:0.05em;color:var(--muted);margin-bottom:0.5rem">Explore the platform</div>
        <div class="set-promo">
          <a class="promo-link" data-role="student" href="/login?role=student#signup" target="_top"><strong>Student</strong><span>Look up a student and get a live risk prediction</span></a>
          <a class="promo-link" data-role="faculty" data-invite="1" href="/login#signup" target="_top"><strong>Faculty<span class="promo-lock">&#128274; invite code</span></strong><span>Monitor department watchlists and at-risk students</span></a>
          <a class="promo-link" data-role="admin" data-invite="1" href="/login#signup" target="_top"><strong>Admin<span class="promo-lock">&#128274; invite code</span></strong><span>See institution-wide risk analytics</span></a>
        </div>
        <p style="color:var(--muted);font-size:0.85rem;margin:0.75rem 0 0.4rem">Enter a faculty or admin invite code to open that dashboard right here in the preview. A real account is only needed for the live app.</p>
        <a class="set-link" href="/login#signup" target="_top">Create an account for the live app</a>
      </div>
      <div style="margin-bottom:1rem">
        <div style="font-weight:600;font-size:0.78rem;text-transform:uppercase;letter-spacing:0.05em;color:var(--muted);margin-bottom:0.5rem">Theme</div>
        <div class="set-theme-menu" id="settingsThemeMenu">
          <button type="button" data-theme-opt="light">&#9728;&#65039; Light</button>
          <button type="button" data-theme-opt="dark">&#127769; Dark</button>
          <button type="button" data-theme-opt="system">&#128421;&#65039; System</button>
          <button type="button" data-theme-opt="ocean">&#128167; Ocean</button>
          <button type="button" data-theme-opt="sunset">&#127788;&#65039; Sunset</button>
          <button type="button" data-theme-opt="forest">&#127807; Forest</button>
        </div>
      </div>
      <div>
        <div style="font-weight:600;font-size:0.78rem;text-transform:uppercase;letter-spacing:0.05em;color:var(--muted);margin-bottom:0.5rem">Language</div>
        <div class="set-lang-grid" id="settingsLangGrid"></div>
      </div>
    </div>
  </section>

  <div class="footer" id="previewFooter">
    Generated from <code>student_risk_scores.csv</code> — the live output of the XGBoost pipeline on the full roster.
  </div>
</main>

<!-- Invite-code gate for the Faculty/Admin sign-up links -->
<div class="invite-modal hidden" id="inviteModal" role="dialog" aria-modal="true" aria-labelledby="inviteTitle">
  <div class="invite-card">
    <button type="button" class="invite-close" id="inviteClose" aria-label="Close">&#10005;</button>
    <h3 id="inviteTitle">Invite code</h3>
    <p id="inviteDesc">Enter your invite code to continue.</p>
    <label class="invite-label" for="inviteInput">Invite code</label>
    <input id="inviteInput" class="invite-input" type="text" autocomplete="off" spellcheck="false" placeholder="e.g. EDU-ADMIN-2026" />
    <p class="invite-error hidden" id="inviteError"></p>
    <div class="invite-actions">
      <button type="button" class="invite-btn ghost" id="inviteCancel">Cancel</button>
      <button type="button" class="invite-btn primary" id="inviteConfirm">Continue</button>
    </div>
  </div>
</div>

<script>
const DATA = /*__DATA__*/;
const records = DATA.records;
const fmt = n => Number(n).toLocaleString(undefined, { maximumFractionDigits: 1 });
const fmtPct = p => (p * 100).toFixed(1) + "%";

// Chart.js comes from a CDN. If it fails to load, `new Chart(...)` would throw
// and kill every script below it (tabs, theme, settings), so all chart
// creation goes through this guard instead.
function makeChart(canvas, config) {
  if (!window.Chart) return null;
  return new Chart(canvas, config);
}

// Charts drawn while their view is hidden measure 0x0 and stay blank after the
// view is shown (a tab switch fires no window resize), so resize them on show.
function resizeCharts(root) {
  if (!window.Chart || !Chart.getChart) return;
  root.querySelectorAll("canvas").forEach(function (canvas) {
    var chart = Chart.getChart(canvas);
    if (chart) chart.resize();
  });
}

// ---------- Overview ----------
(function () {
  const total = records.length;
  const high = records.filter(r => r.Risk_Tier === "High").length;
  const medium = records.filter(r => r.Risk_Tier === "Medium").length;
  const dropout = records.reduce((s, r) => s + r.Actual_Dropout, 0) / total;
  document.getElementById("overview-stats").innerHTML = [
    ["Students scored", fmt(total), "Full roster analysis"],
    ["High risk", fmt(high), "Immediate attention"],
    ["Medium risk", fmt(medium), "Monitor closely"],
    ["Actual dropout rate", fmtPct(dropout), "Historical ground truth"],
  ].map(([l, v, n]) => `<div class="stat"><div class="label">${l}</div><div class="value">${v}</div><div class="note">${n}</div></div>`).join("");

  makeChart(document.getElementById("chart-tier"), {
    type: "doughnut",
    data: {
      labels: ["Low", "Medium", "High"],
      datasets: [{ data: [records.filter(r => r.Risk_Tier === "Low").length, medium, high],
        backgroundColor: ["#66e3a0", "#ffcb6b", "#ff7d7d"], borderWidth: 0 }]
    },
    options: { maintainAspectRatio: false, plugins: { legend: { labels: { color: "#9bb0c9" } } }, cutout: "62%" }
  });

  const bins = Array(10).fill(0);
  records.forEach(r => { bins[Math.min(9, Math.floor(r.Risk_Probability * 10))]++; });
  makeChart(document.getElementById("chart-hist"), {
    type: "bar",
    data: {
      labels: Array.from({ length: 10 }, (_, i) => `${i * 10}–${i * 10 + 10}%`),
      datasets: [{ data: bins, backgroundColor: "rgba(97,223,255,0.7)", borderRadius: 6 }]
    },
    options: { maintainAspectRatio: false, plugins: { legend: { display: false } },
      scales: { x: { ticks: { color: "#9bb0c9" }, grid: { color: "rgba(255,255,255,0.05)" } },
                y: { ticks: { color: "#9bb0c9" }, grid: { color: "rgba(255,255,255,0.05)" } } } }
  });
})();

// ---------- Tabs ----------
var LANDING_ROLE = null;
var VIEW_LABELS = {
  overview: "Overview",
  faculty: "Faculty watchlist",
  admin: "Admin analytics",
  settings: "&#9881;&#65039; Settings",
};

function renderTabs(role) {
  var menu = role === "faculty" ? ["faculty", "overview", "settings"]
    : role === "admin" ? ["admin", "overview", "settings"]
    : ["overview", "settings"];
  document.getElementById("tabs").innerHTML = menu.map(function (v) {
    return '<button type="button" data-view="' + v + '">' + VIEW_LABELS[v] + "</button>";
  }).join("");
}

function activateView(view) {
  const target = document.getElementById("view-" + view);
  if (!target) return;
  document.querySelectorAll("#tabs button").forEach(b => b.classList.toggle("active", b.dataset.view === view));
  document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
  target.classList.add("active");
  if (view === "faculty") renderFaculty();
  if (view === "admin") renderAdmin();
  // Draw any charts that were created while this view was hidden.
  resizeCharts(target);
  if (view === "settings" && window.I18N) initPreviewSettings();
}

document.getElementById("tabs").addEventListener("click", e => {
  const btn = e.target.closest("button");
  if (!btn) return;
  activateView(btn.dataset.view);
});

// Boot: a valid invite code lands on /preview?role=faculty|admin, which opens
// that role's dashboard directly (this page renders it from the embedded
// roster, so no login is needed). The role hand-off is one-shot: the ?role=
// parameter is stripped from the URL immediately, so a later refresh always
// starts from the plain Overview + Settings view again. /preview#settings
// still deep-links too.
(function () {
  try {
    var r = String(new URLSearchParams(window.location.search).get("role") || "").toLowerCase();
    LANDING_ROLE = (r === "faculty" || r === "admin") ? r : null;
  } catch (e) { LANDING_ROLE = null; }
  if (LANDING_ROLE) {
    var pill = document.getElementById("updated-pill");
    if (pill) pill.textContent = VIEW_LABELS[LANDING_ROLE];
    var fnote = document.getElementById("previewFooter");
    if (fnote) {
      fnote.innerHTML = "Generated from <code>student_risk_scores.csv</code> — " +
        (LANDING_ROLE === "faculty" ? "faculty watchlist" : "admin analytics") +
        " rendered live from the embedded roster.";
    }
    try {
      if (window.history && history.replaceState) history.replaceState(null, "", "/preview");
    } catch (e) { /* ignore */ }
  }
  renderTabs(LANDING_ROLE);
  var requested = (window.location.hash || "").replace("#", "");
  var view = document.getElementById("view-" + requested) ? requested : (LANDING_ROLE || "overview");
  activateView(view);
})();

// Keep charts correct when the window is resized.
window.addEventListener("resize", function () { resizeCharts(document); });

function initPreviewSettings() {
  var i18n = window.I18N;
  if (!i18n || !i18n.languages) return;
  var grid = document.getElementById("settingsLangGrid");
  if (grid && grid.childElementCount === 0) {
    i18n.languages.forEach(function(pair) {
      var b = document.createElement("button");
      b.type = "button";
      b.setAttribute("data-lang", pair[0]);
      b.textContent = pair[1];
      b.addEventListener("click", function() { i18n.set(pair[0]); });
      grid.appendChild(b);
    });
  }
  syncPreviewSettings();
  document.addEventListener("i18n:change", syncPreviewSettings);
}

function syncPreviewSettings() {
  var i18n = window.I18N;
  if (!i18n) return;
  document.querySelectorAll("#settingsLangGrid [data-lang]").forEach(function(b) {
    b.classList.toggle("active", b.getAttribute("data-lang") === i18n.get());
  });
}

// bind theme buttons in settings view
document.querySelectorAll("#settingsThemeMenu [data-theme-opt]").forEach(function(b) {
  b.addEventListener("click", function() { if (window.Theme) Theme.set(b.getAttribute("data-theme-opt")); });
});
if (window.Theme) {
  // The public preview always opens in the light theme, regardless of the
  // theme preference saved from the real app or the visitor's OS scheme.
  Theme.set("light");
}

// ---------- Role dashboards (faculty watchlist / admin analytics) ----------
function tierBadge(t) {
  var c = String(t).toLowerCase();
  return '<span class="badge ' + c + '">' + t + "</span>";
}
function attendanceBar(v) {
  var color = v >= 80 ? "var(--green)" : v >= 65 ? "var(--amber)" : "var(--red)";
  return '<div class="bar" title="Attendance ' + fmt(v) + '%"><span style="width:' + Math.min(100, v) + "%;background:" + color + '"></span></div>';
}
function probBar(p) {
  return '<div class="bar"><span style="width:' + Math.round(p * 100) + '%;background:var(--cyan)"></span></div>';
}
function statCards(pairs) {
  return pairs.map(function (p) {
    return '<div class="stat"><div class="label">' + p[0] + '</div><div class="value">' + p[1] + '</div><div class="note">' + p[2] + "</div></div>";
  }).join("");
}

function renderFaculty() {
  var stats = document.getElementById("faculty-stats");
  if (stats && !stats.dataset.rendered) {
    stats.dataset.rendered = "1";
    var high = records.filter(r => r.Risk_Tier === "High").length;
    var medium = records.filter(r => r.Risk_Tier === "Medium").length;
    var avg = records.reduce((s, r) => s + r.Risk_Probability, 0) / records.length;
    stats.innerHTML = statCards([
      ["High risk", fmt(high), "Immediate attention"],
      ["Medium risk", fmt(medium), "Monitor closely"],
      ["Watchlist share", fmtPct(high / records.length), "High-risk share of roster"],
      ["Mean risk probability", fmtPct(avg), "Across all departments"],
    ]);
  }
  var deptSel = document.getElementById("facultyDept");
  if (deptSel && deptSel.childElementCount === 0) {
    deptSel.innerHTML = '<option value="">All departments</option>' +
      DATA.departments.map(function (d) { return "<option>" + d + "</option>"; }).join("");
  }
  renderFacultyTable();
}

function facultyFilters() {
  return {
    dept: document.getElementById("facultyDept").value,
    tier: document.getElementById("facultyRisk").value,
    q: String(document.getElementById("facultySearch").value || "").trim().toLowerCase(),
  };
}

function renderFacultyTable() {
  var f = facultyFilters();
  var list = records.filter(function (r) {
    if (f.dept && r.Department !== f.dept) return false;
    if (f.tier && r.Risk_Tier !== f.tier) return false;
    if (f.q && String(r.Student_ID).toLowerCase().indexOf(f.q) === -1) return false;
    return true;
  }).sort((a, b) => b.Risk_Probability - a.Risk_Probability);
  var count = document.getElementById("faculty-count");
  if (count) count.textContent = list.length + " at-risk students";
  var table = document.getElementById("faculty-table");
  if (!table) return;
  if (!list.length) { table.innerHTML = '<div class="missing">No students match these filters.</div>'; return; }
  var rows = list.slice(0, 250).map(function (r) {
    return "<tr><td><strong>" + r.Student_ID + "</strong></td><td>" + r.Department + "</td><td>" + r.Semester + "</td>" +
      "<td>" + attendanceBar(r.Attendance_Rate) + "</td><td class=\"num\">" + Number(r.GPA).toFixed(2) + "</td>" +
      '<td class="num">' + Number(r.CGPA).toFixed(2) + '</td><td class="num">' + fmtPct(r.Risk_Probability) + "</td>" +
      "<td>" + tierBadge(r.Risk_Tier) + "</td></tr>";
  });
  table.innerHTML = "<table><thead><tr>" +
    "<th>Student ID</th><th>Department</th><th>Semester</th><th>Attendance</th>" +
    '<th class="num">GPA</th><th class="num">CGPA</th><th class="num">Risk</th><th>Tier</th>' +
    "</tr></thead><tbody>" + rows.join("") + "</tbody></table>";
}

document.getElementById("facultyDept").addEventListener("change", renderFacultyTable);
document.getElementById("facultyRisk").addEventListener("change", renderFacultyTable);
document.getElementById("facultySearch").addEventListener("input", renderFacultyTable);

function renderAdmin() {
  var total = records.length;
  var high = records.filter(r => r.Risk_Tier === "High").length;
  var medium = records.filter(r => r.Risk_Tier === "Medium").length;
  var dropout = records.reduce((s, r) => s + r.Actual_Dropout, 0) / total;

  var stats = document.getElementById("admin-stats");
  if (stats && !stats.dataset.rendered) {
    stats.innerHTML = statCards([
      ["Students scored", fmt(total), "Full roster"],
      ["High risk", fmt(high), "Immediate attention"],
      ["Medium risk", fmt(medium), "Monitor closely"],
      ["Actual dropout rate", fmtPct(dropout), "Historical ground truth"],
    ]);
  }

  var depts = DATA.departments.map(function (d) {
    var list = records.filter(r => r.Department === d);
    var h = list.filter(r => r.Risk_Tier === "High").length;
    var m = list.filter(r => r.Risk_Tier === "Medium").length;
    var drop = list.reduce((s, r) => s + r.Actual_Dropout, 0) / list.length;
    var avg = list.reduce((s, r) => s + r.Risk_Probability, 0) / list.length;
    return { d: d, n: list.length, h: h, m: m, drop: drop, avg: avg };
  }).sort((a, b) => b.avg - a.avg);

  var deptTable = document.getElementById("admin-dept");
  if (deptTable) {
    deptTable.innerHTML = "<table><thead><tr>" +
      "<th>Department</th><th class=\"num\">Students</th><th class=\"num\">High</th><th class=\"num\">Medium</th>" +
      '<th class="num">Low</th><th class="num">Dropout rate</th><th>Mean risk</th></tr></thead><tbody>' +
      depts.map(function (x) {
        return "<tr><td><strong>" + x.d + "</strong></td><td class=\"num\">" + x.n + "</td><td class=\"num\">" + x.h + "</td>" +
          '<td class="num">' + x.m + '</td><td class="num">' + (x.n - x.h - x.m) + "</td>" +
          '<td class="num">' + fmtPct(x.drop) + "</td><td>" + probBar(x.avg) + "</td></tr>";
      }).join("") + "</tbody></table>";
  }

  var topTable = document.getElementById("admin-top");
  if (topTable) {
    var top = records.slice().sort((a, b) => b.Risk_Probability - a.Risk_Probability).slice(0, 20);
    topTable.innerHTML = "<table><thead><tr>" +
      "<th>Student ID</th><th>Department</th><th>Semester</th><th>Attendance</th>" +
      '<th class="num">Risk</th><th>Tier</th></tr></thead><tbody>' +
      top.map(function (r) {
        return "<tr><td><strong>" + r.Student_ID + "</strong></td><td>" + r.Department + "</td><td>" + r.Semester + "</td>" +
          "<td>" + attendanceBar(r.Attendance_Rate) + "</td><td class=\"num\">" + fmtPct(r.Risk_Probability) + "</td>" +
          "<td>" + tierBadge(r.Risk_Tier) + "</td></tr>";
      }).join("") + "</tbody></table>";
  }

  var canvas = document.getElementById("chart-dept");
  if (canvas && window.Chart && !window.__deptChart) {
    window.__deptChart = makeChart(canvas, {
      type: "bar",
      data: {
        labels: depts.map(x => x.d),
        datasets: [{ data: depts.map(x => +x.avg.toFixed(3)), backgroundColor: "rgba(102,227,160,0.7)", borderRadius: 6 }],
      },
      options: { maintainAspectRatio: false, plugins: { legend: { display: false } },
        scales: { x: { ticks: { color: "#9bb0c9" }, grid: { color: "rgba(255,255,255,0.05)" } },
                  y: { ticks: { color: "#9bb0c9" }, grid: { color: "rgba(255,255,255,0.05)" } } } },
    });
  }
}

// ---------- Invite-code gate ----------
// Faculty and Admin are gated by an invite code. A valid code opens that
// role's dashboard directly inside this preview (/preview?role=faculty|admin);
// the code is re-validated server-side before the hand-off. The sessionStorage
// hand-off below is kept for the plain Student link, which still points at the
// real sign-up page.
(function () {
  var HANDOFF_KEY = "eduguard_signup_handoff";
  var modal = document.getElementById("inviteModal");
  var modalTitle = document.getElementById("inviteTitle");
  var modalDesc = document.getElementById("inviteDesc");
  var input = document.getElementById("inviteInput");
  var error = document.getElementById("inviteError");
  var confirmBtn = document.getElementById("inviteConfirm");
  var cancelBtn = document.getElementById("inviteCancel");
  var closeBtn = document.getElementById("inviteClose");
  var activeRole = null;

  function storeHandoff(role, inviteCode) {
    try {
      sessionStorage.setItem(HANDOFF_KEY, JSON.stringify({ role: role, inviteCode: inviteCode || null }));
    } catch (e) { /* storage may be unavailable (private mode) */ }
  }

  function goToDashboard(role) {
    // A validated invite code opens that role's dashboard directly inside this
    // preview (/preview?role=faculty|admin) — no login page involved. The
    // invite code itself is never put in the URL.
    var dest = "/preview?role=" + encodeURIComponent(role);
    try { window.top.location.href = dest; }
    catch (e) { window.location.href = dest; }
  }

  function openModal(role) {
    if (!modal) { goToDashboard(role); return; }
    activeRole = role;
    modalTitle.textContent = role === "admin" ? "Admin access" : "Faculty access";
    modalDesc.textContent = role === "admin"
      ? "Enter your admin invite code to continue to the admin dashboard."
      : "Enter your faculty invite code to continue to the faculty dashboard.";
    input.value = "";
    error.textContent = "";
    error.classList.add("hidden");
    modal.classList.remove("hidden");
    document.body.style.overflow = "hidden";
    setTimeout(function () { input.focus(); }, 0);
  }

  function closeModal() {
    if (!modal) return;
    modal.classList.add("hidden");
    document.body.style.overflow = "";
    activeRole = null;
  }

  async function submitInvite() {
    var code = (input.value || "").trim();
    if (!code) {
      error.textContent = "An invite code is required for this role.";
      error.classList.remove("hidden");
      input.focus();
      return;
    }
    confirmBtn.disabled = true;
    var original = confirmBtn.textContent;
    confirmBtn.textContent = "Checking\u2026";
    var proceed = true;
    try {
      var res = await fetch("/api/auth/invite-check", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role: activeRole, invite_code: code }),
      });
      if (res.status === 403) {
        var data = await res.json().catch(function () { return {}; });
        error.textContent = data.error || "That invite code is not valid.";
        error.classList.remove("hidden");
        proceed = false;
      } else if (res.status === 400) {
        error.textContent = "This invite code cannot be used for that role.";
        error.classList.remove("hidden");
        proceed = false;
      }
      // 404/405 -> the preview is being served without the API (e.g. a static
      // build); fall through and open the demo dashboard anyway.
    } catch (e) {
      // Offline / static host: open the demo dashboard instead of blocking.
    } finally {
      confirmBtn.disabled = false;
      confirmBtn.textContent = original;
    }
    if (proceed) {
      var role = activeRole;
      closeModal();
      goToDashboard(role);
    }
  }

  document.querySelectorAll(".promo-link[data-role]").forEach(function (link) {
    link.addEventListener("click", function (event) {
      var role = link.getAttribute("data-role");
      if (link.getAttribute("data-invite") === "1") {
        event.preventDefault();
        openModal(role);
      } else {
        storeHandoff(role, null);
      }
    });
  });

  if (confirmBtn) confirmBtn.addEventListener("click", submitInvite);
  if (cancelBtn) cancelBtn.addEventListener("click", closeModal);
  if (closeBtn) closeBtn.addEventListener("click", closeModal);
  if (input) input.addEventListener("keydown", function (e) {
    if (e.key === "Enter") { e.preventDefault(); submitInvite(); }
  });
  if (modal) modal.addEventListener("click", function (e) { if (e.target === modal) closeModal(); });
})();
</script>
<script src="/js/controls.js"></script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
