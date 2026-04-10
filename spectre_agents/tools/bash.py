"""Safe subprocess execution tool with denylist and timeout."""

from __future__ import annotations

import re
import subprocess

from claude_agent_sdk import tool

# Patterns that are never allowed regardless of context
DENY_PATTERNS: list[re.Pattern] = [
    re.compile(r"\brm\s+-rf\s+/\s*$"),  # rm -rf /
    re.compile(r"\bmkfs\b"),
    re.compile(r"\bdd\s+.*of=/dev/"),
    re.compile(r"\b:(){ :\|:& };:"),  # fork bomb
    re.compile(r"\bshutdown\b"),
    re.compile(r"\breboot\b"),
    re.compile(r"\binit\s+0\b"),
]


def _check_denylist(command: str) -> str | None:
    """Return an error message if the command matches a denied pattern."""
    for pattern in DENY_PATTERNS:
        if pattern.search(command):
            return f"Command denied: matches safety pattern {pattern.pattern!r}"
    return None


@tool(
    "run_command",
    "Execute a shell command with safety checks and timeout. "
    "Returns stdout, stderr, and return code.",
    {
        "command": str,
        "cwd": str,
        "timeout": int,
    },
)
async def run_command(args: dict) -> dict:
    command: str = args["command"]
    cwd: str = args.get("cwd", ".")
    timeout: int = args.get("timeout", 120)

    denial = _check_denylist(command)
    if denial:
        return {"content": [{"type": "text", "text": denial}]}

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = {
            "stdout": result.stdout[-10000:] if len(result.stdout) > 10000 else result.stdout,
            "stderr": result.stderr[-5000:] if len(result.stderr) > 5000 else result.stderr,
            "returncode": result.returncode,
        }
        return {"content": [{"type": "text", "text": str(output)}]}
    except subprocess.TimeoutExpired:
        return {"content": [{"type": "text", "text": f"Command timed out after {timeout}s"}]}
    except OSError as e:
        return {"content": [{"type": "text", "text": f"OS error: {e}"}]}
