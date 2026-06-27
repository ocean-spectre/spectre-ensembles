"""Forcing data validation tools for EXF and OBC binary files."""

from __future__ import annotations

import os

import numpy as np
from claude_agent_sdk import tool

# Physical range expectations for EXF variables
EXF_RANGES: dict[str, tuple[float, float]] = {
    "atemp": (240.0, 320.0),
    "aqh": (0.0, 0.025),
    "uwind": (-50.0, 50.0),
    "vwind": (-50.0, 50.0),
    "swdown": (0.0, 1200.0),
    "lwdown": (100.0, 500.0),
    "precip": (0.0, 1e-3),
    "evap": (-1e-3, 1e-4),
}


@tool(
    "validate_exf_binary",
    "Validate an EXF binary forcing file. Checks physical ranges, NaN/Inf, and grid orientation.",
    {"path": str, "var_name": str, "nx": int, "ny": int},
)
async def validate_exf_binary(args: dict) -> dict:
    path: str = args["path"]
    var_name: str = args["var_name"]
    nx: int = args.get("nx", 768)
    ny: int = args.get("ny", 424)

    if not os.path.exists(path):
        return {"content": [{"type": "text", "text": f"File not found: {path}"}]}

    try:
        record_size = ny * nx
        arr = np.fromfile(path, dtype=">f4", count=record_size).reshape(ny, nx)

        result_lines = [f"File: {path}", f"Variable: {var_name}", f"Shape: ({ny}, {nx})"]

        # Basic stats
        has_nan = bool(np.isnan(arr).any())
        has_inf = bool(np.isinf(arr).any())
        result_lines.append(f"Min: {arr.min():.6g}")
        result_lines.append(f"Max: {arr.max():.6g}")
        result_lines.append(f"Mean: {arr.mean():.6g}")
        result_lines.append(f"NaN: {has_nan}")
        result_lines.append(f"Inf: {has_inf}")

        # Range check
        passed = True
        if var_name in EXF_RANGES:
            lo, hi = EXF_RANGES[var_name]
            valid = np.isfinite(arr)
            if valid.any():
                out_of_range = (arr[valid] < lo) | (arr[valid] > hi)
                pct = 100.0 * out_of_range.sum() / valid.sum()
                result_lines.append(f"Expected range: [{lo}, {hi}]")
                result_lines.append(f"Out of range: {pct:.2f}%")
                if pct > 5 or has_nan or has_inf:
                    passed = False

        # Grid orientation check (j=0 should be south/warm for atemp)
        if var_name == "atemp" and not has_nan:
            south_mean = float(arr[0, :].mean())
            north_mean = float(arr[-1, :].mean())
            result_lines.append(f"j=0 (south) mean: {south_mean:.1f} K")
            result_lines.append(f"j={ny - 1} (north) mean: {north_mean:.1f} K")
            if south_mean < north_mean:
                result_lines.append("WARNING: South is cooler than north — possible orientation error")
                passed = False

        result_lines.append(f"Result: {'PASS' if passed else 'FAIL'}")
        return {"content": [{"type": "text", "text": "\n".join(result_lines)}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error validating {path}: {e}"}]}


@tool(
    "validate_obc_binary",
    "Validate an OBC binary file. Checks record count and dimensions.",
    {"path": str, "boundary": str, "var": str, "nr": int, "n_boundary": int, "expected_records": int},
)
async def validate_obc_binary(args: dict) -> dict:
    path: str = args["path"]
    boundary: str = args["boundary"]
    var: str = args["var"]
    nr: int = args.get("nr", 50)
    n_boundary: int = args["n_boundary"]
    expected_records: int = args.get("expected_records", 5479)

    if not os.path.exists(path):
        return {"content": [{"type": "text", "text": f"File not found: {path}"}]}

    try:
        file_size = os.path.getsize(path)
        is_2d = var.lower() in ("eta", "ssh", "etan")
        if is_2d:
            record_bytes = n_boundary * 4
        else:
            record_bytes = nr * n_boundary * 4

        actual_records = file_size / record_bytes if record_bytes > 0 else 0

        result_lines = [
            f"File: {path}",
            f"Boundary: {boundary}, Variable: {var}",
            f"File size: {file_size} bytes",
            f"Record size: {record_bytes} bytes",
            f"Actual records: {actual_records:.1f}",
            f"Expected records: {expected_records}",
        ]

        passed = abs(actual_records - expected_records) < 1
        if not passed:
            result_lines.append(f"MISMATCH: expected {expected_records}, got {actual_records:.1f}")

        # Sample first record for range check
        arr = np.fromfile(path, dtype=">f4", count=record_bytes // 4)
        result_lines.append(f"First record min: {arr.min():.6g}")
        result_lines.append(f"First record max: {arr.max():.6g}")
        result_lines.append(f"NaN: {bool(np.isnan(arr).any())}")

        result_lines.append(f"Result: {'PASS' if passed else 'FAIL'}")
        return {"content": [{"type": "text", "text": "\n".join(result_lines)}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error validating {path}: {e}"}]}
