from datetime import timedelta
from unittest.mock import MagicMock

import pandas as pd
import pytest

import snowflake_load
from config import DATASETS


@pytest.fixture
def loader_setup(monkeypatch, tmp_path):
    """Provide a real CSV file and mocked Snowflake operations."""

    monkeypatch.setenv("SNOWFLAKE_DATABASE", "ENERGY_DB")
    monkeypatch.setenv("SNOWFLAKE_SCHEMA", "RAW")

    # Every dataset is read from <tmp_path>/<dataset>.csv
    monkeypatch.setattr(
        snowflake_load,
        "processed_path",
        lambda name, date: tmp_path / f"{name}.csv",
    )

    def setup(dataset="load", data=None):
        cfg = DATASETS[dataset]

        if data is None:
            columns = {
                "timestamp": [
                    "2026-10-01T00:00:00Z",
                    "2026-10-01T00:15:00Z",
                ],
                "country_code": ["HU", "HU"],
                cfg["value_column"]: [4500.0, 4600.0],
            }

            if "energy_source" in cfg["key_columns"]:
                columns["energy_source"] = ["Solar", "Solar"]

            data = pd.DataFrame(columns)

        data.to_csv(tmp_path / f"{dataset}.csv", index=False)

        events = []

        conn = MagicMock()
        cursor = conn.cursor.return_value
        cursor.rowcount = len(data)

        def execute(sql, *args):
            operation = sql.strip().split()[0].upper()
            events.append(operation)
            return cursor

        cursor.execute.side_effect = execute

        def upload(*args, **kwargs):
            events.append("UPLOAD")
            return True, 1, len(data), None

        writer = MagicMock(side_effect=upload)

        monkeypatch.setattr(
            snowflake_load,
            "write_pandas",
            writer,
        )

        return conn, cursor, writer, events, data

    return setup


# --------------------------------------------------
# 1. Successful loading
# --------------------------------------------------

@pytest.mark.parametrize("dataset", list(DATASETS))
def test_load_dataset_success(loader_setup, dataset):
    """All datasets should load into the correct tables."""

    conn, cursor, writer, events, data = loader_setup(dataset)

    snowflake_load.load_dataset(
        conn,
        dataset,
        "2026-10-01",
    )

    assert events == [
        "CREATE",
        "UPLOAD",
        "BEGIN",
        "DELETE",
        "INSERT",
        "COMMIT",
        "DROP",
    ]

    writer.assert_called_once()

    args, kwargs = writer.call_args

    assert args[0] is conn
    assert kwargs["table_name"].startswith(
        f"TMP_{dataset.upper()}_"
    )
    assert kwargs["database"] == "ENERGY_DB"
    assert kwargs["schema"] == "RAW"
    assert kwargs["use_logical_type"] is True

    uploaded = args[1]

    assert len(uploaded) == len(data)
    assert all(column.isupper() for column in uploaded.columns)
    assert str(uploaded["TIMESTAMP"].dt.tz) == "UTC"

    statements = [
        item.args[0]
        for item in cursor.execute.call_args_list
    ]

    assert any(
        f"DELETE FROM ENERGY_DB.RAW.{dataset.upper()}"
        in sql
        for sql in statements
    )

    cursor.close.assert_called_once()


# --------------------------------------------------
# 2. Staging upload failures
# --------------------------------------------------

def test_staging_upload_failure(loader_setup):
    """Failed staging upload must not delete existing data."""

    conn, cursor, writer, events, _ = loader_setup()

    writer.side_effect = None
    writer.return_value = (False, 1, 0, None)

    with pytest.raises(RuntimeError, match="staging upload failed"):
        snowflake_load.load_dataset(
            conn, "load", "2026-10-01"
        )

    assert events == ["CREATE", "DROP"]
    assert "DELETE" not in events
    assert "BEGIN" not in events

    cursor.close.assert_called_once()


def test_incomplete_staging_upload(loader_setup):
    """Uploading fewer rows than expected must fail safely."""

    conn, cursor, writer, events, _ = loader_setup()

    writer.side_effect = None
    writer.return_value = (True, 1, 1, None)

    with pytest.raises(RuntimeError, match="staging upload failed"):
        snowflake_load.load_dataset(
            conn, "load", "2026-10-01"
        )

    assert "DELETE" not in events
    assert "BEGIN" not in events
    assert "DROP" in events


# --------------------------------------------------
# 3. Transactions and rollback
# --------------------------------------------------

