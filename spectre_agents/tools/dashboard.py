"""Dashboard management tools: start/stop/health-check the monitoring stack."""

from __future__ import annotations

import subprocess

from claude_agent_sdk import tool


def _run(cmd: str, timeout: int = 10) -> str:
    """Run a shell command and return stdout."""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        return "(timed out)"
    except OSError as e:
        return f"(error: {e})"


@tool(
    "dashboard_health_check",
    "Check the health of all three monitoring processes (dashboard, converter, plotter) "
    "and the Tailscale proxy.",
    {},
)
async def dashboard_health_check(args: dict) -> dict:
    checks = []

    # Dashboard process
    port_check = _run("ss -tlnp | grep :8050")
    checks.append(f"Dashboard port 8050: {'LISTENING' if ':8050' in port_check else 'NOT LISTENING'}")

    # Dashboard serving data
    data_check = _run("curl -s --max-time 5 http://127.0.0.1:8050/data | head -c 100")
    checks.append(f"Dashboard data: {data_check[:80] if data_check else 'NO RESPONSE'}")

    # Tailscale
    ts_check = _run("sudo tailscale serve status 2>&1")
    checks.append(f"Tailscale: {ts_check[:80] if ts_check else 'NOT CONFIGURED'}")

    # Converter
    conv_check = _run("ps aux | grep convert_diagnostics | grep -v grep")
    checks.append(f"Converter: {'RUNNING' if conv_check else 'NOT RUNNING'}")

    # Plotter
    plot_check = _run("ps aux | grep plot_surface_fields | grep -v grep")
    checks.append(f"Plotter: {'RUNNING' if plot_check else 'NOT RUNNING'}")

    return {"content": [{"type": "text", "text": "\n".join(checks)}]}


@tool(
    "start_dashboard",
    "Start the monitoring dashboard with Tailscale proxy.",
    {"stdout_path": str, "base_dir": str, "port": int},
)
async def start_dashboard(args: dict) -> dict:
    stdout_path: str = args["stdout_path"]
    base_dir: str = args.get("base_dir", "/mnt/beegfs/spectre-150-ensembles")
    port: int = args.get("port", 8050)

    commands = [
        f"sudo tailscale serve --http={port} off 2>/dev/null",
        f"kill $(lsof -ti :{port}) 2>/dev/null",
        "sleep 1",
        f"cd {base_dir} && nohup uv run python spectre_utils/monitor_dashboard.py "
        f"{stdout_path} --port {port} --poll 30 </dev/null > /tmp/dashboard.log 2>&1 &",
        "sleep 3",
        f"sudo tailscale serve --bg --http={port} 127.0.0.1:{port}",
    ]
    cmd = " && ".join(commands)
    output = _run(cmd, timeout=30)
    return {"content": [{"type": "text", "text": f"Dashboard start sequence completed.\n{output}"}]}


@tool(
    "start_converter",
    "Start the binary-to-NetCDF converter process.",
    {"run_dir": str, "base_dir": str},
)
async def start_converter(args: dict) -> dict:
    run_dir: str = args["run_dir"]
    base_dir: str = args.get("base_dir", "/mnt/beegfs/spectre-150-ensembles")
    cmd = (
        f"cd {base_dir} && nohup uv run python spectre_utils/convert_diagnostics_to_netcdf.py "
        f"{run_dir} --poll 60 </dev/null > /tmp/converter.log 2>&1 &"
    )
    _run(cmd, timeout=10)
    return {"content": [{"type": "text", "text": "Converter started."}]}


@tool(
    "start_plotter",
    "Start the surface field plotter process.",
    {"run_dir": str, "base_dir": str},
)
async def start_plotter(args: dict) -> dict:
    run_dir: str = args["run_dir"]
    base_dir: str = args.get("base_dir", "/mnt/beegfs/spectre-150-ensembles")
    cmd = (
        f"cd {base_dir} && nohup uv run python spectre_utils/plot_surface_fields.py "
        f"{run_dir} --poll 120 </dev/null > /tmp/plotter.log 2>&1 &"
    )
    _run(cmd, timeout=10)
    return {"content": [{"type": "text", "text": "Plotter started."}]}


@tool(
    "stop_process",
    "Stop a monitoring process by name (dashboard, converter, or plotter).",
    {"process_name": str},
)
async def stop_process(args: dict) -> dict:
    name: str = args["process_name"]
    grep_patterns = {
        "dashboard": "monitor_dashboard",
        "converter": "convert_diagnostics",
        "plotter": "plot_surface_fields",
    }
    pattern = grep_patterns.get(name)
    if not pattern:
        return {"content": [{"type": "text", "text": f"Unknown process: {name}. Use: dashboard, converter, plotter"}]}

    cmd = f"pkill -f '{pattern}' 2>/dev/null"
    _run(cmd, timeout=5)

    if name == "dashboard":
        _run("sudo tailscale serve --http=8050 off 2>/dev/null", timeout=5)

    return {"content": [{"type": "text", "text": f"Stopped {name}."}]}
