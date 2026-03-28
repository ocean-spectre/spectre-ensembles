"""
breed_vectors.py
================
Bred vector ensemble generation for MITgcm.

Subcommands:
    init     — Create N perturbed pickup files from a control pickup
    rescale  — Compute bred vectors, rescale, write new perturbed pickups
    status   — Report per-variable RMS of bred vectors for each member

Usage:
    python breed_vectors.py init    <breed_config.yaml>
    python breed_vectors.py rescale <breed_config.yaml> --cycle <N>
    python breed_vectors.py status  <breed_config.yaml> --cycle <N>
"""

import os
import sys
import re
import argparse
import yaml
import numpy as np
from pathlib import Path


# ---------------------------------------------------------------------------
# MITgcm pickup file I/O
# ---------------------------------------------------------------------------

# Standard pickup field order for MITgcm (with staggerTimeStep)
# Each 3D field has Nr levels; each 2D field has 1 level.
# Fields come in pairs: current + previous (Adams-Bashforth)
PICKUP_FIELDS_3D = ["Uvel", "Vvel", "Theta", "Salt", "GuNm1", "GvNm1"]
PICKUP_FIELDS_2D = ["EtaN", "dEtaHdt", "EtaH"]

# Indices of the dynamically meaningful fields (not tendency terms)
DYNAMIC_3D = {"Uvel": 0, "Vvel": 1, "Theta": 2, "Salt": 3}
DYNAMIC_2D = {"EtaN": 0}


def read_pickup_meta(meta_path):
    """Parse pickup .meta file for dimensions and field list."""
    with open(meta_path, "r") as f:
        text = f.read()

    dims_match = re.search(r"dimList\s*=\s*\[\s*([\d\s,]+)\]", text)
    flds_match = re.search(r"fldList\s*=\s*\{([^}]+)\}", text)
    nflds_match = re.search(r"nFlds\s*=\s*\[\s*(\d+)\s*\]", text)
    nrec_match = re.search(r"nrecords\s*=\s*\[\s*(\d+)\s*\]", text)

    dims = []
    if dims_match:
        nums = [int(x.strip()) for x in dims_match.group(1).split(",") if x.strip()]
        dims = [nums[i] for i in range(0, len(nums), 3)]

    fields = []
    if flds_match:
        fields = [s.strip().strip("'").strip() for s in flds_match.group(1).split("'") if s.strip().strip("'").strip()]

    nflds = int(nflds_match.group(1)) if nflds_match else len(fields)
    nrecs = int(nrec_match.group(1)) if nrec_match else nflds

    return {"dims": dims, "fields": fields, "nflds": nflds, "nrecords": nrecs}


def read_pickup(data_path, Nx, Ny, Nr):
    """Read a full pickup .data file into a dict of numpy arrays keyed by field name."""
    meta_path = data_path.replace(".data", ".meta")
    meta = read_pickup_meta(meta_path)
    fields = meta["fields"]

    raw = np.fromfile(data_path, dtype=">f8")  # pickups are float64
    record_size_3d = Nx * Ny * Nr
    record_size_2d = Nx * Ny

    result = {}
    offset = 0
    for fname in fields:
        # Determine if 3D or 2D from known field names
        if any(fname.startswith(f3d) for f3d in ["Uvel", "Vvel", "Theta", "Salt", "GuNm", "GvNm",
                                                    "PhiHyd", "dPhiHyd"]):
            size = record_size_3d
            shape = (Nr, Ny, Nx)
        else:
            size = record_size_2d
            shape = (Ny, Nx)

        result[fname] = raw[offset:offset + size].reshape(shape).copy()
        offset += size

    return result, meta


def write_pickup(data_path, fields_dict, meta, Nx, Ny, Nr):
    """Write a pickup .data file from a dict of arrays, preserving field order."""
    arrays = []
    for fname in meta["fields"]:
        arrays.append(fields_dict[fname].ravel())
    combined = np.concatenate(arrays)
    combined.astype(">f8").tofile(data_path)

    # Copy the .meta file as-is (structure unchanged)
    meta_src = data_path.replace(".data", ".meta")
    # Meta is already in place from the control — no need to rewrite


# ---------------------------------------------------------------------------
# Perturbation and rescaling
# ---------------------------------------------------------------------------

