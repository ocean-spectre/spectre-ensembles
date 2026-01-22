import cdsapi
import os
from spectre_utils import common
import yaml

def main():
    
    args = common.cli()

    # Load configuration from YAML file
    with open(args.config_file, 'r') as f:
        config = yaml.safe_load(f)

    working_directory = config['working_directory']
    years= config['atmosphere']['years']
    vars= config['atmosphere']['variables']
    prefix = config['atmosphere']['prefix']

    dataset = "reanalysis-era5-single-levels"
    client = cdsapi.Client()

    # Create working_directory directory if it doesn't exist
    if not os.path.exists(working_directory):
        os.makedirs(working_directory)
    for var in vars:
        era_name = var["era_name"]
        mitgcm_name = var["mitgcm_name"]
        for year in years:
            request = {
            "product_type": ["reanalysis"],
            "variable": [era_name],
            "year": [year],
            "month": [
                "01", "02", "03",
                "04", "05", "06",
                "07", "08", "09",
                "10", "11", "12"
            ],
            "day": [
                "01", "02", "03",
                "04", "05", "06",
                "07", "08", "09",
                "10", "11", "12",
                "13", "14", "15",
                "16", "17", "18",
                "19", "20", "21",
                "22", "23", "24",
                "25", "26", "27",
                "28", "29", "30",
                "31"
            ],
            "time": [
                "00:00", "03:00", "06:00",
                "09:00", "12:00", "15:00",
                "18:00", "21:00"
            ],
            "data_format": "netcdf",
            "download_format": "unarchived",
            "area": [60, -90, 20, -10]
            }
            target = f"{working_directory}/{prefix}_{mitgcm_name}_{year}.nc"
            print(f"Downloading {target} ...")
            if os.path.exists(target):
                print(f"File {target} already exists. Skipping download.")
                continue
            client.retrieve(dataset, request, target)

if __name__ == "__main__":
    main()
