import pandas as pd

from config import DATASETS, EXPECTED_COUNTRIES, TIMEZONE, processed_path


def check_missing_intervals(data, dataset, date_str):
    """Check that every country has every 15-minute interval of the local day.

    Datasets that allow missing values (generation) only produce a warning.
    All other datasets fail, because a gap would silently distort the analysis.
    """
    timestamps = pd.to_datetime(data["timestamp"], utc=True)
    local_dates = timestamps.dt.tz_convert(TIMEZONE).dt.date
    target_date = pd.Timestamp(date_str).date()

    local_start = pd.Timestamp(date_str, tz=TIMEZONE)
    expected = pd.date_range(
        start=local_start,
        end=local_start + pd.DateOffset(days=1),
        freq="15min",
        inclusive="left",
    )

    for country in sorted(EXPECTED_COUNTRIES):
        actual = timestamps[
            (data["country_code"] == country) & (local_dates == target_date)
        ].dt.tz_convert(TIMEZONE)

        missing = expected.difference(pd.DatetimeIndex(actual.unique()))

        if len(missing) == 0:
            print(f"{dataset} - {country} - {date_str}: All expected intervals present.")
            continue

        message = (
            f"{dataset} - {country} - {date_str}: "
            f"{len(missing)} missing 15-minute intervals."
        )

        if DATASETS[dataset]["allow_missing_values"]:
            print(f"WARNING: {message}")
        else:
            raise ValueError(message)


def validate_dataset(dataset, data):
    cfg = DATASETS[dataset]
    key_columns = cfg["key_columns"]
    value_column = cfg["value_column"]

    # 1. Required columns
    for column in key_columns + [value_column]:
        if column not in data.columns:
            raise ValueError(f"Missing required column: {column}")

    # 2. Key columns can never be missing
    if data[key_columns].isna().any().any():
        raise ValueError("Key columns contain missing values.")

    # 3. Missing values in the value column: warn or fail, depending on dataset
    missing = data[data[value_column].isna()]
    if len(missing) > 0:
        if not cfg["allow_missing_values"]:
            raise ValueError(f"{len(missing)} missing values in {value_column}.")

        print(f"WARNING: {len(missing)} {value_column} values are missing.")
        group_columns = [c for c in key_columns if c != "timestamp"]
        print(missing.groupby(group_columns).size())

    # 4. Duplicates
    duplicate_count = data.duplicated(subset=key_columns).sum()
    if duplicate_count > 0:
        raise ValueError(f"Dataset contains {duplicate_count} duplicate records.")

    # 5. Value range
    values = data[value_column].dropna()
    if cfg["strictly_positive"]:
        invalid_count = (values <= 0).sum()
    elif cfg.get("allow_negative_values", False):
        invalid_count = 0
    else:
        invalid_count = (values < 0).sum()

    if invalid_count > 0:
        raise ValueError(f"Dataset contains {invalid_count} invalid {value_column} values.")

    # 6. Countries
    actual_countries = set(data["country_code"].unique())
    if actual_countries != EXPECTED_COUNTRIES:
        raise ValueError(f"Unexpected countries: {actual_countries}")

    print(f"{dataset} validation successful. Rows validated: {len(data)}")


def run_validation(dataset, date_str):
    data = pd.read_csv(processed_path(dataset, date_str))

    validate_dataset(dataset, data)

    check_missing_intervals(data, dataset, date_str)