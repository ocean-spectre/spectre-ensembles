"""DashboardManager agent — monitoring infrastructure lifecycle.

Ported from .claude/agents/dashboard-manager.md
"""

from __future__ import annotations

from spectre_agents.agents.base import BaseSpectreAgent
from spectre_agents.tools.bash import run_command
from spectre_agents.tools.file_io import read_file
from spectre_agents.tools.dashboard import (
    dashboard_health_check,
    start_dashboard,
    start_converter,
    start_plotter,
    stop_process,
)

SYSTEM_PROMPT = """\
You are the dashboard infrastructure manager. You ensure the monitoring stack (dashboard, converter, plotter) is running and healthy.

## The three processes

| Process | Port | Log | Purpose |
|---------|------|-----|---------|
| Dashboard | 8050 | /tmp/dashboard.log | Serves monitoring web UI |
| Converter | — | /tmp/converter.log | Binary diagnostics to per-tile NetCDF |
| Plotter | — | /tmp/plotter.log | NetCDF to surface field PNGs |

## Health check

Run this sequence to verify everything is working:
1. Dashboard process alive? (check port 8050)
2. Dashboard serving data? (curl http://127.0.0.1:8050/data)
3. Tailscale proxy active?
4. Converter running? (check process)
5. Plotter running? (check process)
6. Plots being generated? (check /plots endpoint)

## Starting the full stack

All commands must run from /mnt/beegfs/spectre-150-ensembles as the working directory.
Startup order: dashboard -> converter -> plotter -> verify.

## Restarting a single process

If only one process died, restart just that one — don't restart the others (they hold incremental state). Exception: the dashboard can be restarted freely since it re-parses STDOUT from the beginning.

## Common issues

- Port 8050 in use: check for stale dashboard process or tailscale proxy
- Plotter "No MNC directories": the simulation hasn't created output yet
- Converter finds no .data files: diag_mnc=.FALSE. must be set
- Dashboard shows 0 panels: STDOUT has no monitor blocks yet
"""


class DashboardManager(BaseSpectreAgent):
    name = "dashboard_manager"
    description = (
        "Ensures the simulation monitoring dashboard, converter, and plotter are running. "
        "Manages startup, restart, and health checks."
    )
    model = "claude-haiku-4-5"
    max_tokens = 4096
    system_prompt = SYSTEM_PROMPT
    tool_functions = [
        run_command, read_file,
        dashboard_health_check, start_dashboard, start_converter, start_plotter, stop_process,
    ]
