#!/usr/bin/env python3
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional

import dash
from dash import dcc, html, Input, Output, State
import plotly.graph_objs as go

# LocalMongo adapter (directory-based "DB")
from directorydb import LocalMongo

BASE_DIR = "monitoring"  # where mitgcm_mon_tail.py writes data
DB_CLIENT = LocalMongo(BASE_DIR)

def list_ensembles() -> List[str]:
    base = Path(BASE_DIR)
    if not base.exists():
        return []
    return [d.name for d in base.iterdir() if d.is_dir()]

def list_members(ensemble: str) -> List[str]:
    db = DB_CLIENT[ensemble]
    return db.list_collections()

def fetch_member_docs(ensemble: str, member: str) -> List[Dict[str, Any]]:
    coll = DB_CLIENT[ensemble][member]
    docs = coll.find()
    def key_fn(doc):
        # Prefer time_tsnumber, fallback to time_secondsf
        ts = doc.get("time_tsnumber")
        if not isinstance(ts, int):
            ts = doc.get("time_secondsf")
            try:
                ts = float(ts)
            except Exception:
                ts = -1.0
        scraped = doc.get("_scraped_at")
        try:
            scraped_dt = datetime.fromisoformat(str(scraped).replace("Z",""))
        except Exception:
            scraped_dt = datetime.min
        return (ts, scraped_dt)
    docs.sort(key=key_fn)
    return docs

EXCLUDED_KEYS = {"_id", "job_id", "member_id", "_scraped_at", "time_tsnumber", "time_secondsf"}

def list_all_metric_keys(ensemble: str, members: List[str]) -> List[str]:
    keys = set()
    for m in members:
        for doc in fetch_member_docs(ensemble, m):
            for k, v in doc.items():
                if k in EXCLUDED_KEYS:
                    continue
                if isinstance(v, (int, float)):
                    keys.add(k)
    return sorted(keys)

def parse_start_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    s = s.strip()
    # allow "Z"
    if s.endswith("Z"):
        s = s[:-1]
    try:
        dt = datetime.fromisoformat(s)
    except Exception:
        return None
    # make UTC-aware
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt

app = dash.Dash(__name__)
app.title = "MITgcm Monitoring Dashboard"

def serve_layout():
    ensembles = list_ensembles()
    ensemble_default = ensembles[0] if ensembles else None
    members = list_members(ensemble_default) if ensemble_default else []
    return html.Div([
        html.H2("MITgcm Monitoring Dashboard"),
        html.Div([
            html.Div([
                html.Label("Ensemble"),
                dcc.Dropdown(
                    id="ensemble-dropdown", options=[{"label": e, "value": e} for e in ensembles],
                    value=ensemble_default, clearable=False
                )
            ], style={"flex": "1", "minWidth": "220px"}),
            html.Div([
                html.Label("Members"),
                dcc.Dropdown(
                    id="member-dropdown", multi=True,
                    options=[{"label": m, "value": m} for m in members],
                    value=members[:3] if len(members) > 3 else members
                )
            ], style={"flex": "2", "minWidth": "300px"}),
            html.Div([
                html.Label("Metrics"),
                dcc.Dropdown(id="metric-dropdown", multi=True, options=[], value=[]),
            ], style={"flex": "3", "minWidth": "340px"}),
        ], style={"display": "flex", "gap": "16px", "flexWrap": "wrap"}),
        html.Hr(),
        html.Div([
            html.Div([
                html.Label("Simulation start (UTC, ISO 8601, e.g. 2025-11-07T12:00:00Z)"),
                dcc.Input(
                    id="sim-start-input",
                    type="text",
                    placeholder="YYYY-MM-DDTHH:MM:SSZ",
                    style={"width": "100%"}
                ),
                html.Div(id="sim-start-status", style={"fontSize": "12px", "color": "#666", "marginTop": "4px"}),
            ], style={"flex": "2", "minWidth": "360px"}),
            html.Div([
                html.Label("X-axis"),
                dcc.RadioItems(
                    id="x-axis-radio",
                    options=[
                        {"label": "Seconds since start (time_secondsf)", "value": "seconds"},
                        {"label": "Calendar time (requires start)", "value": "calendar"},
                    ],
                    value="seconds",
                    inline=False,
                ),
            ], style={"flex": "1", "minWidth": "320px"}),
        ], style={"display": "flex", "gap": "16px", "flexWrap": "wrap"}),
        html.Div([
            html.Button("Refresh", id="refresh-btn"),
            dcc.Interval(id="poll-interval", interval=5_000, n_intervals=0),
        ], style={"margin": "12px 0"}),
        dcc.Graph(id="metric-graph"),
        html.Div(id="debug-info", style={"fontFamily": "monospace", "fontSize": "12px", "color": "#666"}),
    ], style={"padding": "16px"})
