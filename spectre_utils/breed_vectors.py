"""
breed_vectors.py
================
Bred vector ensemble generation for MITgcm.

Works with initial condition binary files (T.init.bin, S.init.bin, etc.)
rather than pickup files. Each breeding cycle:
  1. Member starts from nIter0=0 with perturbed IC files
  2. Runs forward 30 days, producing a pickup at the end
  3. Bred vector = member_pickup - control_pickup (at t=30 days)
  4. Rescale and overwrite the member's IC files for the next cycle

Subcommands:
    init     — Create N perturbed IC files from control ICs
    rescale  — Compute bred vectors from pickups, rescale, overwrite member ICs
    status   — Report per-variable RMS of bred vectors for each member

Usage:
    python breed_vectors.py init    <breed_config.yaml>
    python breed_vectors.py rescale <breed_config.yaml> --cycle <N>
    python breed_vectors.py status  <breed_config.yaml> --cycle <N>
"""

import os
import sys
import re
import json
import argparse
import yaml
import numpy as np
from pathlib import Path


# ---------------------------------------------------------------------------
# IC and pickup file definitions
# ---------------------------------------------------------------------------

# Initial condition files: simple 3D or 2D arrays, big-endian float32
IC_FILES = {
    "T.init.bin": {"shape_type": "3d", "field": "Theta"},
    "S.init.bin": {"shape_type": "3d", "field": "Salt"},
    "U.init.bin": {"shape_type": "3d", "field": "Uvel"},
    "V.init.bin": {"shape_type": "3d", "field": "Vvel"},
    "Eta.init.bin": {"shape_type": "2d", "field": "EtaN"},
}

# Pickup fields — used for reading the member state after a breeding cycle
# MITgcm pickup with staggerTimeStep contains pairs: current + previous (AB)
# We only need the current fields (first of each pair)
PICKUP_FIELDS = [
    ("Uvel", "3d"),
    ("Vvel", "3d"),
    ("Theta", "3d"),
    ("Salt", "3d"),
    ("GuNm1", "3d"),
    ("GvNm1", "3d"),
    ("EtaN", "2d"),
    ("dEtaHdt", "2d"),
    ("EtaH", "2d"),
]


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def read_ic(path, Nx, Ny, Nr, shape_type):
    """Read an initial condition binary file."""
    if shape_type == "3d":
        return np.fromfile(path, dtype=">f4").reshape(Nr, Ny, Nx)
    else:
        return np.fromfile(path, dtype=">f4").reshape(Ny, Nx)


def write_ic(path, data):
    """Write an initial condition binary file."""
    data.astype(">f4").tofile(path)


def read_pickup_field(data_path, field_name, Nx, Ny, Nr):
    """Read a single field from a pickup .data file.

    Pickup files are float64, fields in the order defined by PICKUP_FIELDS.
    """
    raw = np.fromfile(data_path, dtype=">f8")
    offset = 0
    for fname, ftype in PICKUP_FIELDS:
        size = Nx * Ny * Nr if ftype == "3d" else Nx * Ny
        shape = (Nr, Ny, Nx) if ftype == "3d" else (Ny, Nx)
        if fname == field_name:
            return raw[offset:offset + size].reshape(shape)
        offset += size
    return None


# ---------------------------------------------------------------------------
# Perturbation and rescaling
# ---------------------------------------------------------------------------

def compute_rms(arr):
    """Compute RMS of non-zero elements."""
    vals = arr[arr != 0]
    if len(vals) == 0:
        return 0.0
    return float(np.sqrt(np.mean(vals ** 2)))


