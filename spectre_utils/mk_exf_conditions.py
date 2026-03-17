import os
import sys
from spectre_utils import common
import yaml
from metpy.calc import specific_humidity_from_dewpoint
from metpy.units import units
from datetime import datetime
import numpy as np
import xarray as xr

# Number of time steps to load and write at once.
# ERA5 is hourly, so 744 ≈ one month. Tune down if memory is still tight.
TIME_CHUNK = 744


def _open_var(working_directory, prefix, mitgcm_name, years, t1, t2):
    """Open a single ERA5 variable across all years as a lazily-chunked dataset."""
    files = [f"{working_directory}/{prefix}_{mitgcm_name}_{year}.nc" for year in years]
    for fp in files:
        if not os.path.exists(fp):
            print(f"Missing file: {fp}", file=sys.stderr)
            sys.exit(1)
    ds = xr.open_mfdataset(files, combine="by_coords", chunks={"valid_time": TIME_CHUNK}).sel(
        valid_time=slice(t1, t2)
    )
    data_vars = list(ds.data_vars)
    if len(data_vars) == 1 and data_vars[0] != mitgcm_name:
        ds = ds.rename({data_vars[0]: mitgcm_name})
    # ERA5 latitude is stored north-to-south (60→20 N). Flip to south-to-north
    # so the binary layout matches data.exf: lat0=20.0, lat_inc=+0.25 (j=0=20N).
    ds = ds.isel(latitude=slice(None, None, -1))
    return ds


def _write_chunked(da, output_path):
    """Write a DataArray to a big-endian float32 binary file in time chunks."""
    n_times = da.sizes["valid_time"]
    with open(output_path, "wb") as f:
        for i in range(0, n_times, TIME_CHUNK):
            chunk = da.isel(valid_time=slice(i, i + TIME_CHUNK)).values
            chunk.astype(">f4").tofile(f)


def main():

    args = common.cli()

    # Load configuration from YAML file
    with open(args.config_file, "r") as f:
        config = yaml.safe_load(f)

    working_directory = config["working_directory"]
    simulation_directory = config["simulation_directory"]
    years = config["atmosphere"]["years"]
    atm_vars = config["atmosphere"]["variables"]
    computed_vars = config["atmosphere"].get("computed_variables", [])
    prefix = config["atmosphere"]["prefix"]
    simulation_input_dir = os.path.join(simulation_directory, "input")

    t1 = datetime.strptime(config["domain"]["time"]["start"], "%Y-%m-%d")
    t2 = datetime.strptime(config["domain"]["time"]["end"], "%Y-%m-%d")

    # Process and write each variable one at a time to limit peak memory usage.
    # Each variable's dataset is opened, written in TIME_CHUNK slices, then closed
    # before the next variable is loaded.
    written = set()
    for var in atm_vars:
        mitgcm_name = var["mitgcm_name"]
        if mitgcm_name in written:
            continue
        written.add(mitgcm_name)

        print(f"Processing {mitgcm_name}...")
        scale_factor = var.get("scale_factor")

        ds = _open_var(working_directory, prefix, mitgcm_name, years, t1, t2)
        da = ds[mitgcm_name]
        if scale_factor is not None:
            da = da * scale_factor

        output_path = os.path.join(simulation_input_dir, f"{mitgcm_name}.bin")
        _write_chunked(da, output_path)
        ds.close()

    # Compute derived variables (e.g. specific humidity from dewpoint + surface pressure).
    # Only the two inputs are loaded at a time, also written in chunks.
    for cv in computed_vars:
        mitgcm_name = cv["mitgcm_name"]
        print(f"Computing {mitgcm_name}...")

        ds_d2m = _open_var(working_directory, prefix, "d2m", years, t1, t2)
        ds_sp = _open_var(working_directory, prefix, "sp", years, t1, t2)
        n_times = ds_d2m.sizes["valid_time"]

        output_path = os.path.join(simulation_input_dir, f"{mitgcm_name}.bin")
        with open(output_path, "wb") as f:
            for i in range(0, n_times, TIME_CHUNK):
                d2m_k = ds_d2m["d2m"].isel(valid_time=slice(i, i + TIME_CHUNK)).values
                sp_pa = ds_sp["sp"].isel(valid_time=slice(i, i + TIME_CHUNK)).values
                aqh = specific_humidity_from_dewpoint(
                    sp_pa * units.Pa, (d2m_k - 273.15) * units.degC
                )
                np.array(aqh).astype(">f4").tofile(f)

        ds_d2m.close()
        ds_sp.close()


if __name__ == "__main__":
    main()
