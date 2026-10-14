from pathlib import Path

COUNTRIES = {
    "HU": "hungary",
    "AT": "austria",
    "SK": "slovakia",
}

EXPECTED_COUNTRIES = set(COUNTRIES)
TIMEZONE = "Europe/Budapest"

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DIR = BASE_DIR / "data" / "processed"

# Everything that differs between datasets lives here
DATASETS = {
    "load": {
        "query_method": "query_load",
        "raw_value_column": "Actual Load",
        "value_column": "actual_load_mw",
        "key_columns": ["timestamp", "country_code"],
        "allow_missing_values": False,
        "strictly_positive": True,
    },
    "load_forecast": {
        "query_method": "query_load_forecast",
        "raw_value_column": "Forecasted Load",
        "value_column": "forecast_load_mw",
        "key_columns": ["timestamp", "country_code"],
        "allow_missing_values": False,
        "strictly_positive": True,
    },
    "generation": {
        "query_method": "query_generation",
        "value_column": "generation_mw",
        "key_columns": ["timestamp", "country_code", "energy_source"],
        "allow_missing_values": True,
        "strictly_positive": False,  # zero is allowed, negative is not
    },
    "day_ahead_prices": {
        "query_method": "query_day_ahead_prices",
        "raw_value_column": "Day Ahead Price",
        "value_column": "price_eur_mwh",
        "key_columns": ["timestamp", "country_code"],
        "allow_missing_values": False,
        "strictly_positive": False,
        "allow_negative_values": True,  # negative prices are real
    },
}


def raw_path(country_name, dataset, date_str):
    return RAW_DIR / f"{country_name}_{dataset}_{date_str}.csv"


def processed_path(dataset, date_str):
    return PROCESSED_DIR / f"all_countries_{dataset}_{date_str}.csv"