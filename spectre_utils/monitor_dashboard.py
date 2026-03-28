"""
monitor_dashboard.py
====================
Live-updating MITgcm monitor dashboard.  Runs a lightweight HTTP server that
parses STDOUT.0000 on each poll and pushes updated time series to the browser.

Usage:
    python monitor_dashboard.py <path-to-STDOUT.0000> [--port 8050] [--poll 30]

Then open http://<hostname>:<port> in a browser.
"""

import re
import sys
import json
import argparse
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timedelta
from functools import lru_cache

# ---------------------------------------------------------------------------
# Human-readable panel definitions
# ---------------------------------------------------------------------------

PANELS = [
    {"title": "Sea Surface Height",  "vars": ["dynstat_eta"],    "unit": "m"},
    {"title": "Temperature",         "vars": ["dynstat_theta"],  "unit": "°C"},
    {"title": "Salinity",            "vars": ["dynstat_salt"],   "unit": "PSU"},
    {"title": "Zonal Velocity (U)",  "vars": ["dynstat_uvel"],   "unit": "m/s"},
    {"title": "Meridional Velocity (V)", "vars": ["dynstat_vvel"], "unit": "m/s"},
    {"title": "Vertical Velocity (W)", "vars": ["dynstat_wvel"], "unit": "m/s"},
    {"title": "Wind Speed",          "vars": ["exf_wspeed"],     "unit": "m/s"},
    {"title": "Wind Stress (U)",     "vars": ["exf_ustress"],    "unit": "N/m²"},
    {"title": "Wind Stress (V)",     "vars": ["exf_vstress"],    "unit": "N/m²"},
    {"title": "Net Heat Flux",       "vars": ["exf_hflux"],      "unit": "W/m²"},
    {"title": "Air Temperature (2m)","vars": ["exf_atemp"],      "unit": "K"},
    {"title": "Specific Humidity",   "vars": ["exf_aqh"],        "unit": "kg/kg"},
    {"title": "Shortwave Down",      "vars": ["exf_swdown"],     "unit": "W/m²"},
    {"title": "Longwave Down",       "vars": ["exf_lwdown"],     "unit": "W/m²"},
    {"title": "Freshwater Flux",     "vars": ["exf_evap", "exf_precip"], "unit": "m/s"},
    {"title": "Advective CFL",      "vars": ["advcfl_uvel_max", "advcfl_vvel_max", "advcfl_wvel_max", "advcfl_W_hf_max"], "unit": "", "raw": True},
    {"title": "Tracer CFL",         "vars": ["trAdv_CFL_u_max", "trAdv_CFL_v_max", "trAdv_CFL_w_max"], "unit": "", "raw": True},
]

STAT_SUFFIXES = ["_max", "_mean", "_min", "_sd"]

# ---------------------------------------------------------------------------
# Incremental parser — only reads new bytes since last poll
# ---------------------------------------------------------------------------

class StdoutWatcher:
    """Incrementally parse %MON lines from a growing STDOUT file."""

    _pattern = re.compile(r'%MON\s+(\S+)\s+=\s+(\S+)')

    def __init__(self, path):
        self.path = path
        self.records = []
        self._offset = 0
        self._current = {}
        self._json_cache = None

    def poll(self):
        """Read any new bytes appended since last call. Returns True if new records found."""
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
            self._json_cache = None  # invalidate
        return new_records > 0


def get_slurm_info(stdout_path):
    """Try to extract SLURM job info from the run environment."""
    import subprocess
    info = {}
    run_dir = os.path.dirname(stdout_path)
    sim_dir = os.path.dirname(run_dir)
    # Find the most recent job output file
    try:
        job_files = sorted(
            [f for f in os.listdir(sim_dir) if f.startswith("spectre_glorysv12_run-") and f.endswith(".out")],
            key=lambda f: os.path.getmtime(os.path.join(sim_dir, f)),
            reverse=True,
        )
        if job_files:
            job_id = job_files[0].split("-")[1].split(".")[0]
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


