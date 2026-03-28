"""
ensemble_dashboard.py
=====================
Live-updating dashboard for monitoring bred vector ensemble members.

Features:
- Multi-member STDOUT monitoring with selectable members
- Breeding cycle convergence display (per-variable RMS across cycles)
- Surface field viewer per member
- SLURM job status overview

Usage:
    python ensemble_dashboard.py <ensemble_dir> [--port 8051] [--poll 30]

    ensemble_dir: path to the ensemble/ directory containing member_NNN/ dirs
"""

import os
import sys
import re
import json
import argparse
import glob
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timedelta

# Reuse the incremental parser from monitor_dashboard
MON_PATTERN = re.compile(r'%MON\s+(\S+)\s+=\s+(\S+)')


class MemberWatcher:
    """Incrementally parse STDOUT for one ensemble member."""

    def __init__(self, member_id, stdout_path):
        self.member_id = member_id
        self.path = stdout_path
        self.records = []
        self._offset = 0
        self._current = {}

    def poll(self):
        try:
            size = os.path.getsize(self.path)
        except OSError:
            return False
        if size <= self._offset:
            return False
        new_records = 0
        with open(self.path, "r") as f:
            f.seek(self._offset)
            for line in f:
                m = MON_PATTERN.search(line)
                if not m:
                    continue
                name, val_str = m.group(1), m.group(2)
                try:
                    val = int(val_str)
                except ValueError:
                    try:
                        val = float(val_str.replace("D", "E"))
                    except ValueError:
                        continue
                if name == "time_tsnumber" and self._current:
                    self.records.append(self._current)
                    self._current = {}
                    new_records += 1
                self._current[name] = val
            self._offset = f.tell()
        return new_records > 0


# ---------------------------------------------------------------------------
# Panels (same as control dashboard)
# ---------------------------------------------------------------------------

PANELS = [
    {"title": "Sea Surface Height", "vars": ["dynstat_eta"], "unit": "m"},
    {"title": "Temperature", "vars": ["dynstat_theta"], "unit": "°C"},
    {"title": "Salinity", "vars": ["dynstat_salt"], "unit": "PSU"},
    {"title": "Zonal Velocity (U)", "vars": ["dynstat_uvel"], "unit": "m/s"},
    {"title": "Meridional Velocity (V)", "vars": ["dynstat_vvel"], "unit": "m/s"},
    {"title": "Wind Speed", "vars": ["exf_wspeed"], "unit": "m/s"},
    {"title": "Net Heat Flux", "vars": ["exf_hflux"], "unit": "W/m²"},
    {"title": "Advective CFL", "vars": ["advcfl_uvel_max", "advcfl_vvel_max", "advcfl_wvel_max"], "unit": "", "raw": True},
]

STAT_SUFFIXES = ["_max", "_mean", "_min"]


def member_records_to_traces(records, start_date):
    """Convert monitor records to Chart.js-compatible traces."""
    t0 = datetime.strptime(start_date, "%Y-%m-%d")
    times = [(t0 + timedelta(seconds=r.get("time_secondsf", 0))).isoformat() for r in records]
    all_keys = set()
    for r in records:
        all_keys.update(r.keys())

    panels_data = []
    for panel in PANELS:
        traces = []
        is_raw = panel.get("raw", False)
        if is_raw:
            for var in panel["vars"]:
                if var not in all_keys:
                    continue
                values = [r.get(var) for r in records]
                traces.append({"name": var.split("_", 1)[-1], "x": times, "y": values})
        else:
            for base_var in panel["vars"]:
                for suffix in STAT_SUFFIXES:
                    key = base_var + suffix
                    if key not in all_keys:
                        continue
                    values = [r.get(key) for r in records]
                    label = suffix.replace("_", "").capitalize()
                    traces.append({"name": label, "x": times, "y": values})
        if traces:
            panels_data.append({
                "title": f"{panel['title']} ({panel['unit']})" if panel["unit"] else panel["title"],
                "unit": panel["unit"],
                "traces": traces,
            })
    return panels_data


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