def compute_rms(arr, mask=None):
    """Compute RMS of an array, optionally with a mask."""
    if mask is not None:
        vals = arr[mask]
    else:
        vals = arr[arr != 0]  # exclude exact zeros (land)
    if len(vals) == 0:
        return 0.0
    return np.sqrt(np.mean(vals ** 2))


def create_random_perturbation(control_fields, Nx, Ny, Nr, target_temp_rms, rng):
    """Create a perturbed pickup by adding scaled random noise to the control.

    A single random field is generated for temperature. The noise is scaled
    so that its RMS matches target_temp_rms. The same scaling factor is
    applied to all other dynamic fields, with per-field random noise.
    This creates perturbations with the right amplitude but no initial
    dynamical balance — the breeding process will project these onto
    balanced growing modes.
    """
    perturbed = {k: v.copy() for k, v in control_fields.items()}

    # Create ocean mask from Theta (non-zero cells)
    theta = control_fields["Theta"]
    ocean_mask = theta != 0

    # Generate random noise for temperature, compute scaling factor
    noise_t = rng.standard_normal(theta.shape)
    noise_t[~ocean_mask] = 0
    raw_rms = compute_rms(noise_t, ocean_mask)
    if raw_rms > 0:
        scale = target_temp_rms / raw_rms
    else:
        scale = 0

    # Apply scaled noise to temperature
    perturbed["Theta"] = theta + scale * noise_t

    # Apply independently-generated noise with same scale to other dynamic fields
    for fname in ["Salt", "Uvel", "Vvel"]:
        if fname in control_fields:
            field = control_fields[fname]
            mask = field != 0
            noise = rng.standard_normal(field.shape)
            noise[~mask] = 0
            perturbed[fname] = field + scale * noise

    # Small perturbation to EtaN
    if "EtaN" in control_fields:
        eta = control_fields["EtaN"]
        mask = eta != 0
        noise = rng.standard_normal(eta.shape)
        noise[~mask] = 0
        perturbed["EtaN"] = eta + scale * noise

    return perturbed


def compute_bred_vector_and_rescale(control_fields, member_fields, target_temp_rms):
    """Compute bred vector (member - control), rescale by temperature RMS.

    Returns the new perturbed fields (control + rescaled bred vector)
    and diagnostic info.
    """
    # Compute bred vector
    bred = {}
    for fname in member_fields:
        bred[fname] = member_fields[fname] - control_fields[fname]

    # Compute temperature RMS of the bred vector
    theta_bred = bred.get("Theta", np.zeros(1))
    ocean_mask = control_fields["Theta"] != 0
    actual_rms = compute_rms(theta_bred, ocean_mask)

    if actual_rms > 0:
        rescale_factor = target_temp_rms / actual_rms
    else:
        rescale_factor = 1.0

    # Rescale ALL fields by the same factor (preserves dynamical balance)
    new_perturbed = {}
    for fname in control_fields:
        if fname in bred:
            new_perturbed[fname] = control_fields[fname] + rescale_factor * bred[fname]
        else:
            new_perturbed[fname] = control_fields[fname].copy()

    # Per-variable RMS diagnostics
    diag = {"rescale_factor": rescale_factor, "theta_rms_before": actual_rms}
    for fname in ["Theta", "Salt", "Uvel", "Vvel", "EtaN"]:
        if fname in bred:
            mask = control_fields[fname] != 0 if fname != "EtaN" else None
            diag[f"{fname}_rms"] = compute_rms(bred[fname], mask) * rescale_factor

    return new_perturbed, diag


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def cmd_init(config, config_path):
    """Create initial perturbed pickup files for all members."""
    breed = config["breeding"]
    grid = config["grid"]
    ctrl = config["control"]
    paths = config["paths"]

    Nx, Ny, Nr = grid["Nx"], grid["Ny"], grid["Nr"]
    n_members = breed["n_members"]
    target_rms = breed["target_amplitude"]["temperature_rms"]

    ensemble_dir = os.path.join(os.path.dirname(config_path), paths["ensemble_dir"])

    # Find control pickup
    ctrl_run_dir = os.path.join(os.path.dirname(config_path), ctrl["run_dir"])
    pickup_iter = ctrl["pickup_iter"]
    if pickup_iter is None:
        # Find the latest permanent pickup
        import glob
        pickups = sorted(glob.glob(os.path.join(ctrl_run_dir, "pickup.??????????.data")))
        if not pickups:
            print("Error: no pickup files found in control run directory", file=sys.stderr)
            sys.exit(1)
        pickup_data = pickups[-1]
        pickup_iter = int(os.path.basename(pickup_data).split(".")[1])
    else:
        pickup_data = os.path.join(ctrl_run_dir, f"pickup.{pickup_iter:010d}.data")

    pickup_meta = pickup_data.replace(".data", ".meta")
    print(f"Control pickup: {pickup_data}")
    print(f"  Iteration: {pickup_iter}")

    # Read control pickup
    control_fields, meta = read_pickup(pickup_data, Nx, Ny, Nr)
    print(f"  Fields: {list(control_fields.keys())}")
    print(f"  Theta range: [{control_fields['Theta'].min():.2f}, {control_fields['Theta'].max():.2f}]")

    # Create perturbed pickups
    for m in range(1, n_members + 1):
        member_dir = os.path.join(ensemble_dir, f"{paths['member_prefix']}_{m:03d}")
        os.makedirs(member_dir, exist_ok=True)

        rng = np.random.default_rng(seed=42 + m)  # reproducible per member
        perturbed = create_random_perturbation(control_fields, Nx, Ny, Nr, target_rms, rng)

        # Write perturbed pickup
        out_data = os.path.join(member_dir, f"pickup.{pickup_iter:010d}.data")
        out_meta = os.path.join(member_dir, f"pickup.{pickup_iter:010d}.meta")
        write_pickup(out_data, perturbed, meta, Nx, Ny, Nr)

        # Copy meta file
        import shutil
        shutil.copy2(pickup_meta, out_meta)

        # Write nIter0 for this member
        niter0_file = os.path.join(member_dir, "nIter0.txt")
        with open(niter0_file, "w") as f:
            f.write(str(pickup_iter))

        print(f"  Member {m:03d}: written to {member_dir}")

    print(f"\nInitialized {n_members} perturbed members from iteration {pickup_iter}")
    print(f"Target temperature RMS: {target_rms}°C")


