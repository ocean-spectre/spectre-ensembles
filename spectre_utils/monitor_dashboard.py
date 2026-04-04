"""
monitor_dashboard.py
====================
Live-updating MITgcm monitor dashboard with multi-run support.

Watches a simulation directory for run subdirectories containing STDOUT.0000.
Each discovered run is selectable from a dropdown in the browser.

Usage:
    python monitor_dashboard.py <simulation_dir> [--port 8050] [--poll 30]

    simulation_dir: e.g. simulations/glorysv12-curvilinear/
"""

import re
import sys
import json
import argparse
import os
import glob
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs

# ---------------------------------------------------------------------------
# Human-readable panel definitions
# ---------------------------------------------------------------------------

PANELS = [
    # Dynamics
    {"title": "Sea Surface Height",  "vars": ["dynstat_eta"],    "unit": "m"},
    {"title": "Temperature",         "vars": ["dynstat_theta"],  "unit": "°C"},
    {"title": "Salinity",            "vars": ["dynstat_salt"],   "unit": "PSU"},
    {"title": "Zonal Velocity (U)",  "vars": ["dynstat_uvel"],   "unit": "m/s"},
    {"title": "Meridional Velocity (V)", "vars": ["dynstat_vvel"], "unit": "m/s"},
    {"title": "Vertical Velocity (W)", "vars": ["dynstat_wvel"], "unit": "m/s"},
    # Energy & vorticity
    {"title": "Kinetic Energy",      "vars": ["ke_max", "ke_mean"], "unit": "m²/s²", "raw": True},
    {"title": "Potential Energy",    "vars": ["pe_b_mean"], "unit": "m²/s²", "raw": True},
    {"title": "Vorticity (relative)","vars": ["vort_r_max", "vort_r_min"], "unit": "1/s", "raw": True},
    {"title": "Vorticity (absolute)","vars": ["vort_a_mean", "vort_a_sd"], "unit": "1/s", "raw": True},
    # Surface expansion
    {"title": "Surface Expansion",   "vars": ["surfExpan_theta_mean", "surfExpan_salt_mean"], "unit": "", "raw": True},
    # EXF forcing
    {"title": "Wind Speed",          "vars": ["exf_wspeed"],     "unit": "m/s"},
    {"title": "Wind Stress (U)",     "vars": ["exf_ustress"],    "unit": "N/m²"},
    {"title": "Wind Stress (V)",     "vars": ["exf_vstress"],    "unit": "N/m²"},
    {"title": "Net Heat Flux",       "vars": ["exf_hflux"],      "unit": "W/m²"},
    {"title": "Salt Flux",           "vars": ["exf_sflux"],      "unit": "g/m²/s"},
    {"title": "SW Flux (net)",       "vars": ["exf_swflux"],     "unit": "W/m²"},
    {"title": "LW Flux (net)",       "vars": ["exf_lwflux"],     "unit": "W/m²"},
    {"title": "Air Temperature (2m)","vars": ["exf_atemp"],      "unit": "K"},
    {"title": "Specific Humidity",   "vars": ["exf_aqh"],        "unit": "kg/kg"},
    {"title": "Shortwave Down",      "vars": ["exf_swdown"],     "unit": "W/m²"},
    {"title": "Longwave Down",       "vars": ["exf_lwdown"],     "unit": "W/m²"},
    {"title": "Freshwater Flux",     "vars": ["exf_evap", "exf_precip"], "unit": "m/s"},
    # OBC
    {"title": "OBC North Transport", "vars": ["obc_N_vVel_Int"], "unit": "m³/s", "raw": True},
    {"title": "OBC South Transport", "vars": ["obc_S_vVel_Int"], "unit": "m³/s", "raw": True},
    {"title": "OBC East Transport",  "vars": ["obc_E_uVel_Int"], "unit": "m³/s", "raw": True},
    # CFL
    {"title": "Advective CFL",      "vars": ["advcfl_uvel_max", "advcfl_vvel_max", "advcfl_wvel_max", "advcfl_W_hf_max"], "unit": "", "raw": True},
    {"title": "Tracer CFL",         "vars": ["trAdv_CFL_u_max", "trAdv_CFL_v_max", "trAdv_CFL_w_max"], "unit": "", "raw": True},
]

STAT_SUFFIXES = ["_max", "_mean", "_min", "_sd"]
RAW_LABELS = {
    "advcfl_uvel_max": "U", "advcfl_vvel_max": "V",
    "advcfl_wvel_max": "W", "advcfl_W_hf_max": "W half",
    "trAdv_CFL_u_max": "U", "trAdv_CFL_v_max": "V",
    "trAdv_CFL_w_max": "W",
}