def records_to_json(records, start_date, slurm_info=None, wall_start=None):
    t0 = datetime.strptime(start_date, "%Y-%m-%d")
    times = []
    for r in records:
        s = r.get("time_secondsf", 0)
        times.append((t0 + timedelta(seconds=s)).isoformat())

    all_keys = set()
    for r in records:
        all_keys.update(r.keys())

    # Human-readable labels for raw CFL variables
    RAW_LABELS = {
        "advcfl_uvel_max": "U", "advcfl_vvel_max": "V",
        "advcfl_wvel_max": "W", "advcfl_W_hf_max": "W half",
        "trAdv_CFL_u_max": "U", "trAdv_CFL_v_max": "V",
        "trAdv_CFL_w_max": "W",
    }

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
                traces.append({
                    "name": label, "x": times, "y": values,
                    "mode": "lines", "visible": True,
                })
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
                    traces.append({
                        "name": label, "x": times, "y": values,
                        "mode": "lines", "line": {"dash": dash}, "visible": visible,
                    })
                if base_var in all_keys:
                    values = [r.get(base_var) for r in records]
                    if not all(v is None for v in values):
                        traces.append({"name": base_var, "x": times, "y": values, "mode": "lines"})

        if traces:
            panels_data.append({
                "title": f"{panel['title']} ({panel['unit']})" if panel["unit"] else panel["title"],
                "unit": panel["unit"],
                "traces": traces,
            })

    last = records[-1] if records else {}
    model_days = last.get("time_secondsf", 0) / 86400.0

    # Throughput: sim days per wall hour
    throughput = None
    if wall_start and model_days > 0:
        wall_hours = (datetime.now() - wall_start).total_seconds() / 3600.0
        if wall_hours > 0:
            throughput = model_days / wall_hours

    result = {
        "n_steps": last.get("time_tsnumber", 0),
        "model_days": model_days,
        "n_records": len(records),
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "throughput": round(throughput, 2) if throughput else None,
        "panels": panels_data,
    }
    if slurm_info:
        result["slurm"] = slurm_info
    return json.dumps(result)


# ---------------------------------------------------------------------------
# HTML (served once; JS polls /data for updates)
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
  .summary { display: flex; gap: 24px; font-size: 13px; }
  .summary .item { display: flex; flex-direction: column; }
  .summary .label { color: #888; font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; }
  .summary .value { font-size: 16px; font-weight: 600; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  @media (max-width: 900px) { .grid { grid-template-columns: 1fr; } }
  .chart-box { background: #fff; border-radius: 6px; padding: 10px;
               box-shadow: 0 1px 3px rgba(0,0,0,0.08); height: 270px; position: relative; }
  .chart-box canvas { width: 100% !important; height: 100% !important; }
  .footer { text-align: center; color: #aaa; font-size: 11px; margin-top: 14px; }
  #status { font-size: 11px; color: #888; }
</style>
</head>
<body>
<div class="header">
  <div><h1>MITgcm Live Monitor</h1><span class="live"></span></div>
  <div id="status">connecting...</div>
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
      <select id="field-select" style="padding:4px 8px; border-radius:4px; border:1px solid #ccc; font-size:13px;">
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

<div class="footer">Polling STDOUT.0000 every <span id="poll_s">POLL_INTERVAL</span>s</div>
<script>
const POLL = POLL_INTERVAL * 1000;
const COLORS = ['#2563eb','#dc2626','#16a34a','#9333ea','#ea580c','#0891b2'];
let charts = [];

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
      pointRadius: 0,
      tension: 0.2,
      hidden: tr.visible === 'legendonly',
    }));

    charts.push(new Chart(canvas, {
      type: 'line',
      data: { datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
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
      if (ti < chart.data.datasets.length) {
        chart.data.datasets[ti].data = tr.x.map((t, i) => ({ x: t, y: tr.y[i] }));
      }
    });
    chart.update('none');
  });
}

