
from datetime import datetime, timedelta
import subprocess

from airflow.sdk import dag, task


@dag(
    dag_id="energy_pipeline",
    schedule="@daily",
    start_date=datetime(2026, 10, 1),
    catchup=False,
    tags=["energy", "entsoe"],
)
def energy_pipeline():

    @task(retries=3, retry_delay=timedelta(hours=2))
    def run_etl():
        target_date = (
            datetime.now() - timedelta(days=3)
        ).strftime("%Y-%m-%d")

        subprocess.run(
            [
                "python",
                "/opt/airflow/project/src/run_pipeline.py",
                "--date",
                target_date,
            ],
            cwd="/opt/airflow/project",
            check=True,
        )

    run_etl()


energy_pipeline()