# ---------------------------------------------------------------------------
# Incremental parser
# ---------------------------------------------------------------------------

class StdoutWatcher:
    _pattern = re.compile(r'%MON\s+(\S+)\s+=\s+(\S+)')

    def __init__(self, path):
        self.path = path
        self.records = []
        self._offset = 0
        self._current = {}
        self._json_cache = None

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
                m = self._pattern.search(line)
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
        if new_records > 0:
            self._json_cache = None
        return new_records > 0


# ---------------------------------------------------------------------------
# Run discovery
# ---------------------------------------------------------------------------

def discover_runs(simulation_dir):
    """Find subdirectories containing STDOUT.0000 (up to two levels deep)."""
    runs = []
    for d in sorted(os.listdir(simulation_dir)):
        full = os.path.join(simulation_dir, d)
        if not os.path.isdir(full):
            continue
        if os.path.exists(os.path.join(full, "STDOUT.0000")):
            runs.append(d)
        else:
            # Check one level deeper (e.g. repeat-year-50/001/)
            try:
                for sub in sorted(os.listdir(full)):
                    subfull = os.path.join(full, sub)
                    if os.path.isdir(subfull) and os.path.exists(os.path.join(subfull, "STDOUT.0000")):
                        runs.append(os.path.join(d, sub))
            except OSError:
                pass
    return runs