DASHBOARD_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Ensemble Monitor</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3/dist/chartjs-adapter-date-fns.bundle.min.js"></script>
<style>
  * { box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         margin: 0; padding: 16px; background: #f5f5f5; }
  h1 { margin: 0 0 8px; font-size: 20px; display: inline; }
  h2 { font-size: 15px; margin: 16px 0 8px; }
  .live { display: inline-block; width: 8px; height: 8px; border-radius: 50%;
          background: #4caf50; margin-left: 8px; animation: pulse 2s infinite; }
  @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.3; } }
  .header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
  .summary { display: flex; gap: 20px; font-size: 13px; flex-wrap: wrap; }
  .summary .item { display: flex; flex-direction: column; }
  .summary .label { color: #888; font-size: 10px; text-transform: uppercase; }
  .summary .value { font-size: 16px; font-weight: 600; }
  .section { background: #fff; border-radius: 6px; padding: 12px; margin-bottom: 12px;
             box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
  .member-select { display: flex; flex-wrap: wrap; gap: 4px; margin: 8px 0; }
  .member-select label { font-size: 11px; padding: 2px 6px; border: 1px solid #ddd;
    border-radius: 3px; cursor: pointer; user-select: none; }
  .member-select label.active { background: #2563eb; color: #fff; border-color: #2563eb; }
  .member-select label:hover { border-color: #999; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  @media (max-width: 900px) { .grid { grid-template-columns: 1fr; } }
  .chart-box { background: #fff; border-radius: 6px; padding: 8px;
               box-shadow: 0 1px 3px rgba(0,0,0,0.08); height: 250px; }
  .conv-table { width: 100%; border-collapse: collapse; font-size: 12px; }
  .conv-table th, .conv-table td { border: 1px solid #eee; padding: 4px 8px; text-align: right; }
  .conv-table th { background: #f9f9f9; font-weight: 600; }
  .conv-table td:first-child, .conv-table th:first-child { text-align: left; }
  #status { font-size: 11px; color: #888; }
  .field-viewer { text-align: center; min-height: 100px; }
  .field-viewer img { max-width: 100%; border-radius: 6px; }
  select, button { padding: 4px 8px; border-radius: 4px; border: 1px solid #ccc; font-size: 13px; }
  button { cursor: pointer; background: #2563eb; color: #fff; border: none; }
  button:hover { background: #1d4ed8; }
</style>
</head>
<body>
<div class="header">
  <div><h1>Ensemble Monitor</h1><span class="live"></span></div>
  <div id="status">connecting...</div>
</div>
<div class="summary">
  <div class="item"><span class="label">Members</span><span class="value" id="s_members">&mdash;</span></div>
  <div class="item"><span class="label">Active</span><span class="value" id="s_active">&mdash;</span></div>
  <div class="item"><span class="label">Cycle</span><span class="value" id="s_cycle">&mdash;</span></div>
  <div class="item"><span class="label">Last Update</span><span class="value" id="s_time">&mdash;</span></div>
</div>

<div class="section">
  <h2>Convergence</h2>
  <div id="conv-content"><p style="color:#888; font-size:13px;">No convergence data yet</p></div>
</div>

<div class="section">
  <h2>Member Selection</h2>
  <div style="margin-bottom:6px;">
    <button onclick="selectAll()">All</button>
    <button onclick="selectNone()">None</button>
    <button onclick="selectRange()">Range...</button>
  </div>
  <div class="member-select" id="member-select"></div>
</div>

<div class="section">
  <h2>Monitor Time Series</h2>
  <div class="grid" id="grid"></div>
</div>

<div class="section">
  <h2>Surface Fields</h2>
  <div style="display:flex; gap:10px; align-items:center; margin-bottom:8px;">
    <select id="field-member-select"></select>
    <select id="field-var-select">
      <option value="SST">SST</option>
      <option value="SSS">SSS</option>
      <option value="SSH">SSH</option>
      <option value="KE">KE</option>
    </select>
    <a href="/archive" style="font-size:12px; color:#2563eb;">All plots &rarr;</a>
  </div>
  <div class="field-viewer">
    <p id="field-msg" style="color:#888; font-size:13px;">Select a member</p>
    <img id="field-img" style="display:none;" />
  </div>
  <div id="field-slider-wrap" style="display:none; margin-top:8px;">
    <input type="range" id="field-slider" min="0" max="4" value="4" style="width:100%;" />
    <div style="display:flex; justify-content:space-between; font-size:11px; color:#888;">
      <span id="field-oldest"></span>
      <span id="field-label" style="font-weight:600; color:#333;"></span>
      <span id="field-newest"></span>
    </div>
  </div>
</div>

<script>
const POLL = POLL_INTERVAL * 1000;
const COLORS = ['#2563eb','#dc2626','#16a34a','#9333ea','#ea580c','#0891b2',
  '#4f46e5','#059669','#d97706','#7c3aed','#db2777','#0d9488',
  '#6366f1','#65a30d','#c026d3','#0284c7','#e11d48','#14b8a6'];

let allMembers = [];
let selectedMembers = new Set();
let charts = [];
let memberPlotsData = {};

// --- Member selection ---
function renderMemberSelect() {
  const el = document.getElementById('member-select');
  el.innerHTML = '';
  allMembers.forEach(m => {
    const label = document.createElement('label');
    label.textContent = m;
    label.className = selectedMembers.has(m) ? 'active' : '';
    label.onclick = () => { toggleMember(m); };
    el.appendChild(label);
  });
  // Also update field member dropdown
  const sel = document.getElementById('field-member-select');
  const prev = sel.value;
  sel.innerHTML = '';
  allMembers.forEach(m => {
    const opt = document.createElement('option');
    opt.value = m; opt.textContent = m;
    sel.appendChild(opt);
  });
  if (prev && allMembers.includes(prev)) sel.value = prev;
}
function toggleMember(m) {
  if (selectedMembers.has(m)) selectedMembers.delete(m);
  else selectedMembers.add(m);
  renderMemberSelect();
  refreshCharts();
}
function selectAll() { allMembers.forEach(m => selectedMembers.add(m)); renderMemberSelect(); refreshCharts(); }
function selectNone() { selectedMembers.clear(); renderMemberSelect(); refreshCharts(); }
function selectRange() {
  const r = prompt('Enter range (e.g. 1-10):');
  if (!r) return;
  const [a,b] = r.split('-').map(Number);
  selectedMembers.clear();
  for (let i=a; i<=b; i++) {
    const m = String(i).padStart(3,'0');
    if (allMembers.includes(m)) selectedMembers.add(m);
  }
  renderMemberSelect();
  refreshCharts();
}

// --- Charts ---
let lastData = null;
function refreshCharts() {
  if (lastData) createCharts(lastData);
}

function createCharts(data) {
  const grid = document.getElementById('grid');
  grid.innerHTML = '';
  charts = [];

  // Build unified panel list from first available member
  const memberKeys = Object.keys(data.members).filter(m => selectedMembers.has(m));
  if (memberKeys.length === 0) return;
  const refPanels = data.members[memberKeys[0]].panels;

  refPanels.forEach((panel, pi) => {
    const box = document.createElement('div');
    box.className = 'chart-box';
    const canvas = document.createElement('canvas');
    box.appendChild(canvas);
    grid.appendChild(box);

    const datasets = [];
    memberKeys.forEach((mkey, mi) => {
      const mPanels = data.members[mkey].panels;
      if (pi >= mPanels.length) return;
      const mTraces = mPanels[pi].traces;
      // Only show 'mean' trace per member to avoid clutter (or first trace for raw panels)
      const trace = mTraces.find(t => t.name.toLowerCase().includes('mean')) || mTraces[0];
      if (!trace) return;
      datasets.push({
        label: mkey,
        data: trace.x.map((t,i) => ({x: t, y: trace.y[i]})),
        borderColor: COLORS[mi % COLORS.length],
        borderWidth: 1.2,
        pointRadius: 0,
        tension: 0.2,
      });
    });

    charts.push(new Chart(canvas, {
      type: 'line',
      data: { datasets },
      options: {
        responsive: true, maintainAspectRatio: false, animation: false,
        plugins: {
          title: { display: true, text: panel.title, font: { size: 12 } },
          legend: { display: false },
        },
        scales: {
          x: { type: 'time', ticks: { font: { size: 9 } } },
          y: { title: { display: true, text: panel.unit, font: { size: 9 } }, ticks: { font: { size: 9 } } },
        },
        interaction: { mode: 'index', intersect: false },
      }
    }));
  });
}

// --- Convergence ---
function renderConvergence(conv) {
  const el = document.getElementById('conv-content');
  if (!conv || !conv.cycles || conv.cycles.length === 0) {
    el.innerHTML = '<p style="color:#888; font-size:13px;">No convergence data yet</p>';
    return;
  }
  let html = '<table class="conv-table"><tr><th>Cycle</th><th>T RMS (°C)</th><th>S RMS</th><th>U RMS (m/s)</th><th>V RMS (m/s)</th><th>Eta RMS (m)</th><th>Rescale (mean)</th></tr>';
  conv.cycles.forEach(c => {
    const members = c.members || [];
    if (members.length === 0) return;
    const avg = (key) => {
      const vals = members.map(m => m[key]).filter(v => v != null);
      return vals.length ? (vals.reduce((a,b)=>a+b,0)/vals.length) : 0;
    };
    html += '<tr>';
    html += '<td>' + c.cycle + '</td>';
    html += '<td>' + avg('Theta_rms').toFixed(5) + '</td>';
    html += '<td>' + avg('Salt_rms').toFixed(5) + '</td>';
    html += '<td>' + avg('Uvel_rms').toFixed(5) + '</td>';
    html += '<td>' + avg('Vvel_rms').toFixed(5) + '</td>';
    html += '<td>' + avg('EtaN_rms').toFixed(5) + '</td>';
    html += '<td>' + avg('rescale_factor').toFixed(3) + '</td>';
    html += '</tr>';
  });
  html += '</table>';
  document.getElementById('s_cycle').textContent = conv.cycles.length;
  el.innerHTML = html;
}

// --- Surface field viewer ---
document.getElementById('field-member-select').addEventListener('change', pollMemberPlots);
document.getElementById('field-var-select').addEventListener('change', renderMemberField);
document.getElementById('field-slider').addEventListener('input', (e) => renderMemberFieldImage(parseInt(e.target.value)));

function renderMemberField() {
  const member = document.getElementById('field-member-select').value;
  const varName = document.getElementById('field-var-select').value;
  const entries = (memberPlotsData[member] || {})[varName] || [];
  const msg = document.getElementById('field-msg');
  const img = document.getElementById('field-img');
  const wrap = document.getElementById('field-slider-wrap');
  const slider = document.getElementById('field-slider');
  if (entries.length === 0) {
    msg.style.display = 'block'; msg.textContent = 'No plots for ' + member + '/' + varName;
    img.style.display = 'none'; wrap.style.display = 'none'; return;
  }
  msg.style.display = 'none'; img.style.display = 'block';
  const recent = entries.slice(-5);
  slider.max = recent.length - 1; slider.value = recent.length - 1;
  wrap.style.display = recent.length > 1 ? 'block' : 'none';
  if (recent.length > 1) {
    document.getElementById('field-oldest').textContent = recent[0].ts;
    document.getElementById('field-newest').textContent = recent[recent.length-1].ts;
  }
  renderMemberFieldImage(recent.length - 1);
}

function renderMemberFieldImage(idx) {
  const member = document.getElementById('field-member-select').value;
  const varName = document.getElementById('field-var-select').value;
  const entries = ((memberPlotsData[member] || {})[varName] || []).slice(-5);
  if (idx >= entries.length) return;
  document.getElementById('field-img').src = '/img/' + member + '/' + entries[idx].file;
  document.getElementById('field-label').textContent = 'Step ' + entries[idx].ts;
}

async function pollMemberPlots() {
  const member = document.getElementById('field-member-select').value;
  if (!member) return;
  try {
    const r = await fetch('/plots/' + member);
    memberPlotsData[member] = await r.json();
    renderMemberField();
  } catch(e) {}
}

// --- Main poll ---
async function poll() {
  try {
    const r = await fetch('/data');
    const d = await r.json();
    lastData = d;

    // Update summary
    document.getElementById('s_members').textContent = d.n_members;
    document.getElementById('s_active').textContent = d.n_active;
    document.getElementById('s_time').textContent = d.generated.split(' ')[1];
    document.getElementById('status').textContent = 'last poll: ' + d.generated;

    // Update member list
    const newMembers = Object.keys(d.members).sort();
    if (JSON.stringify(newMembers) !== JSON.stringify(allMembers)) {
      allMembers = newMembers;
      if (selectedMembers.size === 0) {
        // Auto-select first 5
        allMembers.slice(0, 5).forEach(m => selectedMembers.add(m));
      }
      renderMemberSelect();
    }

    // Convergence
    renderConvergence(d.convergence);

    // Charts
    createCharts(d);
  } catch (e) {
    document.getElementById('status').textContent = 'error: ' + e.message;
  }
}

poll();
setInterval(poll, POLL);
setInterval(pollMemberPlots, POLL * 2);
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Scan utilities
# ---------------------------------------------------------------------------

def scan_member_plots(plots_dir):
    """Scan plots for a single member."""
    plots = {}
    for png in sorted(glob.glob(os.path.join(plots_dir, "*.png"))):
        basename = os.path.basename(png)
        parts = basename.replace(".png", "").split("_", 1)
        if len(parts) != 2:
            continue
        field, ts = parts
        plots.setdefault(field, []).append({"ts": ts, "file": basename})
    return plots


# ---------------------------------------------------------------------------
# HTTP server
# ---------------------------------------------------------------------------

class EnsembleHandler(BaseHTTPRequestHandler):
    ensemble_dir = None
    watchers = {}  # member_id → MemberWatcher
    start_date = "2002-07-01"
    poll_interval = 30
    _data_cache = None
    _cache_time = 0

    def do_GET(self):
        path = self.path.split("?")[0]

        if path == "/" or path == "/index.html":
            html = DASHBOARD_HTML.replace("POLL_INTERVAL", str(self.poll_interval))
            self._respond(200, "text/html", html.encode())

        elif path == "/data":
            self._serve_data()

        elif path.startswith("/plots/"):
            member = path.split("/")[2]
            member_dir = os.path.join(self.ensemble_dir, f"member_{member}")
            plots_dir = os.path.join(member_dir, "run", "plots")
            if os.path.isdir(plots_dir):
                plots = scan_member_plots(plots_dir)
                self._respond(200, "application/json", json.dumps(plots).encode())
            else:
                self._respond(200, "application/json", b"{}")

        elif path.startswith("/img/"):
            # /img/<member_id>/<filename>
            parts = path[5:].split("/", 1)
            if len(parts) == 2:
                member, fname = parts
                fpath = os.path.join(self.ensemble_dir, f"member_{member}", "run", "plots", fname)
                if os.path.exists(fpath) and ".." not in fname:
                    with open(fpath, "rb") as f:
                        self._respond(200, "image/png", f.read())
                    return
            self._respond(404, "text/plain", b"Not found")

        elif path.startswith("/archive"):
            self._respond(200, "text/html", b"<h1>Archive</h1><p>TODO</p>")

        else:
            self._respond(404, "text/plain", b"Not found")

    def _respond(self, code, content_type, body):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        if "json" in content_type:
            self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _serve_data(self):
        # Poll all watchers
        for w in self.watchers.values():
            w.poll()

        # Build response
        members_data = {}
        n_active = 0
        for mid, w in sorted(self.watchers.items()):
            if len(w.records) > 0:
                n_active += 1
                last = w.records[-1]
                panels = member_records_to_traces(w.records, self.start_date)
                members_data[mid] = {
                    "n_records": len(w.records),
                    "model_days": last.get("time_secondsf", 0) / 86400.0,
                    "panels": panels,
                }

        # Read convergence log
        convergence = None
        conv_path = os.path.join(self.ensemble_dir, "convergence.json")
        if os.path.exists(conv_path):
            try:
                with open(conv_path, "r") as f:
                    convergence = json.load(f)
            except Exception:
                pass

        result = {
            "n_members": len(self.watchers),
            "n_active": n_active,
            "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "convergence": convergence,
            "members": members_data,
        }
        self._respond(200, "application/json", json.dumps(result).encode())

    def log_message(self, format, *args):
        pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Ensemble monitor dashboard")
    parser.add_argument("ensemble_dir", help="Path to ensemble/ directory")
    parser.add_argument("--port", "-p", type=int, default=8051)
    parser.add_argument("--poll", type=int, default=30)
    parser.add_argument("--start-date", default="2002-07-01")
    args = parser.parse_args()

    ensemble_dir = os.path.abspath(args.ensemble_dir)

    # Discover members
    watchers = {}
    for d in sorted(glob.glob(os.path.join(ensemble_dir, "member_*/"))):
        mid = os.path.basename(d.rstrip("/")).replace("member_", "")
        # Look for STDOUT in the member's run directory
        stdout_path = os.path.join(d, "run", "STDOUT.0000")
        if not os.path.exists(stdout_path):
            stdout_path = os.path.join(d, "STDOUT.0000")
        watchers[mid] = MemberWatcher(mid, stdout_path)

    # Initial poll
    for w in watchers.values():
        w.poll()

    n_with_data = sum(1 for w in watchers.values() if len(w.records) > 0)
    print(f"Ensemble dir: {ensemble_dir}")
    print(f"Members found: {len(watchers)}, with data: {n_with_data}")

    EnsembleHandler.ensemble_dir = ensemble_dir
    EnsembleHandler.watchers = watchers
    EnsembleHandler.start_date = args.start_date
    EnsembleHandler.poll_interval = args.poll

    hostname = os.uname().nodename
    server = HTTPServer(("127.0.0.1", args.port), EnsembleHandler)
    print(f"Dashboard live at http://{hostname}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()


if __name__ == "__main__":
    main()