async function poll() {
  try {
    const r = await fetch('/data?_t=' + Date.now());
    const d = await r.json();
    document.getElementById('s_steps').textContent = d.n_steps.toLocaleString();
    document.getElementById('s_days').textContent = d.model_days.toFixed(1);
    document.getElementById('s_throughput').textContent = d.throughput ? d.throughput.toFixed(1) : '\u2014';
    document.getElementById('s_time').textContent = d.generated.split(' ')[1];
    document.getElementById('status').textContent = 'last poll: ' + d.generated;
    if (d.slurm) {
      document.getElementById('s_job').textContent = d.slurm.job_id || '\u2014';
      document.getElementById('s_state').textContent = d.slurm.state || '\u2014';
      document.getElementById('s_node').textContent = d.slurm.node || '\u2014';
      document.getElementById('s_elapsed').textContent = d.slurm.elapsed || '\u2014';
    }
    if (charts.length !== d.panels.length) {
      createCharts(d.panels);
    } else {
      updateCharts(d.panels);
    }
  } catch (e) {
    document.getElementById('status').textContent = 'error: ' + e.message;
  }
}

// --- Surface field viewer ---
let plotsData = {};
let currentField = 'SST';

document.getElementById('field-select').addEventListener('change', (e) => {
  currentField = e.target.value;
  renderFieldViewer();
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
    msg.style.display = 'block';
    msg.textContent = 'No plots available yet for ' + currentField;
    img.style.display = 'none';
    wrap.style.display = 'none';
    return;
  }

  msg.style.display = 'none';
  img.style.display = 'block';
  const recent = entries.slice(-5);
  slider.max = recent.length - 1;
  slider.value = recent.length - 1;
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
  const img = document.getElementById('field-img');
  img.src = '/img/' + e.file + '?_t=' + Date.now();
  document.getElementById('slider-label').textContent = 'Step ' + e.ts;
}

async function pollPlots() {
  try {
    const r = await fetch('/plots?_t=' + Date.now());
    plotsData = await r.json();
    renderFieldViewer();
  } catch(e) {}
}

document.getElementById('poll_s').textContent = POLL_INTERVAL;
poll();
pollPlots();
setInterval(poll, POLL);
setInterval(pollPlots, POLL * 2);
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# HTTP server
# ---------------------------------------------------------------------------

def scan_plots(plots_dir):
    """Scan plots directory and return structured metadata."""
    import glob as _glob
    plots = {}  # {field: [{ts, date, filename}, ...]}
    for png in sorted(_glob.glob(os.path.join(plots_dir, "*.png"))):
        basename = os.path.basename(png)
        # e.g. SST_0000000240.png
        parts = basename.replace(".png", "").split("_", 1)
        if len(parts) != 2:
            continue
        field, ts = parts
        plots.setdefault(field, []).append({"ts": ts, "file": basename})
    return plots


