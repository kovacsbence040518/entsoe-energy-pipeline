"""Quick check that the Snowflake credentials in .env work.

Run from the project root:  python scripts/check_snowflake_connection.py
"""

import os

import snowflake.connector
from dotenv import load_dotenv


def main():
    load_dotenv()

    conn = snowflake.connector.connect(
        account=os.getenv("SNOWFLAKE_ACCOUNT"),
        user=os.getenv("SNOWFLAKE_USER"),
        password=os.getenv("SNOWFLAKE_PASSWORD"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE"),
        database=os.getenv("SNOWFLAKE_DATABASE"),
        schema=os.getenv("SNOWFLAKE_SCHEMA"),
    )

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT CURRENT_USER(), CURRENT_ROLE(), CURRENT_WAREHOUSE()")
        print(cursor.fetchone())
        cursor.close()
    finally:
        conn.close()


if __name__ == "__main__":
    main()