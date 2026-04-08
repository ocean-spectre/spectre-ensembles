# Glorys v12 - MITgcm Curvilinear Grid

MITgcm re-run of the Glorys v12 simulation on the native NEMO curvilinear grid.
Running on the native grid means no interpolation is needed for GLORYS ocean fields,
and the Arakawa C-grid velocity fields are numerically divergence-free, which
avoids the gravity-wave eruptions that typically complicate spinup on remapped grids.


## Configuration

| Parameter | Value |
|-----------|-------|
| Ocean source | CMEMS Glorys v12 (`cmems_mod_glo_phy_my_0.083deg_P1D-m`) |
| Atmosphere source | ERA5 single levels (EXF package) |
| Longitude | -82.0 to -17.5 |
| Latitude | 26.0 to 50.5 |
| Vertical levels | 50 |
| Simulation period | 2002-07-01 – 2017-06-30 |
| Spinup | 2002-07-01 – 2003-07-01 × 5 repeats |
| MPI layout | 8 × 8 = 64 ranks |

Open boundary array sizes (5479 daily time steps, 2002–2017):

| Boundary | U/V/T/S shape | Eta shape |
|----------|--------------|-----------|
| South | (5479, 50, 768) | (5479, 768) |
| North | (5479, 50, 768) | (5479, 768) |
| West | (5479, 50, 424) | — |
| East | (5479, 50, 424) | — |


## Workflow

All steps are run as Slurm jobs from the `workflows/` directory. Each script
sources `workflows/env.sh` for container image paths and data directories.

### 1. Build MITgcm

```bash
sbatch workflows/build.sh
```

Compiles MITgcm inside the base container image using `code/` for compile-time
options. The executable is written into the simulation directory.

### 2. Download ocean data (GLORYS v12)

```bash
sbatch workflows/download_glorysv12_raw.sh
```

Downloads daily GLORYS v12 fields (T, S, U, V, SSH) from CMEMS for the domain
and years defined in `etc/config.yaml`.

### 3. Download atmospheric data (ERA5)

```bash
sbatch workflows/download_era5.sh
```

Downloads ERA5 single-level fields from the Copernicus CDS for each variable
listed under `atmosphere.variables` in `etc/config.yaml`.

### 4. Generate initial conditions

```bash
sbatch workflows/make_ocean_initial_conditions.sh
```

Interpolates GLORYS v12 T, S, U, V, SSH fields onto the MITgcm grid and writes
binary initial condition files to `input/`.

### 5. Generate ocean boundary conditions

```bash
sbatch workflows/make_ocean_boundary_conditions.sh
```

Processes GLORYS v12 daily fields into open boundary condition binary files
(U, V, T, S, Eta on all four boundaries) in `input/`.

### 6. Generate EXF atmospheric forcing

```bash
sbatch workflows/make_exf_conditions.sh
```

Processes ERA5 fields into EXF binary forcing files in `input/`. Applies any
`scale_factor` values from the config (e.g. for radiation units), and computes
specific humidity from dewpoint temperature and surface pressure.

To review the produced forcing fields before running the model:

```bash
sbatch -w franklin -c8 --wrap \
  "srun --container-image=\$SPECTRE_UTILS_IMG \
        --container-mounts=\$(pwd)/../:/workspace,\$HOST_DATADIR:/data \
        python /opt/spectre_utils/review_exf_conditions.py /workspace/etc/config.yaml"
```

Output (report + figures) is written to `review/atmosphere/`.

### 7. Run the model

```bash
sbatch workflows/run.sh
```

Launches MITgcm under the base container image. Sets up the run directory on
first launch, then submits the MPI job. The run directory is controlled by
`RUN_DIR` in `run.sh` (default: `demo/`).


## Frazil ice and freezing

This simulation enables the MITgcm frazil ice package (`useFRAZIL=.TRUE.` in
`data.pkg`) together with the `allowFreezing=.TRUE.` flag in `data` PARM01.

**Intention.** In a regional ocean model without a coupled sea-ice model, surface
heat loss during winter can cool seawater below its local freezing point (a
function of salinity and pressure). Without intervention the model would produce
unphysical sub-freezing temperatures, which destabilize the equation of state,
generate spurious convection, and can ultimately blow up the simulation.

**Physical mechanism.** When the frazil package is active, MITgcm checks the
in-situ temperature in every cell at the end of each timestep against the local
freezing point, T_f(S, p). If the temperature falls below T_f, the excess
cooling (T_f - T) is converted into frazil ice formation: the cell temperature
is reset to T_f and the latent heat required to form the implied ice mass is
removed from the ocean heat budget. In effect, the ocean "pays" for the phase
change with latent heat rather than continuing to cool. The `allowFreezing` flag
works in concert by permitting the nonlinear free-surface and vertical mixing
schemes to recognize the freezing-point floor, preventing advection or diffusion
from re-introducing sub-freezing temperatures between frazil corrections.

**Impact on the simulation.**
- Prevents numerical blow-ups in winter, particularly on the Labrador shelf and
  in the subpolar gyre where strong surface cooling and fresh meltwater create
  conditions favorable for freezing.
- Adds an implicit latent heat sink wherever ice would form, damping the winter
  mixed-layer deepening that would otherwise be overestimated.
- Does not simulate ice dynamics, thickness, or transport — it is a
  thermodynamic clamp only. Any scientific analysis of ice-affected regions
  should note that frazil formation acts as a sub-grid-scale parameterization of
  ice-ocean thermodynamics, not a prognostic sea-ice model.


## Data sources

| Dataset | Access | Variables |
|---------|--------|-----------|
| CMEMS Glorys v12 daily | `copernicusmarine` Python package | thetao, so, uo, vo, zos |
| CMEMS Glorys v12 static | `copernicusmarine` Python package | mask, deptho, deptho_lev |
| ERA5 single levels | `cdsapi` Python package | winds, temperature, humidity, radiation, precip, pressure |
