
import sys
from pathlib import Path
from unittest.mock import MagicMock, call

import pandas as pd
import pytest


"""
sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "src")
)
"""

import extract
from config import DATASETS


@pytest.fixture
def extraction_setup(tmp_path, monkeypatch):
    """Use a temporary folder and two sample countries."""

    raw_dir = tmp_path / "raw"

    countries = {
        "HU": "Hungary",
        "AT": "Austria",
    }

    monkeypatch.setattr(extract, "RAW_DIR", raw_dir)
    monkeypatch.setattr(extract, "COUNTRIES", countries)

    monkeypatch.setattr(
        extract,
        "raw_path",
        lambda country_name, dataset, date_str: (
            raw_dir / f"{country_name}_{dataset}_{date_str}.csv"
        ),
    )

    return raw_dir


def test_extract_dataframe(extraction_setup):
    """API DataFrame results should be saved for both countries."""

    timestamps = pd.date_range(
        "2026-10-01T00:00:00Z",
        periods=3,
        freq="15min",
    )

    raw_column = DATASETS["load"]["raw_value_column"]

    api_response = pd.DataFrame(
        {raw_column: [4000.0, 4100.0, 4200.0]},
        index=timestamps,
    )

    client = MagicMock()
    client.query_load.return_value = api_response

    start = pd.Timestamp("2026-10-01T00:00:00Z")
    end = pd.Timestamp("2026-10-01T01:00:00Z")

    extract.extract_dataset(
        client,
        "load",
        start,
        end,
        "2026-10-01",
    )

    assert (extraction_setup / "Hungary_load_2026-10-01.csv").exists()
    assert (extraction_setup / "Austria_load_2026-10-01.csv").exists()

    client.query_load.assert_has_calls(
        [
            call(country_code="HU", start=start, end=end),
            call(country_code="AT", start=start, end=end),
        ]
    )

    assert client.query_load.call_count == 2


def test_extract_end_is_exclusive(extraction_setup):
    """The timestamp equal to end must be excluded."""

    timestamps = pd.date_range(
        "2026-10-01T00:00:00Z",
        periods=3,
        freq="15min",
    )

    raw_column = DATASETS["load"]["raw_value_column"]

    api_response = pd.DataFrame(
        {raw_column: [4000.0, 4100.0, 4200.0]},
        index=timestamps,
    )

    client = MagicMock()
    client.query_load.return_value = api_response

    extract.extract_dataset(
        client,
        "load",
        pd.Timestamp("2026-10-01T00:00:00Z"),
        pd.Timestamp("2026-10-01T00:30:00Z"),
        "2026-10-01",
    )

    output = pd.read_csv(
        extraction_setup / "Hungary_load_2026-10-01.csv"
    )

    assert len(output) == 2
    assert output[raw_column].tolist() == [4000.0, 4100.0]


def test_extract_series_conversion(extraction_setup):
    """A pandas Series should be converted into a DataFrame."""

    timestamps = pd.date_range(
        "2026-10-01T00:00:00Z",
        periods=2,
        freq="15min",
    )

    api_response = pd.Series(
        [100.0, 110.0],
        index=timestamps,
    )

    client = MagicMock()
    client.query_load.return_value = api_response

    extract.extract_dataset(
        client,
        "load",
        pd.Timestamp("2026-10-01T00:00:00Z"),
        pd.Timestamp("2026-10-01T01:00:00Z"),
        "2026-10-01",
    )

    output = pd.read_csv(
        extraction_setup / "Hungary_load_2026-10-01.csv",
        index_col=0,
    )

    expected_column = DATASETS["load"]["raw_value_column"]

    assert list(output.columns) == [expected_column]
    assert output[expected_column].tolist() == [100.0, 110.0]


def test_extract_creates_raw_directory(extraction_setup):
    """The raw directory should be created automatically."""

    assert not extraction_setup.exists()

    raw_column = DATASETS["load"]["raw_value_column"]

    client = MagicMock()
    client.query_load.return_value = pd.DataFrame(
        {raw_column: [4500.0]},
        index=pd.DatetimeIndex(["2026-10-01T00:00:00Z"]),
    )

    extract.extract_dataset(
        client,
        "load",
        pd.Timestamp("2026-10-01T00:00:00Z"),
        pd.Timestamp("2026-10-01T01:00:00Z"),
        "2026-10-01",
    )

    assert extraction_setup.is_dir()

def test_extract_prices_series(extraction_setup):
    """The prices query returns a Series: it must be saved with the
    column name the transform step expects."""

    timestamps = pd.date_range(
        "2026-10-01T00:00:00Z",
        periods=2,
        freq="15min",
    )

    client = MagicMock()
    client.query_day_ahead_prices.return_value = pd.Series(
        [-5.0, 80.0],
        index=timestamps,
    )

    extract.extract_dataset(
        client,
        "day_ahead_prices",
        pd.Timestamp("2026-10-01T00:00:00Z"),
        pd.Timestamp("2026-10-01T01:00:00Z"),
        "2026-10-01",
    )

    output = pd.read_csv(
        extraction_setup / "Hungary_day_ahead_prices_2026-10-01.csv",
        index_col=0,
    )

    expected_column = DATASETS["day_ahead_prices"]["raw_value_column"]

    assert list(output.columns) == [expected_column]
    assert output[expected_column].tolist() == [-5.0, 80.0]