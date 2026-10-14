
import sys
from pathlib import Path

import pandas as pd

"""
# Allow importing the existing modules from src/
sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "src")
)"""

from config import DATASETS
from transform import transform_single_series, transform_generation


def test_transform_load(tmp_path):
    """Test load data transformation."""

    cfg = DATASETS["load"]

    input_path = tmp_path / "load.csv"

    raw_data = pd.DataFrame({
        "Unnamed: 0": [
            "2026-10-01 00:00:00+00:00",
            "2026-10-01 00:15:00+00:00"
        ],
        cfg["raw_value_column"]: [4500.0, 4600.0]
    })

    raw_data.to_csv(input_path, index=False)

    result = transform_single_series(input_path, "HU", "load")

    assert len(result) == 2
    assert list(result.columns) == [
        "timestamp",
        cfg["value_column"],
        "country_code"
    ]
    assert result["country_code"].tolist() == ["HU", "HU"]
    assert result[cfg["value_column"]].tolist() == [4500.0, 4600.0]
    assert str(result["timestamp"].dt.tz) == "UTC"


def test_transform_load_forecast(tmp_path):
    """Test forecast data transformation."""

    cfg = DATASETS["load_forecast"]

    input_path = tmp_path / "forecast.csv"

    raw_data = pd.DataFrame({
        "Unnamed: 0": ["2026-10-01 00:00:00+00:00"],
        cfg["raw_value_column"]: [4700.0]
    })

    raw_data.to_csv(input_path, index=False)

    result = transform_single_series(
        input_path,
        "AT",
        "load_forecast"
    )

    assert len(result) == 1
    assert result["country_code"].iloc[0] == "AT"
    assert result[cfg["value_column"]].iloc[0] == 4700.0
    assert str(result["timestamp"].dt.tz) == "UTC"


def test_transform_generation(tmp_path):
    """Test generation data transformation from wide to long."""

    input_path = tmp_path / "generation.csv"

    columns = pd.MultiIndex.from_tuples([
        ("Solar", "Actual Aggregated"),
        ("Wind Onshore", "Actual Aggregated"),
        ("Solar", "Actual Consumption")
    ])

    raw_data = pd.DataFrame(
        [
            [100.0, 200.0, 5.0],
            [110.0, 210.0, 6.0]
        ],
        index=[
            "2026-10-01 00:00:00+00:00",
            "2026-10-01 00:15:00+00:00"
        ],
        columns=columns
    )

    raw_data.to_csv(input_path)

    result = transform_generation(input_path, "SK")

    assert len(result) == 4
    assert set(result["energy_source"]) == {
        "Solar",
        "Wind Onshore"
    }
    assert set(result["generation_mw"]) == {
        100.0, 110.0, 200.0, 210.0
    }
    assert (result["country_code"] == "SK").all()
    assert str(result["timestamp"].dt.tz) == "UTC"

def test_transform_generation_single_header(tmp_path):
    """Regression: some days the API returns a file with ONE header row
    (no consumption series), e.g. Hungary on 2026-10-07."""

    input_path = tmp_path / "generation_single.csv"

    raw_data = pd.DataFrame(
        {
            "Solar": [100.0, 110.0, 120.0],
            "Wind Onshore": [200.0, 210.0, 220.0],
        },
        index=[
            "2026-10-07 00:00:00+00:00",
            "2026-10-07 00:15:00+00:00",
            "2026-10-07 00:30:00+00:00",
        ],
    )

    raw_data.to_csv(input_path)

    result = transform_generation(input_path, "HU")

    assert len(result) == 6
    assert set(result["energy_source"]) == {"Solar", "Wind Onshore"}
    assert set(result["generation_mw"]) == {
        100.0, 110.0, 120.0, 200.0, 210.0, 220.0
    }
    assert (result["country_code"] == "HU").all()
    assert str(result["timestamp"].dt.tz) == "UTC"


def test_transform_prices_keeps_negative_values(tmp_path):
    """Negative day-ahead prices are valid and must not be changed."""

    cfg = DATASETS["day_ahead_prices"]

    input_path = tmp_path / "prices.csv"

    raw_data = pd.DataFrame({
        "Unnamed: 0": [
            "2026-10-01 12:00:00+00:00",
            "2026-10-01 12:15:00+00:00",
        ],
        cfg["raw_value_column"]: [-12.5, 80.0],
    })

    raw_data.to_csv(input_path, index=False)

    result = transform_single_series(input_path, "AT", "day_ahead_prices")

    assert list(result.columns) == [
        "timestamp",
        cfg["value_column"],
        "country_code",
    ]
    assert result[cfg["value_column"]].tolist() == [-12.5, 80.0]
    assert (result["country_code"] == "AT").all()