def cmd_rescale(config, config_path, cycle):
    """Compute bred vectors and rescale after a breeding cycle."""
    breed = config["breeding"]
    grid = config["grid"]
    ctrl = config["control"]
    paths = config["paths"]

    Nx, Ny, Nr = grid["Nx"], grid["Ny"], grid["Nr"]
    n_members = breed["n_members"]
    target_rms = breed["target_amplitude"]["temperature_rms"]
    nTimeSteps = config["member_run"]["nTimeSteps"]

    ensemble_dir = os.path.join(os.path.dirname(config_path), paths["ensemble_dir"])

    # Control pickup at end of this cycle
    ctrl_run_dir = os.path.join(os.path.dirname(config_path), ctrl["run_dir"])

    # Determine the iteration number at the end of this cycle
    # First cycle starts from pickup_iter, each cycle adds nTimeSteps
    pickup_iter = ctrl["pickup_iter"]
    if pickup_iter is None:
        import glob
        pickups = sorted(glob.glob(os.path.join(ctrl_run_dir, "pickup.??????????.data")))
        pickup_iter = int(os.path.basename(pickups[-1]).split(".")[1])

    end_iter = pickup_iter + cycle * nTimeSteps

    # Read control state at end of cycle
    ctrl_pickup = os.path.join(ctrl_run_dir, f"pickup.{end_iter:010d}.data")
    if not os.path.exists(ctrl_pickup):
        print(f"Error: control pickup not found: {ctrl_pickup}", file=sys.stderr)
        sys.exit(1)

    print(f"Control pickup (end of cycle {cycle}): {ctrl_pickup}")
    control_fields, meta = read_pickup(ctrl_pickup, Nx, Ny, Nr)

    # Process each member
    for m in range(1, n_members + 1):
        member_dir = os.path.join(ensemble_dir, f"{paths['member_prefix']}_{m:03d}")

        # Read member pickup at end of cycle
        member_pickup = os.path.join(member_dir, f"pickup.{end_iter:010d}.data")
        if not os.path.exists(member_pickup):
            print(f"  Member {m:03d}: SKIP — no pickup at iter {end_iter}")
            continue

        member_fields, _ = read_pickup(member_pickup, Nx, Ny, Nr)

        # Compute bred vector and rescale
        new_perturbed, diag = compute_bred_vector_and_rescale(
            control_fields, member_fields, target_rms
        )

        # Write new perturbed pickup for next cycle
        out_data = os.path.join(member_dir, f"pickup.{end_iter:010d}.data")
        write_pickup(out_data, new_perturbed, meta, Nx, Ny, Nr)

        # Update nIter0
        with open(os.path.join(member_dir, "nIter0.txt"), "w") as f:
            f.write(str(end_iter))

        print(f"  Member {m:03d}: rescale={diag['rescale_factor']:.3f}, "
              f"T_rms={diag.get('Theta_rms', 0):.4f}°C, "
              f"S_rms={diag.get('Salt_rms', 0):.4f}, "
              f"U_rms={diag.get('Uvel_rms', 0):.4f} m/s, "
              f"Eta_rms={diag.get('EtaN_rms', 0):.4f} m")

    print(f"\nCycle {cycle} rescaling complete")


