"""Manual integration test for the Snowflake loader.

Runs against the real Snowflake account (uses a few credits), but ONLY in the
ENERGY_DB.ETL_TEST schema. pytest does not collect this file. Run it with:

    python tests/integration_test_snowflake.py

Requirements:
- ENERGY_DB.ETL_TEST.LOAD exists (see 01_setup.sql)
- data/processed/all_countries_load_2026-10-01.csv exists
  (run the pipeline once for 2026-10-01 first)
"""

import os
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

# Load credentials without modifying the .env file
load_dotenv(ROOT / ".env")

# Force this script to use ONLY the test schema
os.environ["SNOWFLAKE_SCHEMA"] = "ETL_TEST"

from config import processed_path
from snowflake_load import get_connection, load_dataset


TEST_DATE = "2026-10-01"
TEST_TABLE = "ENERGY_DB.ETL_TEST.LOAD"
EXPECTED_ROWS = 288


def run_sql(conn, sql):
    cursor = conn.cursor()
    try:
        cursor.execute(sql)
        return cursor.fetchone() if cursor.description else None
    finally:
        cursor.close()


def get_row_count(conn):
    return run_sql(conn, f"SELECT COUNT(*) FROM {TEST_TABLE}")[0]


def main():
    # Verify input file before connecting
    csv_path = processed_path("load", TEST_DATE)
    data = pd.read_csv(csv_path)

    if len(data) != EXPECTED_ROWS:
        raise ValueError(
            f"Expected {EXPECTED_ROWS} CSV rows, got {len(data)}"
        )

    timestamps = pd.to_datetime(data["timestamp"], utc=True)
    local_dates = timestamps.dt.tz_convert(
        "Europe/Budapest"
    ).dt.strftime("%Y-%m-%d")

    if not (local_dates == TEST_DATE).all():
        raise ValueError(
            "CSV contains timestamps outside the requested local day"
        )

    conn = get_connection()

    try:
        database, schema = run_sql(
            conn, "SELECT CURRENT_DATABASE(), CURRENT_SCHEMA()"
        )

        # Safety check: never run against production RAW
        if database.upper() != "ENERGY_DB" or schema.upper() != "ETL_TEST":
            raise RuntimeError(
                f"Unsafe connection: {database}.{schema}"
            )

        print(f"Connected to: {database}.{schema}")

        before = get_row_count(conn)
        print(f"Before loading: {before} rows")

        if before != 0:
            raise RuntimeError(
                "Test table is not empty. Aborting to avoid "
                "modifying existing test data."
            )

        try:
            print("\n--- FIRST LOAD ---")
            load_dataset(conn, "load", TEST_DATE)

            first_count = get_row_count(conn)
            print(f"After first load: {first_count} rows")
            assert first_count == EXPECTED_ROWS

            # Re-run the same day: must not create duplicates
            print("\n--- SECOND LOAD ---")
            load_dataset(conn, "load", TEST_DATE)

            second_count = get_row_count(conn)
            print(f"After second load: {second_count} rows")
            assert second_count == EXPECTED_ROWS

            print("\nINTEGRATION TEST PASSED")

        finally:
            # The safety check above guarantees this is the test table
            run_sql(conn, f"TRUNCATE TABLE {TEST_TABLE}")
            print("Test table cleaned up.")

    finally:
        conn.close()


if __name__ == "__main__":
    main()