{{ config(materialized='view') }}

SELECT
    TIMESTAMP AS TIMESTAMP_UTC,
    COUNTRY_CODE,
    FORECAST_LOAD_MW
FROM {{ source('energy_raw', 'load_forecast') }}
WHERE
    TIMESTAMP IS NOT NULL
    AND COUNTRY_CODE IS NOT NULL
    AND FORECAST_LOAD_MW IS NOT NULL