def get_slurm_info(run_dir):
    """Read SLURM job ID from run_dir/slurm_job_id and query sacct."""
    import subprocess
    info = {}
    try:
        job_id_file = os.path.join(run_dir, "slurm_job_id")
        if not os.path.exists(job_id_file):
            return None
        with open(job_id_file, "r") as f:
            job_id = f.read().strip()
        if not job_id:
            return None
        info["job_id"] = job_id
        result = subprocess.run(
            ["sacct", "-j", job_id, "--format=JobID,NodeList,State,Elapsed,Start", "--noheader", "-P"],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.strip().split("\n"):
            parts = line.split("|")
            if len(parts) >= 5 and "." not in parts[0]:
                info["node"] = parts[1]
                info["state"] = parts[2]
                info["elapsed"] = parts[3]
                info["start"] = parts[4]
                break
    except Exception:
        pass
    return info if info else None


# ---------------------------------------------------------------------------
# JSON builders
# ---------------------------------------------------------------------------

def records_to_json(records, start_date, slurm_info=None, wall_start=None):
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
                if all(v is None for v in values):
                    continue
                label = RAW_LABELS.get(var, var)
                traces.append({"name": label, "x": times, "y": values,
                               "mode": "lines", "visible": True})
        else:
            for base_var in panel["vars"]:
                for suffix in STAT_SUFFIXES:
                    key = base_var + suffix
                    if key not in all_keys:
                        continue
                    values = [r.get(key) for r in records]
                    if all(v is None for v in values):
                        continue
                    label = suffix.replace("_", "").capitalize()
                    if len(panel["vars"]) > 1:
                        short = base_var.split("_", 1)[-1]
                        label = f"{short} {label}"
                    dash = "solid" if "mean" in suffix else ("dash" if suffix in ("_max", "_min") else "dot")
                    visible = True if suffix in ("_max", "_mean", "_min") else "legendonly"
                    traces.append({"name": label, "x": times, "y": values,
                                   "mode": "lines", "line": {"dash": dash}, "visible": visible})
                if base_var in all_keys:
                    values = [r.get(base_var) for r in records]
                    if not all(v is None for v in values):
                        traces.append({"name": base_var, "x": times, "y": values, "mode": "lines"})
        if traces:
            panels_data.append({
                "title": f"{panel['title']} ({panel['unit']})" if panel["unit"] else panel["title"],
                "unit": panel["unit"], "traces": traces,
            })

    last = records[-1] if records else {}
    model_days = last.get("time_secondsf", 0) / 86400.0
    throughput = None
    if wall_start and model_days > 0:
        wall_hours = (datetime.now() - wall_start).total_seconds() / 3600.0
        if wall_hours > 0:
            throughput = round(model_days / wall_hours, 2)

    result = {
        "n_steps": last.get("time_tsnumber", 0),
        "model_days": model_days,
        "n_records": len(records),
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "throughput": throughput,
        "panels": panels_data,
    }
    if slurm_info:
        result["slurm"] = slurm_info
    return json.dumps(result)


def scan_plots(plots_dir):
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
# HTML
# ---------------------------------------------------------------------------

DASHBOARD_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>MITgcm Live Monitor</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3/dist/chartjs-adapter-date-fns.bundle.min.js"></script>
<style>
  * { box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         margin: 0; padding: 16px; background: #f5f5f5; }
  h1 { margin: 0 0 8px; font-size: 20px; display: inline; }
  .live { display: inline-block; width: 8px; height: 8px; border-radius: 50%;
          background: #4caf50; margin-left: 8px; animation: pulse 2s infinite; }
  @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.3; } }
  .header { display: flex; align-items: center; justify-content: space-between;
            margin-bottom: 12px; }
  .summary { display: flex; gap: 20px; font-size: 13px; flex-wrap: wrap; }
  .summary .item { display: flex; flex-direction: column; }
  .summary .label { color: #888; font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; }
  .summary .value { font-size: 16px; font-weight: 600; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  @media (max-width: 900px) { .grid { grid-template-columns: 1fr; } }
  .chart-box { background: #fff; border-radius: 6px; padding: 8px;
               box-shadow: 0 1px 3px rgba(0,0,0,0.08); height: 270px; }
  .chart-box canvas { width: 100% !important; height: 100% !important; }
  .footer { text-align: center; color: #aaa; font-size: 11px; margin-top: 14px; }
  #status { font-size: 11px; color: #888; }
  select { padding: 4px 8px; border-radius: 4px; border: 1px solid #ccc; font-size: 13px; }
</style>
</head>
<body>
<div class="header">
  <div>
    <h1>MITgcm Live Monitor</h1><span class="live"></span>
    <select id="run-select" style="margin-left:12px;" onchange="switchRun()"></select>
  </div>
  <div style="display:flex; gap:8px; align-items:center;">
    <a id="csv-link" href="/csv" style="font-size:11px; color:#2563eb; text-decoration:none;">Download CSV</a>
    <span id="status">connecting...</span>
  </div>
</div>
<div class="summary">
  <div class="item"><span class="label">Job</span><span class="value" id="s_job">&mdash;</span></div>
  <div class="item"><span class="label">State</span><span class="value" id="s_state">&mdash;</span></div>
  <div class="item"><span class="label">Node</span><span class="value" id="s_node">&mdash;</span></div>
  <div class="item"><span class="label">Timesteps</span><span class="value" id="s_steps">&mdash;</span></div>
  <div class="item"><span class="label">Model Days</span><span class="value" id="s_days">&mdash;</span></div>
  <div class="item"><span class="label">Sim Days / Wall Hr</span><span class="value" id="s_throughput">&mdash;</span></div>
  <div class="item"><span class="label">Wall Time</span><span class="value" id="s_elapsed">&mdash;</span></div>
  <div class="item"><span class="label">Last Update</span><span class="value" id="s_time">&mdash;</span></div>
</div>
<div class="grid" id="grid"></div>

<div style="margin-top:16px; background:#fff; border-radius:6px; padding:14px; box-shadow:0 1px 3px rgba(0,0,0,0.08);">
  <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:10px;">
    <h2 style="margin:0; font-size:16px;">Surface Fields</h2>
    <div style="display:flex; gap:10px; align-items:center;">
      <select id="field-select">
        <option value="SST">Sea Surface Temperature</option>
        <option value="SSS">Sea Surface Salinity</option>
        <option value="SSH">Sea Surface Height</option>
        <option value="KE">Surface Kinetic Energy</option>
      </select>
      <a href="/archive" style="font-size:12px; color:#2563eb;">All plots &rarr;</a>
    </div>
  </div>
  <div id="field-viewer" style="text-align:center; min-height:100px;">
    <p id="field-msg" style="color:#888; font-size:13px;">No plots available yet</p>
    <img id="field-img" style="max-width:100%; border-radius:6px; display:none;" />
  </div>
  <div id="slider-wrap" style="display:none; margin-top:8px;">
    <input type="range" id="time-slider" min="0" max="4" value="4" style="width:100%;" />
    <div style="display:flex; justify-content:space-between; font-size:11px; color:#888;">
      <span id="slider-oldest"></span>
      <span id="slider-label" style="font-weight:600; color:#333;"></span>
      <span id="slider-newest"></span>
    </div>
  </div>
</div>

<div class="footer">Polling every <span id="poll_s">POLL_INTERVAL</span>s</div>
<script>
const POLL = POLL_INTERVAL * 1000;
const COLORS = ['#2563eb','#dc2626','#16a34a','#9333ea','#ea580c','#0891b2'];
let charts = [];
let plotsData = {};
let currentField = 'SST';
let currentRun = '';

// --- Run selector ---
async function loadRuns() {
  try {
    const r = await fetch('/runs');
    const runs = await r.json();
    const sel = document.getElementById('run-select');
    const prev = currentRun;
    sel.innerHTML = '';
    runs.forEach(name => {
      const opt = document.createElement('option');
      opt.value = name; opt.textContent = name;
      if (name === prev) opt.selected = true;
      sel.appendChild(opt);
    });
    if (!currentRun && runs.length > 0) {
      currentRun = runs[runs.length - 1]; // default to latest
      sel.value = currentRun;
    }
  } catch(e) {}
}
function switchRun() {
  currentRun = document.getElementById('run-select').value;
  charts = []; // force chart rebuild
  document.getElementById('grid').innerHTML = '';
  document.getElementById('csv-link').href = '/csv?run=' + encodeURIComponent(currentRun);
  poll();
  pollPlots();
}

// --- Charts ---
function makeDash(suffix) {
  if (suffix.includes('mean')) return [];
  if (suffix.includes('max') || suffix.includes('min')) return [6, 3];
  return [2, 2];
}
function createCharts(panels) {
  const grid = document.getElementById('grid');
  grid.innerHTML = '';
  charts = [];
  panels.forEach((p, pi) => {
    const box = document.createElement('div');
    box.className = 'chart-box';
    const canvas = document.createElement('canvas');
    box.appendChild(canvas);
    grid.appendChild(box);
    const datasets = p.traces.map((tr, ti) => ({
      label: tr.name,
      data: tr.x.map((t, i) => ({ x: t, y: tr.y[i] })),
      borderColor: COLORS[ti % COLORS.length],
      borderWidth: tr.name.includes('Mean') || tr.name.includes('mean') ? 2 : 1.2,
      borderDash: makeDash(tr.name),
      pointRadius: 0, tension: 0.2,
      hidden: tr.visible === 'legendonly',
    }));
    charts.push(new Chart(canvas, {
      type: 'line', data: { datasets },
      options: {
        responsive: true, maintainAspectRatio: false, animation: false,
        plugins: {
          title: { display: true, text: p.title, font: { size: 13 } },
          legend: { position: 'bottom', labels: { boxWidth: 14, font: { size: 10 } } },
        },
        scales: {
          x: { type: 'time', time: { tooltipFormat: 'MMM d HH:mm' }, ticks: { font: { size: 10 } } },
          y: { title: { display: true, text: p.unit, font: { size: 10 } }, ticks: { font: { size: 10 } } },
        },
        interaction: { mode: 'index', intersect: false },
      }
    }));
  });
}
function updateCharts(panels) {
  panels.forEach((p, pi) => {
    if (pi >= charts.length) return;
    const chart = charts[pi];
    p.traces.forEach((tr, ti) => {
      if (ti < chart.data.datasets.length)
        chart.data.datasets[ti].data = tr.x.map((t, i) => ({ x: t, y: tr.y[i] }));
    });
    chart.update('none');
  });
}

// --- Surface field viewer ---
document.getElementById('field-select').addEventListener('change', (e) => {
  currentField = e.target.value; renderFieldViewer();
});
document.getElementById('time-slider').addEventListener('input', (e) => {
  renderFieldImage(parseInt(e.target.value));
});
function renderFieldViewer() {
  const entries = plotsData[currentField] || [];
  const msg = document.getElementById('field-msg');
  const img = document.getElementById('field-img');
  const wrap = document.getElementById('slider-wrap');
  const slider = document.getElementById('time-slider');
  if (entries.length === 0) {
    msg.style.display = 'block'; msg.textContent = 'No plots available yet for ' + currentField;
    img.style.display = 'none'; wrap.style.display = 'none'; return;
  }
  msg.style.display = 'none'; img.style.display = 'block';
  const recent = entries.slice(-5);
  slider.max = recent.length - 1; slider.value = recent.length - 1;
  wrap.style.display = recent.length > 1 ? 'block' : 'none';
  if (recent.length > 1) {
    document.getElementById('slider-oldest').textContent = recent[0].ts;
    document.getElementById('slider-newest').textContent = recent[recent.length-1].ts;
  }
  renderFieldImage(recent.length - 1);
}
function renderFieldImage(idx) {
  const entries = (plotsData[currentField] || []).slice(-5);
  if (idx >= entries.length) return;
  const e = entries[idx];
  document.getElementById('field-img').src = '/img/' + currentRun + '/' + e.file;
  document.getElementById('slider-label').textContent = 'Step ' + e.ts;
}

// --- Polling ---
async function poll() {
  try {
    const r = await fetch('/data?run=' + encodeURIComponent(currentRun));
    const d = await r.json();
    document.getElementById('s_steps').textContent = d.n_steps.toLocaleString();
    document.getElementById('s_days').textContent = d.model_days.toFixed(1);
    document.getElementById('s_throughput').textContent = d.throughput ? d.throughput.toFixed(1) : '\\u2014';
    document.getElementById('s_time').textContent = d.generated.split(' ')[1];
    document.getElementById('status').textContent = 'last poll: ' + d.generated;
    if (d.slurm) {
      document.getElementById('s_job').textContent = d.slurm.job_id || '\\u2014';
      document.getElementById('s_state').textContent = d.slurm.state || '\\u2014';
      document.getElementById('s_node').textContent = d.slurm.node || '\\u2014';
      document.getElementById('s_elapsed').textContent = d.slurm.elapsed || '\\u2014';
    }
    if (charts.length !== d.panels.length) { createCharts(d.panels); }
    else { updateCharts(d.panels); }
  } catch (e) {
    document.getElementById('status').textContent = 'error: ' + e.message;
  }
}
async function pollPlots() {
  try {
    const r = await fetch('/plots?run=' + encodeURIComponent(currentRun));
    plotsData = await r.json();
    renderFieldViewer();
  } catch(e) {}
}

document.getElementById('poll_s').textContent = POLL_INTERVAL;
loadRuns().then(() => { poll(); pollPlots(); });
setInterval(poll, POLL);
setInterval(pollPlots, POLL * 2);
setInterval(loadRuns, POLL * 10); // refresh run list occasionally
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# HTTP server
# ---------------------------------------------------------------------------

class DashboardHandler(BaseHTTPRequestHandler):
    simulation_dir = None
    watchers = {}       # run_name → StdoutWatcher
    start_date = "2002-07-01"
    poll_interval = 30

    def _get_run(self):
        """Extract run= query param, default to latest."""
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        run = params.get("run", [None])[0]
        if not run:
            runs = discover_runs(self.simulation_dir)
            run = runs[-1] if runs else None
        return run

    def _get_watcher(self, run_name):
        """Get or create a watcher for the given run."""
        if run_name not in self.watchers:
            stdout_path = os.path.join(self.simulation_dir, run_name, "STDOUT.0000")
            if os.path.exists(stdout_path):
                w = StdoutWatcher(stdout_path)
                w.poll()
                self.watchers[run_name] = w
        return self.watchers.get(run_name)

    def _respond(self, code, content_type, body):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        if "json" in content_type:
            self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body if isinstance(body, bytes) else body.encode())

    def do_GET(self):
        path = self.path.split("?")[0]

        if path == "/" or path == "/index.html":
            html = DASHBOARD_HTML.replace("POLL_INTERVAL", str(self.poll_interval))
            self._respond(200, "text/html; charset=utf-8", html.encode())

        elif path == "/runs":
            runs = discover_runs(self.simulation_dir)
            self._respond(200, "application/json", json.dumps(runs).encode())

        elif path.startswith("/data"):
            run = self._get_run()
            if not run:
                self._respond(200, "application/json", json.dumps({"n_steps": 0, "model_days": 0, "n_records": 0, "generated": "", "panels": []}).encode())
                return
            w = self._get_watcher(run)
            if not w:
                self._respond(200, "application/json", json.dumps({"n_steps": 0, "model_days": 0, "n_records": 0, "generated": "", "panels": []}).encode())
                return
            w.poll()
            if w._json_cache is None:
                run_path = os.path.join(self.simulation_dir, run)
                slurm_info = get_slurm_info(run_path)
                wall_start = None
                if slurm_info and slurm_info.get("start"):
                    try:
                        wall_start = datetime.strptime(slurm_info["start"], "%Y-%m-%dT%H:%M:%S")
                    except ValueError:
                        pass
                w._json_cache = records_to_json(w.records, self.start_date,
                                                 slurm_info=slurm_info, wall_start=wall_start)
            self._respond(200, "application/json", w._json_cache.encode())

        elif path.startswith("/plots"):
            run = self._get_run()
            if run:
                plots_dir = os.path.join(self.simulation_dir, run, "plots")
                plots = scan_plots(plots_dir) if os.path.isdir(plots_dir) else {}
            else:
                plots = {}
            self._respond(200, "application/json", json.dumps(plots).encode())

        elif path.startswith("/csv"):
            run = self._get_run()
            w = self._get_watcher(run) if run else None
            if w:
                w.poll()
                csv = self._build_csv(w.records, run)
                self.send_response(200)
                self.send_header("Content-Type", "text/csv")
                self.send_header("Content-Disposition", f'attachment; filename="monitor_{run}.csv"')
                self.end_headers()
                self.wfile.write(csv.encode())
            else:
                self._respond(404, "text/plain", b"No data")

        elif path.startswith("/img/"):
            # /img/<run_name>/<filename>
            parts = path[5:].split("/", 1)
            if len(parts) == 2:
                run_name, fname = parts
                if ".." not in fname:
                    fpath = os.path.join(self.simulation_dir, run_name, "plots", fname)
                    if os.path.exists(fpath):
                        self.send_response(200)
                        self.send_header("Content-Type", "image/png")
                        self.send_header("Cache-Control", "public, max-age=86400")
                        self.end_headers()
                        with open(fpath, "rb") as f:
                            self.wfile.write(f.read())
                        return
            self._respond(404, "text/plain", b"Not found")

        elif path.startswith("/archive"):
            run = self._get_run()
            plots_dir = os.path.join(self.simulation_dir, run, "plots") if run else ""
            plots = scan_plots(plots_dir) if os.path.isdir(plots_dir) else {}
            rows = ""
            for field in sorted(plots.keys()):
                for p in plots[field]:
                    img_url = f"/img/{run}/{p['file']}"
                    rows += f'<tr><td>{field}</td><td>{p["ts"]}</td><td><a href="{img_url}"><img src="{img_url}" style="max-width:300px"></a></td></tr>\n'
            html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Plot Archive — {run}</title>
<style>body{{font-family:sans-serif;margin:20px}}table{{border-collapse:collapse}}td,th{{border:1px solid #ddd;padding:8px}}
th{{background:#f5f5f5}}a{{color:#2563eb}}img{{border-radius:4px}}</style></head>
<body><h1>Plot Archive — {run}</h1><p><a href="/">&larr; Dashboard</a></p>
<table><tr><th>Field</th><th>Timestep</th><th>Image</th></tr>{rows}</table></body></html>"""
            self._respond(200, "text/html; charset=utf-8", html.encode())

        else:
            self._respond(404, "text/plain", b"Not found")

    def _build_csv(self, records, run_name):
        """Build CSV string from monitor records."""
        if not records:
            return ""
        # Collect all keys across all records
        all_keys = set()
        for r in records:
            all_keys.update(r.keys())
        # Add model_date column
        t0 = datetime.strptime(self.start_date, "%Y-%m-%d")
        cols = ["model_date"] + sorted(all_keys)
        lines = [",".join(cols)]
        for r in records:
            date = (t0 + timedelta(seconds=r.get("time_secondsf", 0))).strftime("%Y-%m-%d %H:%M")
            vals = [date] + [str(r.get(k, "")) for k in sorted(all_keys)]
            lines.append(",".join(vals))
        return "\n".join(lines)

    def log_message(self, format, *args):
        pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="MITgcm live monitor dashboard")
    parser.add_argument("simulation_dir", help="Path to simulation directory (e.g. simulations/glorysv12-curvilinear/)")
    parser.add_argument("--port", "-p", type=int, default=8050)
    parser.add_argument("--poll", type=int, default=30)
    parser.add_argument("--start-date", default="2002-07-01")
    args = parser.parse_args()

    simulation_dir = os.path.abspath(args.simulation_dir)
    if not os.path.isdir(simulation_dir):
        print(f"Error: {simulation_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    runs = discover_runs(simulation_dir)
    print(f"Simulation directory: {simulation_dir}")
    print(f"Discovered runs: {runs}")

    DashboardHandler.simulation_dir = simulation_dir
    DashboardHandler.start_date = args.start_date
    DashboardHandler.poll_interval = args.poll

    hostname = os.uname().nodename
    server = HTTPServer(("127.0.0.1", args.port), DashboardHandler)
    print(f"Dashboard live at http://{hostname}:{args.port}")
    print(f"Poll interval: {args.poll}s")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()


if __name__ == "__main__":
    main()
