USE WAREHOUSE ENERGY_WH;
USE DATABASE ENERGY_DB;
USE SCHEMA ETL_TEST;

-- Create a separate schema for integration testing
CREATE SCHEMA IF NOT EXISTS ENERGY_DB.ETL_TEST;

-- Create an empty test table with the same structure as RAW.LOAD
CREATE TABLE IF NOT EXISTS ENERGY_DB.ETL_TEST.LOAD
LIKE ENERGY_DB.RAW.LOAD;

-- Verify that the test table is empty
SELECT COUNT(*)
FROM ENERGY_DB.ETL_TEST.LOAD;


-- ==========================================
-- TEST: TRANSACTION ROLLBACK
-- Only affects ENERGY_DB.ETL_TEST.LOAD
-- ==========================================

-- 1. Check original data
SELECT
    COUNT(*) AS ROW_COUNT,
    HASH_AGG(*) AS DATA_HASH
FROM ENERGY_DB.ETL_TEST.LOAD;

-- 2. Start transaction
BEGIN TRANSACTION;

-- 3. Simulate deletion during data replacement
DELETE FROM ENERGY_DB.ETL_TEST.LOAD;

-- 4. Check that rows are temporarily deleted
SELECT COUNT(*) AS ROWS_DURING_TRANSACTION
FROM ENERGY_DB.ETL_TEST.LOAD;

-- 5. Cancel the transaction
ROLLBACK;

-- 6. Verify that original data is restored
SELECT
    COUNT(*) AS ROW_COUNT,
    HASH_AGG(*) AS DATA_HASH
FROM ENERGY_DB.ETL_TEST.LOAD;
