"""Generate a professional, self-contained HTML dashboard from real roster data."""
import json
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
ROSTER_CSV = BASE_DIR / "dataset" / "processed" / "student_risk_scores.csv"
OUTPUT_HTML = BASE_DIR / "frontend" / "dashboard_preview.html"


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
    for prefix in ("me", "fm", "am"):
        html = html.replace(f"<<{prefix.upper()}_PANEL>>", MANUAL_PANEL.replace("{{P}}", prefix))

    OUTPUT_HTML.write_text(html, encoding="utf-8")
    print(f"Wrote {OUTPUT_HTML}")


MANUAL_PANEL = r"""
    <div class="panel" style="padding:22px;margin-top:18px">
      <h3 style="margin:0 0 6px">Manual entry</h3>
      <p style="color:var(--muted);margin:0 0 16px">Enter a profile to get a live risk prediction (matched against the 10,000-student roster).</p>
      <div class="field">
        <select id="{{P}}-gender">
          <option value="Male">Male</option>
          <option value="Female">Female</option>
        </select>
        <select id="{{P}}-dept"></select>
        <select id="{{P}}-year"></select>
      </div>
      <div class="field">
        <label style="align-self:center;color:var(--muted)">Attendance %</label>
        <input type="number" id="{{P}}-att" min="0" max="100" step="0.1" placeholder="e.g. 82" style="width:110px" />
        <label style="align-self:center;color:var(--muted)">GPA</label>
        <input type="number" id="{{P}}-gpa" min="0" max="4" step="0.01" placeholder="e.g. 2.5" style="width:90px" />
        <label style="align-self:center;color:var(--muted)">CGPA</label>
        <input type="number" id="{{P}}-cgpa" min="0" max="4" step="0.01" placeholder="e.g. 2.5" style="width:90px" />
        <label style="align-self:center;color:var(--muted)">Stress (1-10)</label>
        <input type="number" id="{{P}}-stress" min="1" max="10" step="0.1" placeholder="e.g. 6" style="width:90px" />
        <button class="btn primary" id="{{P}}-go">Predict</button>
      </div>
      <div class="student-result panel hidden" id="{{P}}-result">
        <div class="result-head">
          <h3>Predicted outcome</h3>
          <span id="{{P}}-badge"></span>
        </div>
        <div style="margin-bottom:10px;color:var(--muted);font-size:0.85rem">Predicted dropout probability</div>
        <div class="bar" style="height:16px"><span id="{{P}}-bar"></span></div>
        <div style="margin:18px 0 8px;color:var(--muted);font-size:0.85rem">Recommendations</div>
        <ul id="{{P}}-recs" style="margin:0;padding-left:20px;color:var(--text);line-height:1.7"></ul>
        <div style="margin:18px 0 8px;color:var(--muted);font-size:0.85rem">Most similar students</div>
        <div style="overflow-x:auto">
          <table>
            <thead><tr><th>Student ID</th><th>Dept</th><th>Year</th><th>Attendance</th><th>GPA</th><th>Risk</th></tr></thead>
            <tbody id="{{P}}-similar"></tbody>
          </table>
        </div>
      </div>
    </div>
"""


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Student Dropout Risk — Live Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>
<script src="/js/theme.js"></script>
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
  font-weight: 900; letter-spacing: 0.04em;
}
.brand h1 { margin: 0; font-size: clamp(1rem, 2vw, 1.25rem); letter-spacing: 0.08em; text-transform: uppercase; }
.brand p { margin: 2px 0 0; color: var(--muted); font-size: 0.95rem; }
.pill {
  padding: 10px 14px; border: 1px solid var(--line); border-radius: 999px;
  color: var(--muted); background: rgba(255,255,255,0.03); white-space: nowrap;
}
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
html[data-theme="light"] {
  --bg: #eef4fb;
  --panel: rgba(255, 255, 255, 0.82);
  --panel-strong: rgba(255, 255, 255, 0.92);
  --text: #0f1c2e;
  --muted: #56708d;
  --line: rgba(15, 28, 46, 0.14);
  --shadow: 0 24px 80px rgba(30, 60, 100, 0.18);
}
html[data-theme="light"] html, html[data-theme="light"] body {
  background:
    radial-gradient(circle at top left, rgba(97,223,255,0.35), transparent 28%),
    radial-gradient(circle at 85% 15%, rgba(102,227,160,0.28), transparent 22%),
    radial-gradient(circle at 30% 80%, rgba(255,203,107,0.22), transparent 24%),
    linear-gradient(180deg, #f4f8fe 0%, #e9f1fb 56%, #f2f7fd 100%);
}
html[data-theme="light"] .topbar { background: rgba(255, 255, 255, 0.65); }
html[data-theme="light"] .tabs button,
html[data-theme="light"] .btn,
html[data-theme="light"] .meta,
html[data-theme="light"] select,
html[data-theme="light"] input[type="text"],
html[data-theme="light"] input[type="number"] { background: rgba(15, 28, 46, 0.05); }
html[data-theme="light"] tbody tr:hover { background: rgba(15, 28, 46, 0.05); }
html[data-theme="light"] .bar { background: rgba(15, 28, 46, 0.1); }
html[data-theme="light"] .pill { background: rgba(15, 28, 46, 0.05); }

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
      <div class="mark">SR</div>
      <div>
        <h1>Student Risk Intelligence</h1>
        <p>Live dashboard · real model output on the full 10,000-student roster</p>
      </div>
    </div>
    <div class="pill" id="updated-pill">Live data</div>
  </header>

<nav class="tabs" id="tabs">
    <button type="button" class="active" data-view="overview">Overview</button>
    <button type="button" data-view="student">Student</button>
    <button type="button" data-view="faculty">Faculty</button>
    <button type="button" data-view="admin">Admin</button>
    <button type="button" data-view="settings">&#9881;&#65039; Settings</button>
</nav>

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

  <!-- STUDENT -->
  <section class="view" id="view-student">
    <div class="panel" style="padding:22px">
      <h3 style="margin:0 0 6px">Student lookup</h3>
      <p style="color:var(--muted);margin:0 0 16px">Enter a student ID (1–10,000) to see their real predicted risk.</p>
      <div class="lookup">
        <input type="text" id="sid-input" placeholder="Student ID" inputmode="numeric" />
        <button class="btn primary" id="sid-go">Look up</button>
      </div>
      <div class="student-result panel hidden" id="student-result">
        <div class="result-head">
          <h3 id="sr-name"></h3>
          <span id="sr-badge"></span>
        </div>
        <div class="result-meta" id="sr-meta"></div>
        <div style="margin-bottom:10px;color:var(--muted);font-size:0.85rem">Predicted dropout probability</div>
        <div class="bar" style="height:16px"><span id="sr-bar"></span></div>
      </div>
      <div class="missing hidden" id="sr-missing">No student found with that ID.</div>
    </div>

    <div class="panel" style="padding:22px;margin-top:18px">
      <h3 style="margin:0 0 6px">Manual entry</h3>
      <p style="color:var(--muted);margin:0 0 16px">Enter a profile to get a live risk prediction (matched against the 10,000-student roster).</p>
      <div class="field">
        <select id="me-gender">
          <option value="Male">Male</option>
          <option value="Female">Female</option>
        </select>
        <select id="me-dept"></select>
        <select id="me-year"></select>
      </div>
      <div class="field">
        <label style="align-self:center;color:var(--muted)">Attendance %</label>
        <input type="number" id="me-att" min="0" max="100" step="0.1" placeholder="e.g. 82" style="width:110px" />
        <label style="align-self:center;color:var(--muted)">GPA</label>
        <input type="number" id="me-gpa" min="0" max="4" step="0.01" placeholder="e.g. 2.5" style="width:90px" />
        <label style="align-self:center;color:var(--muted)">CGPA</label>
        <input type="number" id="me-cgpa" min="0" max="4" step="0.01" placeholder="e.g. 2.5" style="width:90px" />
        <label style="align-self:center;color:var(--muted)">Stress (1-10)</label>
        <input type="number" id="me-stress" min="1" max="10" step="0.1" placeholder="e.g. 6" style="width:90px" />
        <button class="btn primary" id="me-go">Predict</button>
      </div>
      <div class="student-result panel hidden" id="me-result">
        <div class="result-head">
          <h3>Predicted outcome</h3>
          <span id="me-badge"></span>
        </div>
        <div style="margin-bottom:10px;color:var(--muted);font-size:0.85rem">Predicted dropout probability</div>
        <div class="bar" style="height:16px"><span id="me-bar"></span></div>
        <div style="margin:18px 0 8px;color:var(--muted);font-size:0.85rem">Recommendations</div>
        <ul id="me-recs" style="margin:0;padding-left:20px;color:var(--text);line-height:1.7"></ul>
        <div style="margin:18px 0 8px;color:var(--muted);font-size:0.85rem">Most similar students</div>
        <div style="overflow-x:auto">
          <table>
            <thead><tr><th>Student ID</th><th>Dept</th><th>Year</th><th>Attendance</th><th>GPA</th><th>Risk</th></tr></thead>
            <tbody id="me-similar"></tbody>
          </table>
        </div>
      </div>
    </div>
  </section>

  <!-- FACULTY -->
  <section class="view" id="view-faculty">
    <div class="panel" style="padding:22px">
      <h3 style="margin:0 0 16px">Department watchlist</h3>
      <div class="field">
        <select id="fa-dept"></select>
        <select id="fa-year"></select>
      </div>
      <div class="grid" id="fa-summary" style="margin-bottom:18px"></div>
      <div style="overflow-x:auto">
        <table>
          <thead><tr><th>Student ID</th><th>Year</th><th>Attendance %</th><th>GPA</th><th>CGPA</th><th>Stress</th><th>Risk</th><th>Tier</th></tr></thead>
          <tbody id="fa-rows"></tbody>
        </table>
      </div>
      <div class="pager">
        <span class="count" id="fa-count"></span>
        <div><button class="btn" id="fa-prev">Prev</button> <button class="btn" id="fa-next">Next</button></div>
      </div>
    </div>
    <<FM_PANEL>>
  </section>

  <!-- ADMIN -->
  <section class="view" id="view-admin">
    <div class="grid" id="admin-stats"></div>
    <div class="double">
      <div class="panel chart-panel">
        <h3>Average risk by department</h3>
        <div class="wrap"><canvas id="chart-dept"></canvas></div>
      </div>
      <div class="panel chart-panel">
        <h3>Average risk by year</h3>
        <div class="wrap"><canvas id="chart-year"></canvas></div>
      </div>
    </div>
    <<AM_PANEL>>
  </section>

  <!-- SETTINGS -->
  <section class="view" id="view-settings">
    <div class="panel settings-view-card" style="padding:24px">
      <h3 style="margin:0 0 6px">Settings</h3>
      <p style="color:var(--muted);margin:0 0 1.25rem">Theme and language apply to all pages. Your choice is saved automatically on this device.</p>
      <div style="margin-bottom:1rem">
        <div style="font-weight:600;font-size:0.78rem;text-transform:uppercase;letter-spacing:0.05em;color:var(--muted);margin-bottom:0.5rem">Theme</div>
        <div class="set-theme-menu" id="settingsThemeMenu">
          <button type="button" data-theme-opt="light">&#9728;&#65039; Light</button>
          <button type="button" data-theme-opt="dark">&#127769; Dark</button>
          <button type="button" data-theme-opt="system">&#128421;&#65039; System</button>
        </div>
      </div>
      <div>
        <div style="font-weight:600;font-size:0.78rem;text-transform:uppercase;letter-spacing:0.05em;color:var(--muted);margin-bottom:0.5rem">Language</div>
        <div class="set-lang-grid" id="settingsLangGrid"></div>
      </div>
    </div>
  </section>

  <div class="footer">
    Generated from <code>student_risk_scores.csv</code> — the live output of the XGBoost pipeline on the full roster.
  </div>
</main>

<script>
const DATA = /*__DATA__*/;
const records = DATA.records;
const byId = new Map(records.map(r => [String(r.Student_ID), r]));
const fmt = n => Number(n).toLocaleString(undefined, { maximumFractionDigits: 1 });
const fmtPct = p => (p * 100).toFixed(1) + "%";

function tierBadge(tier) {
  return `<span class="badge ${tier.toLowerCase()}">${tier}</span>`;
}
function riskBar(p, color) {
  const w = Math.round(p * 100);
  return `<div class="bar"><span style="width:${w}%;background:${color}"></span></div>`;
}
function tierColor(t) {
  return t === "High" ? "#ff7d7d" : t === "Medium" ? "#ffcb6b" : "#66e3a0";
}

// ---------- Overview ----------
(function () {
  const total = records.length;
  const high = records.filter(r => r.Risk_Tier === "High").length;
  const medium = records.filter(r => r.Risk_Tier === "Medium").length;
  const dropout = records.reduce((s, r) => s + r.Actual_Dropout, 0) / total;
  const avgRisk = records.reduce((s, r) => s + r.Risk_Probability, 0) / total;
  document.getElementById("overview-stats").innerHTML = [
    ["Students scored", fmt(total), "Full roster analysis"],
    ["High risk", fmt(high), "Immediate attention"],
    ["Medium risk", fmt(medium), "Monitor closely"],
    ["Actual dropout rate", fmtPct(dropout), "Historical ground truth"],
  ].map(([l, v, n]) => `<div class="stat"><div class="label">${l}</div><div class="value">${v}</div><div class="note">${n}</div></div>`).join("");

  new Chart(document.getElementById("chart-tier"), {
    type: "doughnut",
    data: {
      labels: ["Low", "Medium", "High"],
      datasets: [{ data: [records.filter(r => r.Risk_Tier === "Low").length, medium, high],
        backgroundColor: ["#66e3a0", "#ffcb6b", "#ff7d7d"], borderWidth: 0 }]
    },
    options: { plugins: { legend: { labels: { color: "#9bb0c9" } } }, cutout: "62%" }
  });

  const bins = Array(10).fill(0);
  records.forEach(r => { bins[Math.min(9, Math.floor(r.Risk_Probability * 10))]++; });
  new Chart(document.getElementById("chart-hist"), {
    type: "bar",
    data: {
      labels: Array.from({ length: 10 }, (_, i) => `${i * 10}–${i * 10 + 10}%`),
      datasets: [{ data: bins, backgroundColor: "rgba(97,223,255,0.7)", borderRadius: 6 }]
    },
    options: { plugins: { legend: { display: false } },
      scales: { x: { ticks: { color: "#9bb0c9" }, grid: { color: "rgba(255,255,255,0.05)" } },
                y: { ticks: { color: "#9bb0c9" }, grid: { color: "rgba(255,255,255,0.05)" } } } }
  });
})();

// ---------- Student lookup ----------
(function () {
  const input = document.getElementById("sid-input");
  const result = document.getElementById("student-result");
  const missing = document.getElementById("sr-missing");
  function lookup() {
    const r = byId.get(input.value.trim());
    missing.classList.add("hidden");
    if (!r) { result.classList.add("hidden"); missing.classList.remove("hidden"); return; }
    document.getElementById("sr-name").textContent = "Student #" + r.Student_ID;
    document.getElementById("sr-badge").innerHTML = tierBadge(r.Risk_Tier);
    document.getElementById("sr-meta").innerHTML = [
      ["Department", r.Department], ["Year", r.Semester], ["Gender", r.Gender],
      ["Attendance", fmt(r.Attendance_Rate) + "%"], ["GPA", fmt(r.GPA)],
      ["CGPA", fmt(r.CGPA)], ["Stress index", fmt(r.Stress_Index)],
      ["Actual dropout", r.Actual_Dropout ? "Yes" : "No"],
    ].map(([l, v]) => `<div class="meta"><span>${l}</span><strong>${v}</strong></div>`).join("");
    const p = r.Risk_Probability;
    document.getElementById("sr-bar").style.width = (p * 100).toFixed(1) + "%";
    document.getElementById("sr-bar").style.background = tierColor(r.Risk_Tier);
    result.classList.remove("hidden");
    result.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
  document.getElementById("sid-go").addEventListener("click", lookup);
  input.addEventListener("keydown", e => { if (e.key === "Enter") lookup(); });
})();

// ---------- Faculty ----------
(function () {
  const deptSel = document.getElementById("fa-dept");
  const yearSel = document.getElementById("fa-year");
  const tbody = document.getElementById("fa-rows");
  const PAGE = 25;
  let page = 0;

  DATA.departments.forEach(d => { const o = document.createElement("option"); o.value = d; o.textContent = d; deptSel.appendChild(o); });
  DATA.semesters.forEach(s => { const o = document.createElement("option"); o.value = s; o.textContent = s; yearSel.appendChild(o); });
  const all = document.createElement("option"); all.value = "All"; all.textContent = "All years"; yearSel.prepend(all);

  function current() {
    return records.filter(r => r.Department === deptSel.value && (yearSel.value === "All" || r.Semester === yearSel.value));
  }
  function render() {
    let rows = current().filter(r => r.Risk_Tier !== "Low").sort((a, b) => b.Risk_Probability - a.Risk_Probability);
    const allRows = rows;
    const total = rows.length;
    const pages = Math.max(1, Math.ceil(total / PAGE));
    page = Math.min(page, pages - 1);
    rows = rows.slice(page * PAGE, (page + 1) * PAGE);

    const sub = current();
    document.getElementById("fa-summary").innerHTML = [
      ["Students in filter", fmt(sub.length)],
      ["High risk", fmt(sub.filter(r => r.Risk_Tier === "High").length)],
      ["Medium risk", fmt(sub.filter(r => r.Risk_Tier === "Medium").length)],
      ["At-risk shown", fmt(Math.min(PAGE, Math.max(0, total - page * PAGE)))],
    ].map(([l, v]) => `<div class="stat"><div class="label">${l}</div><div class="value" style="font-size:1.4rem">${v}</div></div>`).join("");

    tbody.innerHTML = rows.map(r => `
      <tr>
        <td>${r.Student_ID}</td><td>${r.Semester}</td><td>${fmt(r.Attendance_Rate)}%</td>
        <td>${fmt(r.GPA)}</td><td>${fmt(r.CGPA)}</td><td>${fmt(r.Stress_Index)}</td>
        <td>${riskBar(r.Risk_Probability, tierColor(r.Risk_Tier))}</td><td>${tierBadge(r.Risk_Tier)}</td>
      </tr>`).join("") || `<tr><td colspan="8" style="text-align:center;color:var(--muted)">No at-risk students in this filter.</td></tr>`;

    document.getElementById("fa-count").textContent = `Page ${page + 1} of ${pages} · ${total} at-risk students`;
    document.getElementById("fa-prev").disabled = page === 0;
    document.getElementById("fa-next").disabled = page >= pages - 1;
    return allRows.length;
  }
  deptSel.addEventListener("change", () => { page = 0; render(); });
  yearSel.addEventListener("change", () => { page = 0; render(); });
  document.getElementById("fa-prev").addEventListener("click", () => { page--; render(); });
  document.getElementById("fa-next").addEventListener("click", () => { page++; render(); });
  render();
})();

// ---------- Admin ----------
(function () {
  const total = records.length;
  const high = records.filter(r => r.Risk_Tier === "High").length;
  const medium = records.filter(r => r.Risk_Tier === "Medium").length;
  const dropout = records.reduce((s, r) => s + r.Actual_Dropout, 0) / total;
  document.getElementById("admin-stats").innerHTML = [
    ["Total students", fmt(total), "Full roster"],
    ["Predicted dropout rate", fmtPct(records.reduce((s, r) => s + r.Risk_Probability, 0) / total), "Model estimate"],
    ["Actual dropout rate", fmtPct(dropout), "Ground truth"],
    ["Flagged (High + Medium)", fmt(high + medium), "Needs attention"],
  ].map(([l, v, n]) => `<div class="stat"><div class="label">${l}</div><div class="value">${v}</div><div class="note">${n}</div></div>`).join("");

  const deptAvg = DATA.departments.map(d => {
    const sub = records.filter(r => r.Department === d);
    return sub.reduce((s, r) => s + r.Risk_Probability, 0) / sub.length;
  });
  new Chart(document.getElementById("chart-dept"), {
    type: "bar",
    data: {
      labels: DATA.departments,
      datasets: [{ data: deptAvg.map(v => +(v * 100).toFixed(1)), backgroundColor: DATA.departments.map((_, i) =>
        ["#61dfff", "#22c7d7", "#ffcb6b", "#66e3a0", "#ff7d7d"][i % 5]), borderRadius: 8 }]
    },
    options: { plugins: { legend: { display: false } },
      scales: { x: { ticks: { color: "#9bb0c9" }, grid: { color: "rgba(255,255,255,0.05)" } },
                y: { ticks: { color: "#9bb0c9", callback: v => v + "%" }, grid: { color: "rgba(255,255,255,0.05)" } } } }
  });

  const yearAvg = DATA.semesters.map(y => {
    const sub = records.filter(r => r.Semester === y);
    return sub.reduce((s, r) => s + r.Risk_Probability, 0) / sub.length;
  });
  new Chart(document.getElementById("chart-year"), {
    type: "bar",
    data: {
      labels: DATA.semesters,
      datasets: [{ data: yearAvg.map(v => +(v * 100).toFixed(1)), backgroundColor: "rgba(255,203,107,0.75)", borderRadius: 8 }]
    },
    options: { plugins: { legend: { display: false } },
      scales: { x: { ticks: { color: "#9bb0c9" }, grid: { color: "rgba(255,255,255,0.05)" } },
                y: { ticks: { color: "#9bb0c9", callback: v => v + "%" }, grid: { color: "rgba(255,255,255,0.05)" } } } }
  });
})();

// ---------- Manual entry ----------
function initManualEntry(P) {
  const genderSel = document.getElementById(P + "-gender");
  const deptSel = document.getElementById(P + "-dept");
  const yearSel = document.getElementById(P + "-year");
  const attIn = document.getElementById(P + "-att");
  const gpaIn = document.getElementById(P + "-gpa");
  const cgpaIn = document.getElementById(P + "-cgpa");
  const stressIn = document.getElementById(P + "-stress");
  const result = document.getElementById(P + "-result");
  const FEATS = ["Attendance_Rate", "GPA", "CGPA", "Stress_Index"];
  const R = DATA.featureRange;

  DATA.departments.forEach(d => { const o = document.createElement("option"); o.value = d; o.textContent = d; deptSel.appendChild(o); });
  DATA.semesters.forEach(s => { const o = document.createElement("option"); o.value = s; o.textContent = s; yearSel.appendChild(o); });

  function recsFor(q) {
    const recs = [];
    if (q.Attendance_Rate < 75) recs.push("Attendance below 75% - flag for an advising check-in.");
    if (q.GPA < 2.0) recs.push("Low GPA - recommend tutoring / academic support referral.");
    if (q.Stress_Index >= 7) recs.push("High stress index - suggest counseling / wellness resources.");
    if (!recs.length) recs.push("No major red flags detected - continue routine monitoring.");
    return recs;
  }
  function norm(f, v) {
    const [lo, hi] = R[f];
    return hi === lo ? 0 : (v - lo) / (hi - lo);
  }
  function predict() {
    const q = {
      Gender: genderSel.value,
      Department: deptSel.value,
      Semester: yearSel.value,
      Attendance_Rate: parseFloat(attIn.value),
      GPA: parseFloat(gpaIn.value),
      CGPA: parseFloat(cgpaIn.value),
      Stress_Index: parseFloat(stressIn.value),
    };
    for (const f of FEATS) {
      if (isNaN(q[f])) { alert("Please enter a value for " + f.replace("_", " ")); return; }
    }
    const sims = records.map(r => {
      let d = 0;
      for (const f of FEATS) { const x = norm(f, q[f]) - norm(f, r[f]); d += x * x; }
      return { r, d: Math.sqrt(d) };
    }).sort((a, b) => a.d - b.d).slice(0, 30);

    const risk = sims.reduce((s, x) => s + x.r.Risk_Probability, 0) / sims.length;
    const tier = risk >= 0.5 ? "High" : risk >= 0.243 ? "Medium" : "Low";

    document.getElementById(P + "-badge").innerHTML = tierBadge(tier);
    const bar = document.getElementById(P + "-bar");
    bar.style.width = (risk * 100).toFixed(1) + "%";
    bar.style.background = tierColor(tier);
    document.getElementById(P + "-recs").innerHTML = recsFor(q).map(r => `<li>${r}</li>`).join("");
    document.getElementById(P + "-similar").innerHTML = sims.slice(0, 5).map(x => `
      <tr>
        <td>${x.r.Student_ID}</td><td>${x.r.Department}</td><td>${x.r.Semester}</td>
        <td>${fmt(x.r.Attendance_Rate)}%</td><td>${fmt(x.r.GPA)}</td>
        <td>${riskBar(x.r.Risk_Probability, tierColor(x.r.Risk_Tier))}<span style="font-size:0.78rem;color:var(--muted)">${fmtPct(x.r.Risk_Probability)}</span></td>
      </tr>`).join("");
    result.classList.remove("hidden");
    result.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
  document.getElementById(P + "-go").addEventListener("click", predict);
  [attIn, gpaIn, cgpaIn, stressIn].forEach(i => i.addEventListener("keydown", e => { if (e.key === "Enter") predict(); }));
}
initManualEntry("me");
initManualEntry("fm");
initManualEntry("am");

// ---------- Tabs ----------
document.getElementById("tabs").addEventListener("click", e => {
  const btn = e.target.closest("button");
  if (!btn) return;
  document.querySelectorAll("#tabs button").forEach(b => b.classList.toggle("active", b === btn));
  document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
  document.getElementById("view-" + btn.dataset.view).classList.add("active");
  if (btn.dataset.view === "settings" && window.I18N) initPreviewSettings();
});

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
if (window.Theme) Theme.set(Theme.get());
</script>
<script src="/js/controls.js"></script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
