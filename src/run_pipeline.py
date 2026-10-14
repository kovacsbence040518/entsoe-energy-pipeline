import os
import argparse
import pandas as pd
from snowflake_load import run_snowflake_load
from dotenv import load_dotenv
from entsoe import EntsoePandasClient

from config import DATASETS, TIMEZONE
from extract import extract_dataset
from transform import run_transform
from validate import run_validation



def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="Date in YYYY-MM-DD format")
    args = parser.parse_args()

    print(f"Running pipeline for: {args.date}")

    load_dotenv()
    client = EntsoePandasClient(api_key=os.getenv("ENTSOE_API_KEY"))

    start = pd.Timestamp(args.date, tz=TIMEZONE)
    end = start + pd.DateOffset(days=1)  # DST-safe

    for dataset in DATASETS:
        print(f"\n=== {dataset.upper()} ===")
        extract_dataset(client, dataset, start, end, args.date)
        run_transform(dataset, args.date)
        run_validation(dataset, args.date)

    print("\n=== SNOWFLAKE LOAD ===")
    run_snowflake_load(args.date)


if __name__ == "__main__":
    main()