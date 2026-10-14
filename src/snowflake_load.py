import os
import re
from uuid import uuid4

import pandas as pd
import snowflake.connector
from dotenv import load_dotenv
from snowflake.connector.pandas_tools import write_pandas

from config import DATASETS, TIMEZONE, processed_path


def get_connection():
    """Create a Snowflake connection."""
    load_dotenv()

    return snowflake.connector.connect(
        account=os.getenv("SNOWFLAKE_ACCOUNT"),
        user=os.getenv("SNOWFLAKE_USER"),
        password=os.getenv("SNOWFLAKE_PASSWORD"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE"),
        database=os.getenv("SNOWFLAKE_DATABASE"),
        schema=os.getenv("SNOWFLAKE_SCHEMA"),
    )


def safe_identifier(value):
    """Validate SQL identifiers used for database objects."""
    if not value or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError(f"Invalid Snowflake identifier: {value!r}")

    return value.upper()


def get_day_boundaries(date_str):
    """Return UTC boundaries for one Budapest calendar day.

    Handles 23-hour, 24-hour and 25-hour days.
    """
    local_start = pd.Timestamp(date_str, tz=TIMEZONE)
    local_end = local_start + pd.DateOffset(days=1)

    return (
        local_start.tz_convert("UTC"),
        local_end.tz_convert("UTC"),
    )


def prepare_dataset(dataset, date_str):
    """Read and check the processed CSV before anything touches Snowflake.

    Returns the data (upper-case column names) and the UTC day boundaries.
    """
    cfg = DATASETS[dataset]

    data = pd.read_csv(processed_path(dataset, date_str))

    if data.empty:
        raise ValueError(
            f"{dataset}: processed CSV is empty. "
            "Existing Snowflake data will not be modified."
        )

    required_columns = list(
        dict.fromkeys(cfg["key_columns"] + [cfg["value_column"]])
    )

    missing_columns = [col for col in required_columns if col not in data.columns]

    if missing_columns:
        raise ValueError(f"{dataset}: missing columns: {missing_columns}")

    data = data[required_columns].copy()

    data["timestamp"] = pd.to_datetime(data["timestamp"], utc=True, errors="raise")

    if data["timestamp"].isna().any():
        raise ValueError(f"{dataset}: missing timestamps.")

    # The CSV must contain the full Budapest calendar day and nothing else
    start, end = get_day_boundaries(date_str)

    if not ((data["timestamp"] >= start) & (data["timestamp"] < end)).all():
        raise ValueError(
            f"{dataset}: CSV contains timestamps outside "
            f"the requested Budapest day: {date_str}"
        )

    # Snowflake uses uppercase column names
    data.columns = [column.upper() for column in data.columns]

    return data, start, end


def replace_day(cursor, dataset, data, staging_table, start, end, database, schema):
    """Replace one local day in the target table with the staged rows.

    Must be called inside a transaction.
    """
    target_table = f"{database}.{schema}.{safe_identifier(dataset)}"
    column_list = ", ".join(safe_identifier(column) for column in data.columns)

    cursor.execute(
        f"DELETE FROM {target_table} "
        "WHERE TIMESTAMP >= TO_TIMESTAMP_TZ(%s) "
        "AND TIMESTAMP < TO_TIMESTAMP_TZ(%s)",
        (start.isoformat(), end.isoformat()),
    )
    deleted_rows = cursor.rowcount

    cursor.execute(
        f"INSERT INTO {target_table} ({column_list}) "
        f"SELECT {column_list} FROM {staging_table}"
    )
    inserted_rows = cursor.rowcount

    if inserted_rows != len(data):
        raise RuntimeError(
            f"{dataset}: expected {len(data)} inserted rows, "
            f"got {inserted_rows}."
        )

    print(f"{dataset}: deleted {deleted_rows} | inserted {inserted_rows}")


def load_datasets(conn, datasets, date_str):
    """Replace one Budapest day in several tables within ONE transaction.

    1. Read and check every CSV first, so a bad file changes nothing.
    2. Upload every dataset into its own temporary staging table.
    3. In a single transaction, delete the day from every target table and
       insert the staged rows. If anything fails, everything is rolled back,
       so the day is either replaced in all tables or not changed at all.
    """
    prepared = {
        dataset: prepare_dataset(dataset, date_str) for dataset in datasets
    }

    database = safe_identifier(os.getenv("SNOWFLAKE_DATABASE"))
    schema = safe_identifier(os.getenv("SNOWFLAKE_SCHEMA"))

    cursor = conn.cursor()
    staging_tables = {}
    transaction_started = False

    try:
        # Staging happens before the transaction: DDL inside a
        # transaction could end it early.
        for dataset, (data, _, _) in prepared.items():
            table = safe_identifier(dataset)
            staging_name = f"TMP_{table}_{uuid4().hex[:12].upper()}"
            staging_table = f"{database}.{schema}.{staging_name}"

            cursor.execute(
                f"CREATE TEMPORARY TABLE {staging_table} "
                f"LIKE {database}.{schema}.{table}"
            )
            staging_tables[dataset] = staging_table

            success, _, row_count, _ = write_pandas(
                conn,
                data,
                table_name=staging_name,
                database=database,
                schema=schema,
                use_logical_type=True,
            )

            if not success or row_count != len(data):
                raise RuntimeError(
                    f"{dataset}: staging upload failed. "
                    f"Expected {len(data)} rows, uploaded {row_count}."
                )

            print(f"{dataset}: {row_count} rows uploaded to staging.")

        cursor.execute("BEGIN TRANSACTION")
        transaction_started = True

        for dataset, (data, start, end) in prepared.items():
            replace_day(
                cursor, dataset, data, staging_tables[dataset],
                start, end, database, schema,
            )

        cursor.execute("COMMIT")
        transaction_started = False

        print(f"{date_str}: committed {len(prepared)} dataset(s) together.")

    except Exception:
        if transaction_started:
            try:
                cursor.execute("ROLLBACK")
                print(f"{date_str}: transaction rolled back.")
            except Exception as rollback_error:
                print(f"{date_str}: rollback failed: {rollback_error}")

        raise

    finally:
        # Cleanup happens outside the transaction
        for staging_table in staging_tables.values():
            try:
                cursor.execute(f"DROP TABLE IF EXISTS {staging_table}")
            except Exception as cleanup_error:
                print(f"{staging_table}: cleanup warning: {cleanup_error}")

        cursor.close()


def load_dataset(conn, dataset, date_str):
    """Replace one local day of a single dataset (used by the integration test)."""
    load_datasets(conn, [dataset], date_str)


def run_snowflake_load(date_str):
    """Load all configured datasets for one day, all or nothing."""
    conn = get_connection()

    try:
        load_datasets(conn, list(DATASETS), date_str)

    finally:
        conn.close()