def create_perturbation(control_ic, target_rms, rng):
    """Add scaled random noise to a control IC field.

    Returns perturbed field. Scale factor is derived from the temperature
    field externally — this function applies a pre-computed scale.
    """
    ocean_mask = control_ic != 0
    noise = rng.standard_normal(control_ic.shape).astype(np.float32)
    noise[~ocean_mask] = 0
    raw_rms = compute_rms(noise)
    if raw_rms > 0:
        noise *= target_rms / raw_rms
    return control_ic + noise


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def cmd_init(config, config_path):
    """Create initial perturbed IC files for all members."""
    breed = config["breeding"]
    grid = config["grid"]
    paths_cfg = config["paths"]

    Nx, Ny, Nr = grid["Nx"], grid["Ny"], grid["Nr"]
    n_members = breed["n_members"]
    target_rms = breed["target_amplitude"]["temperature_rms"]

    ensemble_dir = os.path.dirname(os.path.abspath(config_path))
    sim_input_dir = os.path.join(os.path.dirname(ensemble_dir), "input")

    print(f"Control ICs from: {sim_input_dir}")
    print(f"Target temperature RMS: {target_rms}°C")

    # Read control ICs
    control = {}
    for fname, info in IC_FILES.items():
        path = os.path.join(sim_input_dir, fname)
        if not os.path.exists(path):
            print(f"Error: {path} not found", file=sys.stderr)
            sys.exit(1)
        control[info["field"]] = read_ic(path, Nx, Ny, Nr, info["shape_type"])
        print(f"  {fname}: shape={control[info['field']].shape}")

    # For each member: generate noise scaled to target_rms (from temperature),
    # apply same scale factor to all variables
    for m in range(1, n_members + 1):
        member_dir = os.path.join(ensemble_dir, f"{paths_cfg['member_prefix']}_{m:03d}")
        os.makedirs(member_dir, exist_ok=True)

        rng = np.random.default_rng(seed=42 + m)

        # Compute scale factor from temperature noise
        theta = control["Theta"]
        ocean_mask = theta != 0
        noise_t = rng.standard_normal(theta.shape).astype(np.float32)
        noise_t[~ocean_mask] = 0
        raw_rms = compute_rms(noise_t)
        scale = target_rms / raw_rms if raw_rms > 0 else 0

        # Write perturbed ICs for all variables
        for fname, info in IC_FILES.items():
            field = control[info["field"]]
            mask = field != 0
            noise = rng.standard_normal(field.shape).astype(np.float32)
            noise[~mask] = 0
            perturbed = field + scale * noise
            write_ic(os.path.join(member_dir, fname), perturbed)

        print(f"  Member {m:03d}: scale={scale:.6f}")

    print(f"\nInitialized {n_members} members")


def cmd_rescale(config, config_path, cycle):
    """Compute bred vectors from pickups, rescale, overwrite member ICs."""
    breed = config["breeding"]
    grid = config["grid"]
    ctrl_cfg = config["control"]
    paths_cfg = config["paths"]
    member_run_cfg = config["member_run"]

    Nx, Ny, Nr = grid["Nx"], grid["Ny"], grid["Nr"]
    n_members = breed["n_members"]
    target_rms = breed["target_amplitude"]["temperature_rms"]
    nTimeSteps = member_run_cfg["nTimeSteps"]

    ensemble_dir = os.path.dirname(os.path.abspath(config_path))
    ctrl_run_dir = os.path.join(os.path.dirname(ensemble_dir), ctrl_cfg["run_dir"])

    # The pickup iteration at the end of the cycle (all members ran from
    # nIter0=0 for nTimeSteps)
    end_iter = nTimeSteps
    pickup_name = f"pickup.{end_iter:010d}.data"

    # Read control pickup at end of cycle
    ctrl_pickup_path = os.path.join(ctrl_run_dir, pickup_name)
    if not os.path.exists(ctrl_pickup_path):
        print(f"Error: control pickup not found: {ctrl_pickup_path}", file=sys.stderr)
        print(f"The control run must also have been run for {nTimeSteps} steps "
              f"to produce this pickup.", file=sys.stderr)
        sys.exit(1)

    print(f"Control pickup: {ctrl_pickup_path}")
    ctrl_fields = {}
    for fname, info in IC_FILES.items():
        pickup_field = info["field"]
        data = read_pickup_field(ctrl_pickup_path, pickup_field, Nx, Ny, Nr)
        if data is not None:
            ctrl_fields[pickup_field] = data.astype(np.float32)
            print(f"  {pickup_field}: shape={data.shape}")

    # Read control ICs (for creating new perturbed ICs)
    sim_input_dir = os.path.join(os.path.dirname(ensemble_dir), "input")
    control_ics = {}
    for fname, info in IC_FILES.items():
        control_ics[info["field"]] = read_ic(
            os.path.join(sim_input_dir, fname), Nx, Ny, Nr, info["shape_type"]
        )

    # Process each member
    cycle_diags = []
    for m in range(1, n_members + 1):
        member_dir = os.path.join(ensemble_dir, f"{paths_cfg['member_prefix']}_{m:03d}")
        member_run_dir = os.path.join(member_dir, "run")
        member_pickup = os.path.join(member_run_dir, pickup_name)

        if not os.path.exists(member_pickup):
            print(f"  Member {m:03d}: SKIP — no pickup at {pickup_name}")
            continue

        # Read member state at end of cycle
        member_fields = {}
        for fname, info in IC_FILES.items():
            data = read_pickup_field(member_pickup, info["field"], Nx, Ny, Nr)
            if data is not None:
                member_fields[info["field"]] = data.astype(np.float32)

        # Compute bred vector
        bred = {}
        for field_name in member_fields:
            bred[field_name] = member_fields[field_name] - ctrl_fields[field_name]

        # Compute rescale factor from temperature
        theta_rms = compute_rms(bred["Theta"])
        rescale = target_rms / theta_rms if theta_rms > 0 else 1.0

        # Overwrite member IC files: control_IC + rescaled bred vector
        for fname, info in IC_FILES.items():
            field_name = info["field"]
            new_ic = control_ics[field_name] + rescale * bred[field_name]
            write_ic(os.path.join(member_dir, fname), new_ic)

        # Diagnostics
        diag = {"member": m, "rescale_factor": rescale, "theta_rms_before": theta_rms}
        for field_name in bred:
            diag[f"{field_name}_rms"] = compute_rms(bred[field_name]) * rescale
        cycle_diags.append(diag)

        print(f"  Member {m:03d}: rescale={rescale:.3f}, "
              f"T={diag.get('Theta_rms', 0):.5f}°C, "
              f"S={diag.get('Salt_rms', 0):.5f}, "
              f"U={diag.get('Uvel_rms', 0):.5f} m/s, "
              f"Eta={diag.get('EtaN_rms', 0):.5f} m")

    # Write convergence log
    convergence_path = os.path.join(ensemble_dir, "convergence.json")
    if os.path.exists(convergence_path):
        with open(convergence_path, "r") as f:
            convergence = json.load(f)
    else:
        convergence = {"cycles": []}

    convergence["cycles"].append({
        "cycle": cycle,
        "end_iter": end_iter,
        "members": cycle_diags,
    })
    with open(convergence_path, "w") as f:
        json.dump(convergence, f, indent=2)

    print(f"\nCycle {cycle} rescaling complete — convergence log: {convergence_path}")