def test_insert_failure_causes_rollback(loader_setup):
    """An INSERT error must roll back the deletion."""

    conn, cursor, writer, events, _ = loader_setup()

    original_execute = cursor.execute.side_effect

    def failing_execute(sql, *args):
        if sql.startswith("INSERT INTO"):
            events.append("INSERT")
            raise RuntimeError("Simulated INSERT failure")

        return original_execute(sql, *args)

    cursor.execute.side_effect = failing_execute

    with pytest.raises(
        RuntimeError, match="Simulated INSERT failure"
    ):
        snowflake_load.load_dataset(
            conn, "load", "2026-10-01"
        )

    assert events == [
        "CREATE",
        "UPLOAD",
        "BEGIN",
        "DELETE",
        "INSERT",
        "ROLLBACK",
        "DROP",
    ]

    assert "COMMIT" not in events
    cursor.close.assert_called_once()


def test_incorrect_insert_count_causes_rollback(loader_setup):
    """A row-count mismatch must roll back the transaction."""

    conn, cursor, writer, events, _ = loader_setup()

    original_execute = cursor.execute.side_effect

    def incorrect_insert_count(sql, *args):
        result = original_execute(sql, *args)

        if sql.startswith("INSERT INTO"):
            cursor.rowcount = 1

        return result

    cursor.execute.side_effect = incorrect_insert_count

    with pytest.raises(RuntimeError, match="expected 2 inserted rows"):
        snowflake_load.load_dataset(
            conn, "load", "2026-10-01"
        )

    assert "ROLLBACK" in events
    assert "COMMIT" not in events
    assert events[-1] == "DROP"


def test_staging_creation_failure(loader_setup):
    """A failed CREATE must not start a transaction."""

    conn, cursor, writer, events, _ = loader_setup()

    def failing_create(sql, *args):
        events.append(sql.split()[0].upper())
        raise RuntimeError("CREATE failed")

    cursor.execute.side_effect = failing_create

    with pytest.raises(RuntimeError, match="CREATE failed"):
        snowflake_load.load_dataset(
            conn, "load", "2026-10-01"
        )

    assert events == ["CREATE"]
    writer.assert_not_called()
    cursor.close.assert_called_once()


# --------------------------------------------------
# 4. Input validation
# --------------------------------------------------

def test_empty_csv_rejected(loader_setup):
    """An empty CSV must be rejected before database changes."""

    empty = pd.DataFrame(
        columns=[
            "timestamp",
            "country_code",
            "actual_load_mw",
        ]
    )

    conn, cursor, writer, events, _ = loader_setup(
        data=empty
    )

    with pytest.raises(ValueError, match="CSV is empty"):
        snowflake_load.load_dataset(
            conn, "load", "2026-10-01"
        )

    assert events == []
    writer.assert_not_called()


def test_missing_csv_column(loader_setup):
    """Missing required columns must fail before staging."""

    data = pd.DataFrame({
        "timestamp": ["2026-10-01T00:00:00Z"],
        "country_code": ["HU"],
    })

    conn, cursor, writer, events, _ = loader_setup(
        data=data
    )

    with pytest.raises(ValueError, match="missing columns"):
        snowflake_load.load_dataset(
            conn, "load", "2026-10-01"
        )

    assert events == []
    writer.assert_not_called()


def test_timestamp_outside_requested_day(loader_setup):
    """Unexpected dates must be rejected."""

    data = pd.DataFrame({
        "timestamp": ["2026-10-02T00:00:00Z"],
        "country_code": ["HU"],
        "actual_load_mw": [4500.0],
    })

    conn, cursor, writer, events, _ = loader_setup(
        data=data
    )

    with pytest.raises(ValueError, match="outside"):
        snowflake_load.load_dataset(
            conn, "load", "2026-10-01"
        )

    assert events == []
    writer.assert_not_called()


# --------------------------------------------------
# 5. Budapest timezone and daylight saving
# --------------------------------------------------

@pytest.mark.parametrize(
    "date_str, expected_hours",
    [
        ("2026-03-29", 23),
        ("2026-10-01", 24),
        ("2026-10-25", 25),
    ]
)
def test_day_boundaries(date_str, expected_hours):
    """UTC boundaries must handle Budapest DST correctly."""

    start, end = snowflake_load.get_day_boundaries(
        date_str
    )

    assert (end - start) == timedelta(
        hours=expected_hours
    )

    assert start.tz_convert(
        "Europe/Budapest"
    ).date() == pd.Timestamp(date_str).date()

    assert end.tz_convert(
        "Europe/Budapest"
    ).date() == (
        pd.Timestamp(date_str) + timedelta(days=1)
    ).date()


