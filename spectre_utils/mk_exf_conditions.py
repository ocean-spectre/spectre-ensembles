import os
from spectre_utils import common
import yaml
from metpy.calc import specific_humidity_from_dewpoint
from metpy.units import units
from datetime import datetime

def main():

    args = common.cli()

    # Load configuration from YAML file
    with open(args.config_file, 'r') as f:
        config = yaml.safe_load(f)

    working_directory = config['working_directory']
    simulation_directory = config['simulation_directory']
    years = config['atmosphere']['years']
    atm_vars = config['atmosphere']['variables']
    computed_vars = config['atmosphere'].get('computed_variables', [])
    prefix = config['atmosphere']['prefix']
    simulation_input_dir = os.path.join(simulation_directory, 'input')

    t1 = datetime.strptime(config['domain']['time']['start'], "%Y-%m-%d")
    t2 = datetime.strptime(config['domain']['time']['end'], "%Y-%m-%d")

    ds = common.load_atm_dataset(working_directory, prefix, years, atm_vars, t1, t2)
    print(ds)

    # Compute specific humidity from dewpoint temperature and surface pressure
    d2m_celsius = ds["d2m"] - 273.15  # Convert from Kelvin to Celsius
    ds['aqh'] = specific_humidity_from_dewpoint(ds['sp'] * units.Pa, d2m_celsius * units.degC)

    # Write all configured variables to binary files
    written = set()
    for var in atm_vars:
        mitgcm_name = var["mitgcm_name"]
        if mitgcm_name in written:
            continue
        written.add(mitgcm_name)
        with open(os.path.join(simulation_input_dir, f'{mitgcm_name}.bin'), 'wb') as f:
            ds[mitgcm_name].values.astype('>f4').tofile(f)

    # Write computed variables
    for cv in computed_vars:
        mitgcm_name = cv["mitgcm_name"]
        with open(os.path.join(simulation_input_dir, f'{mitgcm_name}.bin'), 'wb') as f:
            ds[mitgcm_name].values.astype('>f4').tofile(f)
    
if __name__ == "__main__":
    main()
