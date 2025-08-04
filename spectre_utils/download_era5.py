import cdsapi

years= [
        "2002", "2003", "2004",
        "2005", "2006", "2007",
        "2008", "2009", "2010",
        "2011", "2012", "2013",
        "2014", "2015", "2016",
        "2017", "2018", "2019",
        "2020", "2021", "2022",
        "2023"
    ]
vars= {"10m_u_component_of_wind":"u10",
        "10m_v_component_of_wind":"v10",
        "2m_dewpoint_temperature":"d2m",
        "2m_temperature":"t2m",
        "total_precipitation":"precip",
        "mean_surface_downward_short_wave_radiation_flux":"ssrd",
        "mean_surface_net_long_wave_radiation_flux":"slrd"}

dataset = "reanalysis-era5-single-levels"
client = cdsapi.Client()

for var in vars.keys():
    for year in years:
        request = {
        "product_type": ["reanalysis"],
        "variable": [var],
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
        target = vars[var] + "_" + year + ".nc"
        request["target"] = target
        print(f"Downloading {target}...")

        client.retrieve(dataset, request).download()