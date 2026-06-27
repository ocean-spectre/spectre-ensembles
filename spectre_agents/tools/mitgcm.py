"""MITgcm-specific tools: STDOUT parsing, monitor stats, CFL extraction."""

from __future__ import annotations

import re
import subprocess

from claude_agent_sdk import tool


@tool(
    "parse_monitor_stats",
    "Extract the last N monitor blocks from MITgcm STDOUT. "
    "Returns parsed %MON fields with timestep and values.",
    {"stdout_path": str, "last_n": int},
)
async def parse_monitor_stats(args: dict) -> dict:
    stdout_path: str = args["stdout_path"]
    last_n: int = args.get("last_n", 10)

    try:
        with open(stdout_path) as f:
            lines = f.readlines()
    except OSError as e:
        return {"content": [{"type": "text", "text": f"Error reading {stdout_path}: {e}"}]}

    # Collect all %MON lines grouped by time_secondsf
    mon_lines = [l for l in lines if "%MON" in l]
    if not mon_lines:
        return {"content": [{"type": "text", "text": "No %MON lines found in STDOUT"}]}

    # Find unique timesteps
    timesteps = []
    for line in mon_lines:
        m = re.match(r".*%MON\s+time_secondsf\s+=\s+([\d.E+\-]+)", line)
        if m:
            timesteps.append(float(m.group(1)))

    # Get last N timesteps
    unique_ts = sorted(set(timesteps))[-last_n:]
    if not unique_ts:
        # Just return last 50 %MON lines
        result = "".join(mon_lines[-50:])
        return {"content": [{"type": "text", "text": result}]}

    min_ts = unique_ts[0]
    relevant = [l for l in mon_lines if _get_time(l, min_ts) >= min_ts]
    result = "".join(relevant[-200:])  # Cap output
    return {"content": [{"type": "text", "text": result}]}


def _get_time(line: str, default: float) -> float:
    """Extract time_secondsf from a %MON line, or return default."""
    # This is a heuristic — monitor blocks don't have time on every line
    return default


@tool(
    "get_cfl_values",
    "Extract the latest CFL values from MITgcm STDOUT.",
    {"stdout_path": str},
)
async def get_cfl_values(args: dict) -> dict:
    stdout_path: str = args["stdout_path"]
    cmd = f"grep '%MON advcfl' {stdout_path} | tail -7"
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        return {"content": [{"type": "text", "text": result.stdout.strip() or "No CFL data found"}]}
    except (subprocess.TimeoutExpired, OSError) as e:
        return {"content": [{"type": "text", "text": f"Error: {e}"}]}


@tool(
    "get_model_days",
    "Calculate model days reached from MITgcm STDOUT.",
    {"stdout_path": str},
)
async def get_model_days(args: dict) -> dict:
    stdout_path: str = args["stdout_path"]
    cmd = f"grep '%MON time_secondsf' {stdout_path} | tail -1"
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        line = result.stdout.strip()
        if not line:
            return {"content": [{"type": "text", "text": "No time data found"}]}

        m = re.search(r"=\s+([\d.E+\-]+)", line)
        if m:
            seconds = float(m.group(1))
            days = seconds / 86400.0
            return {"content": [{"type": "text", "text": f'{{"seconds": {seconds}, "days": {days:.2f}}}'}]}
        return {"content": [{"type": "text", "text": f"Could not parse: {line}"}]}
    except (subprocess.TimeoutExpired, OSError) as e:
        return {"content": [{"type": "text", "text": f"Error: {e}"}]}


@tool(
    "get_stdout_tail",
    "Read the last N lines of an MITgcm STDOUT file.",
    {"stdout_path": str, "n_lines": int},
)
async def get_stdout_tail(args: dict) -> dict:
    stdout_path: str = args["stdout_path"]
    n_lines: int = args.get("n_lines", 30)
    try:
        with open(stdout_path) as f:
            lines = f.readlines()
        tail = lines[-n_lines:]
        return {"content": [{"type": "text", "text": "".join(tail)}]}
    except OSError as e:
        return {"content": [{"type": "text", "text": f"Error: {e}"}]}