def cmd_status(config, config_path, cycle):
    """Report per-variable RMS of bred vectors."""
    ensemble_dir = os.path.dirname(os.path.abspath(config_path))
    convergence_path = os.path.join(ensemble_dir, "convergence.json")

    if not os.path.exists(convergence_path):
        print("No convergence data yet.")
        return

    with open(convergence_path, "r") as f:
        convergence = json.load(f)

    if cycle is not None:
        cycles = [c for c in convergence["cycles"] if c["cycle"] == cycle]
    else:
        cycles = convergence["cycles"]

    for c in cycles:
        members = c.get("members", [])
        if not members:
            continue
        print(f"\nCycle {c['cycle']} (end iter {c['end_iter']}):")
        print(f"{'Member':>8s}  {'T (°C)':>10s}  {'S (PSU)':>10s}  "
              f"{'U (m/s)':>10s}  {'V (m/s)':>10s}  {'Eta (m)':>10s}  {'Rescale':>8s}")
        print("-" * 72)
        for d in members:
            print(f"  {d['member']:03d}     "
                  f"{d.get('Theta_rms', 0):10.5f}  "
                  f"{d.get('Salt_rms', 0):10.5f}  "
                  f"{d.get('Uvel_rms', 0):10.5f}  "
                  f"{d.get('Vvel_rms', 0):10.5f}  "
                  f"{d.get('EtaN_rms', 0):10.5f}  "
                  f"{d.get('rescale_factor', 0):8.3f}")

        # Ensemble mean
        avg = lambda k: np.mean([d[k] for d in members if k in d])
        print(f"  {'MEAN':>3s}     "
              f"{avg('Theta_rms'):10.5f}  "
              f"{avg('Salt_rms'):10.5f}  "
              f"{avg('Uvel_rms'):10.5f}  "
              f"{avg('Vvel_rms'):10.5f}  "
              f"{avg('EtaN_rms'):10.5f}  "
              f"{avg('rescale_factor'):8.3f}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Bred vector ensemble generation")
    sub = parser.add_subparsers(dest="command")

    p_init = sub.add_parser("init", help="Create initial perturbed ICs")
    p_init.add_argument("config", help="Path to breed_config.yaml")

    p_rescale = sub.add_parser("rescale", help="Compute bred vectors and rescale")
    p_rescale.add_argument("config", help="Path to breed_config.yaml")
    p_rescale.add_argument("--cycle", type=int, required=True)

    p_status = sub.add_parser("status", help="Report bred vector RMS")
    p_status.add_argument("config", help="Path to breed_config.yaml")
    p_status.add_argument("--cycle", type=int, default=None)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    with open(args.config, "r") as f:
        config = yaml.safe_load(f)

    if args.command == "init":
        cmd_init(config, args.config)
    elif args.command == "rescale":
        cmd_rescale(config, args.config, args.cycle)
    elif args.command == "status":
        cmd_status(config, args.config, args.cycle)


if __name__ == "__main__":
    main()
