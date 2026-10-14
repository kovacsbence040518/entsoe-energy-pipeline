import pandas as pd

from config import COUNTRIES, DATASETS, RAW_DIR, raw_path


def extract_dataset(client, dataset, start, end, date_str):
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    # e.g. client.query_load, client.query_generation
    query = getattr(client, DATASETS[dataset]["query_method"])

    for country_code, country_name in COUNTRIES.items():
        print(f"Extracting {dataset} data for {country_code}...")

        data = query(country_code=country_code, start=start, end=end)

        # Some queries (e.g. prices) return a Series instead of a DataFrame
        if isinstance(data, pd.Series):
            data = data.to_frame(name=DATASETS[dataset]["raw_value_column"])

        # Keep only timestamps inside the requested window (end is exclusive)
        data = data[data.index < end]

        output_path = raw_path(country_name, dataset, date_str)
        data.to_csv(output_path)

        print(f"Saved to: {output_path} | shape: {data.shape}")