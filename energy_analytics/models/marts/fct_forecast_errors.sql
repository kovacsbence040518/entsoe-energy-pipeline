
{{ config(materialized='view') }}

SELECT
    actual.TIMESTAMP_UTC,
    actual.COUNTRY_CODE,
    actual.ACTUAL_LOAD_MW,
    forecast.FORECAST_LOAD_MW,

    forecast.FORECAST_LOAD_MW - actual.ACTUAL_LOAD_MW
        AS FORECAST_ERROR_MW,

    ABS(forecast.FORECAST_LOAD_MW - actual.ACTUAL_LOAD_MW)
        AS ABSOLUTE_ERROR_MW,

    ABS(forecast.FORECAST_LOAD_MW - actual.ACTUAL_LOAD_MW)
        / NULLIF(actual.ACTUAL_LOAD_MW, 0) * 100
        AS ABSOLUTE_PERCENTAGE_ERROR

FROM {{ ref('stg_load') }} AS actual

INNER JOIN {{ ref('stg_load_forecast') }} AS forecast
    ON actual.TIMESTAMP_UTC = forecast.TIMESTAMP_UTC
    AND actual.COUNTRY_CODE = forecast.COUNTRY_CODE