@pytest.mark.parametrize(
    "date_str, expected_hours",
    [
        ("2026-03-29", 23),
        ("2026-10-25", 25),
    ]
)
def test_delete_uses_full_local_day(
    loader_setup, date_str, expected_hours, monkeypatch
):
    """DELETE must cover the entire Budapest day."""

    start, end = snowflake_load.get_day_boundaries(
        date_str
    )

    data = pd.DataFrame({
        "timestamp": [
            (start + timedelta(minutes=15)).isoformat(),
            (start + timedelta(minutes=30)).isoformat(),
        ],
        "country_code": ["HU", "HU"],
        "actual_load_mw": [4500.0, 4600.0],
    })

    conn, cursor, writer, events, _ = loader_setup(
        data=data
    )

    snowflake_load.load_dataset(
        conn, "load", date_str
    )

    delete_call = next(
        item
        for item in cursor.execute.call_args_list
        if item.args[0].startswith("DELETE FROM")
    )

    sql, params = delete_call.args

    assert "TIMESTAMP >=" in sql
    assert "TIMESTAMP < TO_TIMESTAMP_TZ" in sql

    assert params == (
        start.isoformat(),
        end.isoformat(),
    )

    assert end - start == timedelta(
        hours=expected_hours
    )

# --------------------------------------------------
# 6. All datasets in one transaction
# --------------------------------------------------

def write_forecast_csv(tmp_path):
    """Second dataset for the multi-dataset tests."""
    pd.DataFrame({
        "timestamp": ["2026-10-01T00:00:00Z", "2026-10-01T00:15:00Z"],
        "country_code": ["HU", "HU"],
        "forecast_load_mw": [4400.0, 4500.0],
    }).to_csv(tmp_path / "load_forecast.csv", index=False)


def test_all_datasets_committed_in_one_transaction(loader_setup, tmp_path):
    """Two datasets share ONE transaction: one BEGIN, one COMMIT."""

    conn, cursor, writer, events, _ = loader_setup("load")
    write_forecast_csv(tmp_path)

    snowflake_load.load_datasets(
        conn, ["load", "load_forecast"], "2026-10-01"
    )

    assert events == [
        "CREATE", "UPLOAD",
        "CREATE", "UPLOAD",
        "BEGIN",
        "DELETE", "INSERT",
        "DELETE", "INSERT",
        "COMMIT",
        "DROP", "DROP",
    ]


def test_failure_in_second_dataset_rolls_back_first(loader_setup, tmp_path):
    """If the second dataset fails, the first one is rolled back too."""

    conn, cursor, writer, events, _ = loader_setup("load")
    write_forecast_csv(tmp_path)

    original_execute = cursor.execute.side_effect
    insert_count = []

    def fail_on_second_insert(sql, *args):
        if sql.startswith("INSERT INTO"):
            insert_count.append(sql)

            if len(insert_count) == 2:
                events.append("INSERT")
                raise RuntimeError("Simulated INSERT failure")

        return original_execute(sql, *args)

    cursor.execute.side_effect = fail_on_second_insert

    with pytest.raises(RuntimeError, match="Simulated INSERT failure"):
        snowflake_load.load_datasets(
            conn, ["load", "load_forecast"], "2026-10-01"
        )

    assert events == [
        "CREATE", "UPLOAD",
        "CREATE", "UPLOAD",
        "BEGIN",
        "DELETE", "INSERT",
        "DELETE", "INSERT",
        "ROLLBACK",
        "DROP", "DROP",
    ]
    assert "COMMIT" not in events


def test_bad_second_csv_changes_nothing(loader_setup, tmp_path):
    """A bad CSV is found before anything is created in Snowflake."""

    conn, cursor, writer, events, _ = loader_setup("load")

    pd.DataFrame(
        columns=["timestamp", "country_code", "forecast_load_mw"]
    ).to_csv(tmp_path / "load_forecast.csv", index=False)

    with pytest.raises(ValueError, match="CSV is empty"):
        snowflake_load.load_datasets(
            conn, ["load", "load_forecast"], "2026-10-01"
        )

    assert events == []
    writer.assert_not_called()


# --------------------------------------------------
# 7. Connection management
# --------------------------------------------------

def test_connection_closes_after_success(monkeypatch):
    """Load all datasets together, then close the connection."""

    conn = MagicMock()
    loader = MagicMock()

    monkeypatch.setattr(
        snowflake_load, "get_connection", lambda: conn
    )
    monkeypatch.setattr(
        snowflake_load, "load_datasets", loader
    )

    snowflake_load.run_snowflake_load("2026-10-01")

    loader.assert_called_once_with(
        conn, list(DATASETS), "2026-10-01"
    )
    conn.close.assert_called_once()


def test_connection_closes_after_failure(monkeypatch):
    """Close the connection even when loading fails."""

    conn = MagicMock()

    monkeypatch.setattr(
        snowflake_load, "get_connection", lambda: conn
    )

    monkeypatch.setattr(
        snowflake_load,
        "load_datasets",
        MagicMock(side_effect=RuntimeError("Load failed")),
    )

    with pytest.raises(RuntimeError, match="Load failed"):
        snowflake_load.run_snowflake_load("2026-10-01")

    conn.close.assert_called_once()