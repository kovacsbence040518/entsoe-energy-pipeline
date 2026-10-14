import pandas as pd

from config import COUNTRIES, DATASETS, PROCESSED_DIR, raw_path, processed_path


def transform_single_series(input_path, country_code, dataset):
    """Load and load_forecast: one value column per country."""
    cfg = DATASETS[dataset]

    data = pd.read_csv(input_path)
    data = data.rename(columns={
        "Unnamed: 0": "timestamp",
        cfg["raw_value_column"]: cfg["value_column"],
    })

    data["timestamp"] = pd.to_datetime(data["timestamp"], utc=True)
    data["country_code"] = country_code

    return data[["timestamp", cfg["value_column"], "country_code"]]


def transform_generation(input_path, country_code):
    """Transform generation data from wide to long format.

    The API returns two file layouts:
    - two header rows (source name + "Actual Aggregated" / "Actual Consumption"):
      only the "Actual Aggregated" columns are kept;
    - one header row (some days, e.g. when a country has no consumption series):
      the columns carry no label, so every column is assumed to be generation.
    """

    # Read with two header rows first to find out which layout the file has
    data = pd.read_csv(input_path, header=[0, 1], index_col=0)

    if "Actual Aggregated" in data.columns.get_level_values(1):
        # Two header rows: keep only actual generation
        data = data.loc[
            :, data.columns.get_level_values(1) == "Actual Aggregated"
        ].copy()

        data.columns = data.columns.get_level_values(0)

    else:
        # One header row: read the file again with a single header
        data = pd.read_csv(input_path, index_col=0)

    data = data.reset_index()
    data = data.rename(columns={data.columns[0]: "timestamp"})

    data = data.melt(
        id_vars=["timestamp"],
        var_name="energy_source",
        value_name="generation_mw",
    )

    data["timestamp"] = pd.to_datetime(data["timestamp"], utc=True)
    data["country_code"] = country_code

    return data


def run_transform(dataset, date_str):
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    all_data = []

    for country_code, country_name in COUNTRIES.items():
        print(f"Transforming {dataset} data for {country_code}...")

        input_path = raw_path(country_name, dataset, date_str)

        if dataset == "generation":
            data = transform_generation(input_path, country_code)
        else:
            data = transform_single_series(input_path, country_code, dataset)

        all_data.append(data)
        print(f"Rows transformed: {len(data)}")

    combined = pd.concat(all_data, ignore_index=True)

    output_path = processed_path(dataset, date_str)
    combined.to_csv(output_path, index=False)

    print(f"Combined data saved to: {output_path} | total rows: {len(combined)}")