CREATE WAREHOUSE IF NOT EXISTS ENERGY_WH
    WAREHOUSE_SIZE = 'XSMALL'
    AUTO_SUSPEND = 60
    AUTO_RESUME = TRUE;

CREATE DATABASE IF NOT EXISTS ENERGY_DB;

-- Select the Snowflake warehouse and database
USE WAREHOUSE ENERGY_WH;
USE DATABASE ENERGY_DB;

-- Create schemas for raw data and analytical views
CREATE SCHEMA IF NOT EXISTS RAW;
CREATE SCHEMA IF NOT EXISTS ANALYTICS;

-- Note: LOADED_AT uses CURRENT_TIMESTAMP(), i.e. the account's session time zone (not UTC).
-- Actual electricity consumption
CREATE TABLE IF NOT EXISTS RAW.LOAD (
    TIMESTAMP      TIMESTAMP_TZ,
    ACTUAL_LOAD_MW FLOAT,
    COUNTRY_CODE   VARCHAR(2),
    LOADED_AT      TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- Day-ahead electricity load forecast
CREATE TABLE IF NOT EXISTS RAW.LOAD_FORECAST (
    TIMESTAMP        TIMESTAMP_TZ,
    FORECAST_LOAD_MW FLOAT,
    COUNTRY_CODE     VARCHAR(2),
    LOADED_AT        TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- Electricity generation by energy source
CREATE TABLE IF NOT EXISTS RAW.GENERATION (
    TIMESTAMP     TIMESTAMP_TZ,
    ENERGY_SOURCE VARCHAR(100),
    GENERATION_MW FLOAT,
    COUNTRY_CODE  VARCHAR(2),
    LOADED_AT     TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

--Day-ahead electricity prices
CREATE TABLE IF NOT EXISTS RAW.DAY_AHEAD_PRICES (
    TIMESTAMP     TIMESTAMP_TZ,
    PRICE_EUR_MWH FLOAT,
    COUNTRY_CODE  VARCHAR(2),
    LOADED_AT     TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);


-- Energy source -> category mapping (single source of truth for all views)
CREATE OR REPLACE TABLE ANALYTICS.ENERGY_SOURCE_CATEGORY AS
SELECT column1 AS ENERGY_SOURCE, column2 AS ENERGY_CATEGORY
FROM VALUES
    ('Biomass',                        'Renewable'),
    ('Geothermal',                     'Renewable'),
    ('Hydro Run-of-river and pondage', 'Renewable'),
    ('Hydro Water Reservoir',          'Renewable'),
    ('Other renewable',                'Renewable'),
    ('Solar',                          'Renewable'),
    ('Wind Onshore',                   'Renewable'),
    ('Fossil Brown coal/Lignite',      'Fossil'),
    ('Fossil Gas',                     'Fossil'),
    ('Fossil Hard coal',               'Fossil'),
    ('Fossil Oil',                     'Fossil'),
    ('Nuclear',                        'Nuclear'),
    ('Hydro Pumped Storage',           'Energy Storage'),
    ('Waste',                          'Other / Mixed'),
    ('Other',                          'Other / Mixed');