class DashboardHandler(BaseHTTPRequestHandler):
    watcher = None
    start_date = "2002-07-01"
    poll_interval = 30
    slurm_info = None
    wall_start = None
    plots_dir = None

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            html = DASHBOARD_HTML.replace("POLL_INTERVAL", str(self.poll_interval))
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode())
        elif self.path.startswith("/data"):
            try:
                w = self.watcher
                w.poll()
                if w._json_cache is None:
                    self.__class__.slurm_info = get_slurm_info(w.path)
                    w._json_cache = records_to_json(
                        w.records, self.start_date,
                        slurm_info=self.slurm_info,
                        wall_start=self.wall_start,
                    )
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(w._json_cache.encode())
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
        elif self.path.startswith("/plots"):
            # Return JSON listing of available plots
            plots = scan_plots(self.plots_dir) if self.plots_dir else {}
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(json.dumps(plots).encode())
        elif self.path.split("?")[0].startswith("/img/"):
            # Serve plot images
            fname = self.path.split("?")[0][5:]  # strip /img/ and query string
            if ".." in fname or "/" in fname:
                self.send_response(403)
                self.end_headers()
                return
            fpath = os.path.join(self.plots_dir, fname) if self.plots_dir else None
            if fpath and os.path.exists(fpath):
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Cache-Control", "public, max-age=86400")
                self.end_headers()
                with open(fpath, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_response(404)
                self.end_headers()
        elif self.path.startswith("/archive"):
            # Simple archive listing page
            plots = scan_plots(self.plots_dir) if self.plots_dir else {}
            html = self._render_archive(plots)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode())
        else:
            self.send_response(404)
            self.end_headers()

    def _render_archive(self, plots):
        rows = ""
        for field in sorted(plots.keys()):
            for p in plots[field]:
                rows += f'<tr><td>{field}</td><td>{p["ts"]}</td><td><a href="/img/{p["file"]}"><img src="/img/{p["file"]}" style="max-width:300px"></a></td></tr>\n'
        return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Plot Archive</title>
<style>body{{font-family:sans-serif;margin:20px}}table{{border-collapse:collapse}}td,th{{border:1px solid #ddd;padding:8px}}
th{{background:#f5f5f5}}a{{color:#2563eb}}img{{border-radius:4px}}</style></head>
<body><h1>Plot Archive</h1><p><a href="/">&larr; Dashboard</a></p>
<table><tr><th>Field</th><th>Timestep</th><th>Image</th></tr>{rows}</table></body></html>"""

    def log_message(self, format, *args):
        pass  # suppress access logs


def main():
    parser = argparse.ArgumentParser(description="MITgcm live monitor dashboard")
    parser.add_argument("stdout_file", help="Path to STDOUT.0000")
    parser.add_argument("--port", "-p", type=int, default=8050, help="HTTP port (default 8050)")
    parser.add_argument("--poll", type=int, default=30, help="Browser poll interval in seconds (default 30)")
    parser.add_argument("--start-date", default="2002-07-01", help="Simulation start date (YYYY-MM-DD)")
    parser.add_argument("--plots-dir", default=None, help="Directory containing surface field PNGs")
    args = parser.parse_args()

    if not os.path.exists(args.stdout_file):
        print(f"Error: {args.stdout_file} not found", file=sys.stderr)
        sys.exit(1)

    watcher = StdoutWatcher(os.path.abspath(args.stdout_file))
    watcher.poll()  # initial parse
    print(f"Initial parse: {len(watcher.records)} monitor blocks")

    DashboardHandler.watcher = watcher
    DashboardHandler.start_date = args.start_date
    DashboardHandler.poll_interval = args.poll
    # Plots directory — default to run_dir/plots
    run_dir = os.path.dirname(os.path.abspath(args.stdout_file))
    plots_dir = args.plots_dir or os.path.join(run_dir, "plots")
    os.makedirs(plots_dir, exist_ok=True)
    DashboardHandler.plots_dir = plots_dir
    print(f"Plots directory: {plots_dir}")
    slurm_info = get_slurm_info(os.path.abspath(args.stdout_file))
    DashboardHandler.slurm_info = slurm_info
    # Use SLURM job start time for throughput calculation
    wall_start = None
    if slurm_info and slurm_info.get("start"):
        try:
            wall_start = datetime.strptime(slurm_info["start"], "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            pass
    DashboardHandler.wall_start = wall_start or datetime.now()

    hostname = os.uname().nodename
    server = HTTPServer(("127.0.0.1", args.port), DashboardHandler)
    print(f"Dashboard live at http://{hostname}:{args.port}")
    print(f"Watching: {args.stdout_file}")
    print(f"Poll interval: {args.poll}s")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()


if __name__ == "__main__":
    main()
