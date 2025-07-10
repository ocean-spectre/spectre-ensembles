import copernicusmarine
from datetime import date, timedelta
import yaml
import os

def cli():
    import argparse
    # Get configuration file from command line
    parser = argparse.ArgumentParser(description="Download Copernicus Marine data for a specific date range.")
    parser.add_argument('config_file', type=str, help="Path to the configuration file.")
    return parser.parse_args()

def main():
    
    args = cli()

    # Load configuration from YAML file
    with open(args.config_file, 'r') as f:
        config = yaml.safe_load(f)

    # Get time range from configuration
    time_range = config.get('time')
    start_date = time_range.get('start')
    end_date = time_range.get('end')
    dataset_id = config.get('dataset_id')
    longitude_range = config.get('longitude')
    min_long = longitude_range.get('min')
    max_long = longitude_range.get('max')
    latitude_range = config.get('latitude')
    min_lat = latitude_range.get('min')
    max_lat = latitude_range.get('max')
    working_directory = config.get('working_directory', '.')
    dataset_prefix = config.get('dataset_prefix', 'copernicus_marine')

    if not os.path.exists(working_directory):
        os.makedirs(working_directory)

    copernicusmarine.subset(
        dataset_id=dataset_id,
        variables=[
            "thetao",  # Sea water potential temperature
            "so",  # Sea water salinity
            "uo",  # Eastward ocean current velocity
            "vo",  # Northward sea water velocity
            "zos",  # Sea Surface Height above Geoid
        ],
        minimum_longitude=min_long,
        maximum_longitude=max_long,
        minimum_latitude=min_lat,
        maximum_latitude=max_lat,
        start_datetime=start_date,
        end_datetime=start_date,
        output_filename=f"{dataset_prefix}_{start_date}.nc",
        output_directory=working_directory,
    )

if __name__ == "__main__":
    main()