def cmd_status(config, config_path, cycle):
    """Report per-variable RMS of current bred vectors."""
    breed = config["breeding"]
    grid = config["grid"]
    ctrl = config["control"]
    paths = config["paths"]

    Nx, Ny, Nr = grid["Nx"], grid["Ny"], grid["Nr"]
    n_members = breed["n_members"]
    nTimeSteps = config["member_run"]["nTimeSteps"]

    ensemble_dir = os.path.join(os.path.dirname(config_path), paths["ensemble_dir"])
    ctrl_run_dir = os.path.join(os.path.dirname(config_path), ctrl["run_dir"])

    pickup_iter = ctrl["pickup_iter"]
    if pickup_iter is None:
        import glob
        pickups = sorted(glob.glob(os.path.join(ctrl_run_dir, "pickup.??????????.data")))
        pickup_iter = int(os.path.basename(pickups[-1]).split(".")[1])

    end_iter = pickup_iter + cycle * nTimeSteps
    ctrl_pickup = os.path.join(ctrl_run_dir, f"pickup.{end_iter:010d}.data")
    control_fields, _ = read_pickup(ctrl_pickup, Nx, Ny, Nr)

    print(f"Bred vector RMS at cycle {cycle} (iter {end_iter}):")
    print(f"{'Member':>8s}  {'T (°C)':>10s}  {'S (PSU)':>10s}  {'U (m/s)':>10s}  {'V (m/s)':>10s}  {'Eta (m)':>10s}")
    print("-" * 62)

    for m in range(1, n_members + 1):
        member_dir = os.path.join(ensemble_dir, f"{paths['member_prefix']}_{m:03d}")
        member_pickup = os.path.join(member_dir, f"pickup.{end_iter:010d}.data")
        if not os.path.exists(member_pickup):
            continue
        member_fields, _ = read_pickup(member_pickup, Nx, Ny, Nr)

        rms = {}
        for fname in ["Theta", "Salt", "Uvel", "Vvel", "EtaN"]:
            if fname in member_fields and fname in control_fields:
                diff = member_fields[fname] - control_fields[fname]
                mask = control_fields[fname] != 0 if fname != "EtaN" else None
                rms[fname] = compute_rms(diff, mask)

        print(f"  {m:03d}     {rms.get('Theta', 0):10.5f}  {rms.get('Salt', 0):10.5f}  "
              f"{rms.get('Uvel', 0):10.5f}  {rms.get('Vvel', 0):10.5f}  {rms.get('EtaN', 0):10.5f}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Bred vector ensemble generation")
    sub = parser.add_subparsers(dest="command")

    p_init = sub.add_parser("init", help="Create initial perturbed pickups")
    p_init.add_argument("config", help="Path to breed_config.yaml")

    p_rescale = sub.add_parser("rescale", help="Compute bred vectors and rescale")
    p_rescale.add_argument("config", help="Path to breed_config.yaml")
    p_rescale.add_argument("--cycle", type=int, required=True, help="Breeding cycle number")

    p_status = sub.add_parser("status", help="Report bred vector RMS")
    p_status.add_argument("config", help="Path to breed_config.yaml")
    p_status.add_argument("--cycle", type=int, required=True, help="Breeding cycle number")

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
