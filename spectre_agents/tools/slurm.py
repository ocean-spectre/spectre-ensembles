"""SLURM job management tools: submit, status, queue, cancel."""

from __future__ import annotations

import re
import subprocess

from claude_agent_sdk import tool


@tool(
    "submit_job",
    "Submit a SLURM job via sbatch. Returns job ID.",
    {"script": str, "chdir": str},
)
async def submit_job(args: dict) -> dict:
    script: str = args["script"]
    chdir: str = args.get("chdir", ".")

    cmd = f"sbatch --chdir={chdir} {script}"
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return {"content": [{"type": "text", "text": f"sbatch failed: {result.stderr}"}]}

        # Parse "Submitted batch job 12345"
        match = re.search(r"Submitted batch job (\d+)", result.stdout)
        if match:
            job_id = int(match.group(1))
            return {"content": [{"type": "text", "text": f'{{"job_id": {job_id}, "submitted": true}}'}]}
        return {"content": [{"type": "text", "text": f"Unexpected sbatch output: {result.stdout}"}]}
    except subprocess.TimeoutExpired:
        return {"content": [{"type": "text", "text": "sbatch timed out after 30s"}]}


@tool(
    "job_status",
    "Get SLURM job status via sacct. Returns job state, exit code, elapsed time, and memory.",
    {"job_id": int},
)
async def job_status(args: dict) -> dict:
    job_id: int = args["job_id"]
    cmd = f"sacct -j {job_id} --format=JobID,State,ExitCode,Elapsed,MaxRSS --parsable2 --noheader"
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
        return {"content": [{"type": "text", "text": result.stdout.strip() or "(no output)"}]}
    except subprocess.TimeoutExpired:
        return {"content": [{"type": "text", "text": "sacct timed out"}]}


@tool(
    "queue_status",
    "Show current SLURM queue for this user.",
    {},
)
async def queue_status(args: dict) -> dict:
    cmd = "squeue -u $USER --format='%.18i %.9P %.50j %.8u %.8T %.10M %.9l %.6D %R' --noheader"
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
        return {"content": [{"type": "text", "text": result.stdout.strip() or "(queue empty)"}]}
    except subprocess.TimeoutExpired:
        return {"content": [{"type": "text", "text": "squeue timed out"}]}


@tool(
    "cancel_job",
    "Cancel a SLURM job.",
    {"job_id": int},
)
async def cancel_job(args: dict) -> dict:
    job_id: int = args["job_id"]
    cmd = f"scancel {job_id}"
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
        if result.returncode == 0:
            return {"content": [{"type": "text", "text": f"Job {job_id} cancelled"}]}
        return {"content": [{"type": "text", "text": f"scancel failed: {result.stderr}"}]}
    except subprocess.TimeoutExpired:
        return {"content": [{"type": "text", "text": "scancel timed out"}]}
