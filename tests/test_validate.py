
import sys
from pathlib import Path

import pandas as pd
import pytest

""""
sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "src")
)
"""

from config import DATASETS, EXPECTED_COUNTRIES, TIMEZONE
from validate import validate_dataset, check_missing_intervals


@pytest.fixture
def valid_load_data():
    """Create valid load data for every expected country."""
    cfg = DATASETS["load"]
    rows = []

    for country in sorted(EXPECTED_COUNTRIES):
        rows.append({
            "timestamp": "2026-10-01T00:00:00Z",
            "country_code": country,
            cfg["value_column"]: 4500.0,
        })

    return pd.DataFrame(rows)


def test_valid_load_data(valid_load_data, capsys):
    """Valid data should pass."""
    validate_dataset("load", valid_load_data)

    output = capsys.readouterr().out
    assert "validation successful" in output


def test_missing_required_column(valid_load_data):
    """A required column must not be missing."""
    data = valid_load_data.drop(columns=["timestamp"])

    with pytest.raises(ValueError, match="Missing required column"):
        validate_dataset("load", data)


def test_missing_key_value(valid_load_data):
    """Key columns cannot contain null values."""
    data = valid_load_data.copy()
    data.loc[0, "timestamp"] = None

    with pytest.raises(ValueError, match="Key columns contain missing values"):
        validate_dataset("load", data)


def test_missing_load_value(valid_load_data):
    """Load values cannot be missing."""
    data = valid_load_data.copy()
    value_column = DATASETS["load"]["value_column"]
    data.loc[0, value_column] = None

    with pytest.raises(ValueError, match="missing values"):
        validate_dataset("load", data)


def test_duplicate_record(valid_load_data):
    """Duplicate keys must be rejected."""
    data = pd.concat(
        [valid_load_data, valid_load_data.iloc[[0]]],
        ignore_index=True
    )

    with pytest.raises(ValueError, match="duplicate records"):
        validate_dataset("load", data)


@pytest.mark.parametrize("invalid_value", [0, -100, -4500])
def test_invalid_load_value(valid_load_data, invalid_value):
    """Load must be strictly positive."""
    data = valid_load_data.copy()
    value_column = DATASETS["load"]["value_column"]
    data.loc[0, value_column] = invalid_value

    with pytest.raises(ValueError, match="invalid"):
        validate_dataset("load", data)


def test_unexpected_country(valid_load_data):
    """Only the configured country set is accepted."""
    data = valid_load_data.copy()
    data.loc[0, "country_code"] = "XX"

    with pytest.raises(ValueError, match="Unexpected countries"):
        validate_dataset("load", data)


def test_generation_missing_value_allowed(capsys):
    """Missing generation values should produce a warning."""
    cfg = DATASETS["generation"]
    rows = []

    for country in sorted(EXPECTED_COUNTRIES):
        rows.append({
            "timestamp": "2026-10-01T00:00:00Z",
            "country_code": country,
            "energy_source": "Solar",
            cfg["value_column"]: 100.0,
        })

    data = pd.DataFrame(rows)
    data.loc[0, cfg["value_column"]] = None

    validate_dataset("generation", data)

    output = capsys.readouterr().out
    assert "WARNING:" in output
    assert "validation successful" in output


def test_negative_generation_rejected():
    """Negative generation values must be rejected."""
    cfg = DATASETS["generation"]
    rows = []

    for country in sorted(EXPECTED_COUNTRIES):
        rows.append({
            "timestamp": "2026-10-01T00:00:00Z",
            "country_code": country,
            "energy_source": "Solar",
            cfg["value_column"]: -10.0,
        })

    data = pd.DataFrame(rows)

    with pytest.raises(ValueError, match="invalid"):
        validate_dataset("generation", data)


def test_generation_missing_intervals_warning(capsys):
    """Incomplete generation timestamps should produce a warning."""
    data = pd.DataFrame({
        "timestamp": ["2026-10-01T00:00:00Z"],
        "country_code": [sorted(EXPECTED_COUNTRIES)[0]],
    })

    check_missing_intervals(data, "generation", "2026-10-01")

    output = capsys.readouterr().out
    assert "WARNING:" in output
    assert "missing 15-minute intervals" in output



@pytest.mark.parametrize(
    "date_str, expected_intervals",
    [
        ("2026-03-29", 92),   # Spring: 23-hour day
        ("2026-10-25", 100),  # Autumn: 25-hour day
    ]
)
def test_generation_daylight_saving_time(
    date_str, expected_intervals, capsys
):
    """Validate 15-minute intervals on DST transition days."""

    timestamps = pd.date_range(
        start=pd.Timestamp(date_str, tz="Europe/Budapest"),
        periods=expected_intervals,
        freq="15min",
    )

    # Confirm the timestamps belong to the selected local day
    assert all(
        timestamp.date() == pd.Timestamp(date_str).date()
        for timestamp in timestamps
    )

    rows = []

    for country in sorted(EXPECTED_COUNTRIES):
        for timestamp in timestamps:
            rows.append({
                "timestamp": timestamp.isoformat(),
                "country_code": country,
            })

    data = pd.DataFrame(rows)

    check_missing_intervals(data, "generation", date_str)

    output = capsys.readouterr().out

    assert "WARNING:" not in output
    assert output.count("All expected intervals present.") == len(
        EXPECTED_COUNTRIES
    )


def full_day_data(date_str):
    """Every expected country with every 15-minute interval of the local day."""
    local_start = pd.Timestamp(date_str, tz=TIMEZONE)

    timestamps = pd.date_range(
        start=local_start,
        end=local_start + pd.DateOffset(days=1),
        freq="15min",
        inclusive="left",
    )

    return pd.DataFrame([
        {"timestamp": timestamp.isoformat(), "country_code": country}
        for country in sorted(EXPECTED_COUNTRIES)
        for timestamp in timestamps
    ])


def test_load_complete_day_passes(capsys):
    """A complete day must not produce warnings or errors."""
    check_missing_intervals(full_day_data("2026-10-01"), "load", "2026-10-01")

    output = capsys.readouterr().out
    assert "WARNING:" not in output
    assert output.count("All expected intervals present.") == len(
        EXPECTED_COUNTRIES
    )


def test_load_missing_interval_is_rejected():
    """Datasets that do not allow gaps must fail on a missing interval."""
    data = full_day_data("2026-10-01").iloc[:-1]  # drop one interval

    with pytest.raises(ValueError, match="missing 15-minute intervals"):
        check_missing_intervals(data, "load", "2026-10-01")


@pytest.mark.parametrize("price", [-50.0, 0.0, 85.0])
def test_prices_allow_negative_and_zero(price, capsys):
    """Day-ahead prices may be negative or zero."""
    cfg = DATASETS["day_ahead_prices"]

    data = pd.DataFrame([
        {
            "timestamp": "2026-10-01T12:00:00Z",
            "country_code": country,
            cfg["value_column"]: price,
        }
        for country in sorted(EXPECTED_COUNTRIES)
    ])

    validate_dataset("day_ahead_prices", data)

    assert "validation successful" in capsys.readouterr().out
