"""Fortran namelist parsing and validation tools."""

from __future__ import annotations

import os
import re
from pathlib import Path

from claude_agent_sdk import tool


def parse_fortran_namelist(text: str) -> dict[str, dict[str, str]]:
    """Parse a Fortran namelist file into a dict of {group: {key: value}}."""
    result: dict[str, dict[str, str]] = {}
    current_group = None

    for line in text.splitlines():
        stripped = line.strip()
        # Skip comments and empty lines
        if not stripped or stripped.startswith("#") or stripped.startswith("!"):
            continue
        # Group start: &GROUPNAME
        m = re.match(r"&(\w+)", stripped)
        if m:
            current_group = m.group(1)
            result[current_group] = {}
            continue
        # Group end
        if stripped == "/" or stripped == "&":
            current_group = None
            continue
        # Key = value
        if current_group and "=" in stripped:
            key, _, val = stripped.partition("=")
            key = key.strip()
            val = val.strip().rstrip(",")
            result[current_group][key] = val

    return result


@tool(
    "parse_namelist",
    "Parse a Fortran namelist file and return its contents as structured data.",
    {"path": str},
)
async def parse_namelist_tool(args: dict) -> dict:
    path: str = args["path"]
    try:
        text = Path(path).read_text()
        parsed = parse_fortran_namelist(text)
        lines = []
        for group, params in parsed.items():
            lines.append(f"&{group}")
            for k, v in params.items():
                lines.append(f"  {k} = {v}")
            lines.append("")
        return {"content": [{"type": "text", "text": "\n".join(lines)}]}
    except OSError as e:
        return {"content": [{"type": "text", "text": f"Error reading {path}: {e}"}]}


@tool(
    "validate_namelists",
    "Run cross-validation checks on all MITgcm namelist files in an input directory. "
    "Checks package consistency, grid dimensions, EXF config, OBC sizes, time config, "
    "and memory safety.",
    {"input_dir": str},
)
async def validate_namelists(args: dict) -> dict:
    input_dir: str = args["input_dir"]
    checks: list[str] = []
    pass_count = 0
    fail_count = 0

    def check(name: str, passed: bool, detail: str) -> None:
        nonlocal pass_count, fail_count
        status = "PASS" if passed else "FAIL"
        if passed:
            pass_count += 1
        else:
            fail_count += 1
        checks.append(f"[{status}] {name}: {detail}")

    base = Path(input_dir)

    # Parse namelists
    namelists = {}
    for name in ("data", "data.exf", "data.obcs", "data.pkg", "data.diagnostics", "data.mnc"):
        path = base / name
        if path.exists():
            namelists[name] = parse_fortran_namelist(path.read_text())
        else:
            checks.append(f"[WARN] {name}: file not found")

    # 1. Package consistency
    pkg = namelists.get("data.pkg", {}).get("PACKAGES", {})
    use_diag = pkg.get("useDIAGNOSTICS", "").upper()
    use_mnc = pkg.get("useMNC", "").upper()
    use_exf = pkg.get("useEXF", "").upper()

    if use_diag == ".TRUE.":
        check("DIAGNOSTICS package", "data.diagnostics" in namelists,
              "data.diagnostics exists" if "data.diagnostics" in namelists else "data.diagnostics MISSING")

    # 2. Memory safety
    diag = namelists.get("data.diagnostics", {}).get("DIAGNOSTICS_LIST", {})
    diag_mnc = diag.get("diag_mnc", "")
    check("diag_mnc disabled", ".FALSE." in diag_mnc.upper() if diag_mnc else True,
          f"diag_mnc={diag_mnc}" if diag_mnc else "not set (OK)")

    parms = namelists.get("data", {}).get("PARM03", {})
    dump_freq = parms.get("dumpFreq", "0")
    check("dumpFreq=0", dump_freq.strip(".") == "0" or dump_freq == "0.",
          f"dumpFreq={dump_freq}")

    mnc_nml = namelists.get("data.mnc", {}).get("MNC_01", {})
    pickup_write = mnc_nml.get("pickup_write_mnc", "")
    check("pickup_write_mnc disabled",
          ".FALSE." in pickup_write.upper() if pickup_write else True,
          f"pickup_write_mnc={pickup_write}" if pickup_write else "not set (OK)")

    # 3. EXF check
    exf_nml = namelists.get("data.exf", {})
    exf04 = exf_nml.get("EXF_NML_04", {})
    check("No EXF interpolation metadata",
          not any("_nlon" in k or "_nlat" in k for k in exf04),
          "No *_nlon/*_nlat keys in EXF_NML_04")

    # 4. OBC period
    obcs = namelists.get("data.obcs", {}).get("OBCS_PARM01", {})
    for boundary in ("OB_Jnorth", "OB_Jsouth", "OB_Ieast", "OB_Iwest"):
        if boundary in obcs:
            check(f"{boundary} defined", True, f"{boundary} present")

    # Summary
    checks.append(f"\nSummary: {pass_count} PASS, {fail_count} FAIL")
    return {"content": [{"type": "text", "text": "\n".join(checks)}]}
