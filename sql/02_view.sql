-- All daily aggregations use Europe/Budapest (HU, AT and SK share the same time zone, CET/CEST).

USE WAREHOUSE ENERGY_WH;
USE DATABASE ENERGY_DB;


-- ==========================================================
-- 1. LOAD FORECAST ANALYSIS
-- ==========================================================


--Calculate forecast errors for matching country and timestamp
CREATE OR REPLACE VIEW ANALYTICS.LOAD_FORECAST_ERROR AS
SELECT
    a.TIMESTAMP,
    a.COUNTRY_CODE,
    a.ACTUAL_LOAD_MW,
    f.FORECAST_LOAD_MW,
    a.ACTUAL_LOAD_MW - f.FORECAST_LOAD_MW      AS FORECAST_ERROR_MW,
    ABS(a.ACTUAL_LOAD_MW - f.FORECAST_LOAD_MW) AS ABSOLUTE_ERROR_MW
FROM RAW.LOAD a
JOIN RAW.LOAD_FORECAST f
  ON  a.TIMESTAMP    = f.TIMESTAMP
  AND a.COUNTRY_CODE = f.COUNTRY_CODE;

--Calculate daily forecast accuracy metrics (MAE, MEA % ,bias)
CREATE OR REPLACE VIEW ANALYTICS.FORECAST_ACCURACY_BY_COUNTRY AS
SELECT
    COUNTRY_CODE,
    DATE(CONVERT_TIMEZONE('Europe/Budapest', TIMESTAMP)) AS LOCAL_DATE,
    ROUND(AVG(ABSOLUTE_ERROR_MW), 2) AS MAE_MW,
    ROUND(
        AVG(ABSOLUTE_ERROR_MW) /
        NULLIF(AVG(ACTUAL_LOAD_MW), 0) * 100,
        2
    ) AS MAE_PERCENT,
    ROUND(AVG(FORECAST_ERROR_MW), 2) AS BIAS_MW
FROM ANALYTICS.LOAD_FORECAST_ERROR
GROUP BY COUNTRY_CODE, LOCAL_DATE;


-- ==========================================================
-- 2. ELECTRICITY PRICE ANALYSIS
-- ==========================================================


-- Calculate daily electricity price statistics
-- Negative electricity prices are valid market observations
CREATE OR REPLACE VIEW ANALYTICS.DAILY_PRICE_STATS AS
SELECT
    COUNTRY_CODE,
    DATE(CONVERT_TIMEZONE('Europe/Budapest', TIMESTAMP)) AS LOCAL_DATE,
    ROUND(AVG(PRICE_EUR_MWH), 2)  AS AVG_PRICE,
    MIN(PRICE_EUR_MWH)            AS MIN_PRICE,
    MAX(PRICE_EUR_MWH)            AS MAX_PRICE,
    COUNT_IF(PRICE_EUR_MWH < 0)   AS NEGATIVE_PRICE_INTERVALS
FROM RAW.DAY_AHEAD_PRICES
GROUP BY COUNTRY_CODE, LOCAL_DATE;


-- ==========================================================
-- 3. RENEWABLE ENERGY ANALYSIS
-- ==========================================================

-- Every generation row with its category (new, unknown sources show up as UNMAPPED)
CREATE OR REPLACE VIEW ANALYTICS.GENERATION_MIX AS
SELECT
    g.TIMESTAMP,
    g.COUNTRY_CODE,
    g.ENERGY_SOURCE,
    g.GENERATION_MW,
    COALESCE(c.ENERGY_CATEGORY, 'UNMAPPED') AS ENERGY_CATEGORY
FROM RAW.GENERATION g
LEFT JOIN ANALYTICS.ENERGY_SOURCE_CATEGORY c
  ON g.ENERGY_SOURCE = c.ENERGY_SOURCE;

-- Renewable share of reported generation per country and local day
CREATE OR REPLACE VIEW ANALYTICS.RENEWABLE_SHARE_DAILY AS
SELECT
    COUNTRY_CODE,
    DATE(CONVERT_TIMEZONE('Europe/Budapest', TIMESTAMP)) AS LOCAL_DATE,
    ROUND(
        SUM(IFF(ENERGY_CATEGORY = 'Renewable', GENERATION_MW, 0))
        / NULLIF(SUM(GENERATION_MW), 0) * 100, 2
    ) AS RENEWABLE_SHARE_PERCENT
FROM ANALYTICS.GENERATION_MIX
GROUP BY COUNTRY_CODE, LOCAL_DATE;


-- ==========================================================
-- 4. DAILY MARKET SUMMARY
-- ==========================================================


-- Combine daily electricity prices, consumption and renewable share
-- Join datasets using country code and local date
CREATE OR REPLACE VIEW ANALYTICS.DAILY_MARKET_SUMMARY AS
WITH daily_load AS (
    SELECT
        COUNTRY_CODE,
        DATE(CONVERT_TIMEZONE('Europe/Budapest', TIMESTAMP)) AS LOCAL_DATE,
        ROUND(AVG(ACTUAL_LOAD_MW), 2) AS AVG_LOAD_MW
    FROM RAW.LOAD
    GROUP BY COUNTRY_CODE, LOCAL_DATE
)
SELECT
    p.COUNTRY_CODE,
    p.LOCAL_DATE,
    p.AVG_PRICE,
    p.NEGATIVE_PRICE_INTERVALS,
    l.AVG_LOAD_MW,
    r.RENEWABLE_SHARE_PERCENT
FROM ANALYTICS.DAILY_PRICE_STATS p
JOIN daily_load l
  ON p.COUNTRY_CODE = l.COUNTRY_CODE AND p.LOCAL_DATE = l.LOCAL_DATE
JOIN ANALYTICS.RENEWABLE_SHARE_DAILY r
  ON p.COUNTRY_CODE = r.COUNTRY_CODE AND p.LOCAL_DATE = r.LOCAL_DATE;


-- ==========================================================
-- 5. HOURLY ELECTRICITY MARKET PROFILE
-- ==========================================================


--Calculate average electricity consumption and prices by local hour
-- Join load and price data using country and timestamp
CREATE OR REPLACE VIEW ANALYTICS.HOURLY_PROFILE AS
SELECT
    l.COUNTRY_CODE,
    HOUR(CONVERT_TIMEZONE('Europe/Budapest', l.TIMESTAMP)) AS LOCAL_HOUR,
    ROUND(AVG(l.ACTUAL_LOAD_MW), 2)    AS AVG_LOAD_MW,
    ROUND(AVG(p.PRICE_EUR_MWH), 2)     AS AVG_PRICE_EUR_MWH
FROM RAW.LOAD l
JOIN RAW.DAY_AHEAD_PRICES p
  ON l.TIMESTAMP = p.TIMESTAMP AND l.COUNTRY_CODE = p.COUNTRY_CODE
GROUP BY l.COUNTRY_CODE, LOCAL_HOUR;