app.layout = serve_layout

@app.callback(
    Output("member-dropdown", "options"),
    Output("member-dropdown", "value"),
    Input("ensemble-dropdown", "value"),
)
def update_members(ensemble):
    if not ensemble:
        return [], []
    members = list_members(ensemble)
    return [{"label": m, "value": m} for m in members], (members[:3] if len(members) > 3 else members)

@app.callback(
    Output("metric-dropdown", "options"),
    Output("metric-dropdown", "value"),
    Input("ensemble-dropdown", "value"),
    Input("member-dropdown", "value"),
)
def update_metrics(ensemble, members):
    if not ensemble or not members:
        return [], []
    keys = list_all_metric_keys(ensemble, members)
    return [{"label": k, "value": k} for k in keys], keys[: min(3, len(keys))]

@app.callback(
    Output("sim-start-status", "children"),
    Input("sim-start-input", "value"),
)
def check_start(value):
    if not value:
        return "No simulation start set; time axis will use seconds since start."
    dt = parse_start_iso(value)
    if dt is None:
        return "⚠️ Could not parse start datetime. Use ISO 8601, e.g. 2025-11-07T12:00:00Z"
    return f"Using start (UTC): {dt.isoformat().replace('+00:00','Z')}"

@app.callback(
    Output("metric-graph", "figure"),
    Output("debug-info", "children"),
    Input("ensemble-dropdown", "value"),
    Input("member-dropdown", "value"),
    Input("metric-dropdown", "value"),
    Input("x-axis-radio", "value"),
    Input("sim-start-input", "value"),
    Input("poll-interval", "n_intervals"),
    Input("refresh-btn", "n_clicks"),
    prevent_initial_call=False,
)
def refresh_plot(ensemble, members, metrics, xaxis, start_str, _tick, _btn):
    if not ensemble or not members or not metrics:
        return go.Figure(), "Select an ensemble, member(s), and metric(s)."
    start_dt = parse_start_iso(start_str)
    fig = go.Figure()
    trace_count = 0
    missing_secs = set()

    for member in members:
        docs = fetch_member_docs(ensemble, member)
        if not docs:
            continue
        # Build x vector from time_secondsf
        secs = []
        for doc in docs:
            val = doc.get("time_secondsf")
            try:
                secs.append(float(val))
            except Exception:
                secs.append(None)
                missing_secs.add(member)
        # Map to desired x-axis
        if xaxis == "calendar":
            if start_dt is None:
                # fallback gracefully to seconds if no start
                xs = secs
            else:
                xs = [ (start_dt + timedelta(seconds=s)).replace(tzinfo=timezone.utc) if isinstance(s, (int, float)) else None
                       for s in secs ]
        else:
            xs = secs

        # Add traces per metric per member
        for metric in metrics:
            ys = []
            for doc in docs:
                v = doc.get(metric, None)
                if isinstance(v, list) and v:
                    v = v[-1]
                ys.append(v if isinstance(v, (int, float)) else None)
            fig.add_trace(go.Scatter(
                x=xs, y=ys, mode="lines+markers",
                name=f"{member} • {metric}", hovertemplate="x=%{x}<br>y=%{y}<extra></extra>"
            ))
            trace_count += 1

    # Axis labels
    if xaxis == "calendar" and start_dt is not None:
        x_title = "simulation time (calendar UTC)"
    else:
        x_title = "time_secondsf (s since start)"

    fig.update_layout(
        height=640,
        margin=dict(l=30, r=10, t=40, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        xaxis_title=x_title,
        yaxis_title="metric value",
        hovermode="x unified",
        template="plotly_white",
        title=f"Ensemble: {ensemble}",
    )
    info = f"Rendered {trace_count} trace(s) from {len(members)} member(s)."
    if missing_secs:
        info += f" Note: some docs in members {sorted(missing_secs)} were missing time_secondsf."
    return fig, info

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8050, debug=True)
