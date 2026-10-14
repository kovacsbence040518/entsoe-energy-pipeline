
-- ==========================================================
-- SNOWFLAKE RESOURCE MANAGEMENT
-- Run commands individually, only when needed.
-- ==========================================================

-- Check resource status
SHOW WAREHOUSES LIKE 'ENERGY_WH';
SHOW COMPUTE POOLS LIKE 'SYSTEM_COMPUTE_POOL_CPU';

-- Stop the warehouse
ALTER WAREHOUSE ENERGY_WH SUSPEND;

-- Stop the Streamlit compute pool
ALTER COMPUTE POOL SYSTEM_COMPUTE_POOL_CPU SUSPEND;

-- Disable automatic compute pool resume
ALTER COMPUTE POOL SYSTEM_COMPUTE_POOL_CPU
SET AUTO_RESUME = FALSE;

-- Manually resume the compute pool
 ALTER COMPUTE POOL SYSTEM_COMPUTE_POOL_CPU RESUME;

SHOW STREAMLITS IN ACCOUNT;

DESCRIBE COMPUTE POOL SYSTEM_COMPUTE_POOL_CPU;

SHOW WAREHOUSES LIKE 'ENERGY_WH';

SHOW COMPUTE POOLS LIKE 'SYSTEM_COMPUTE_POOL_CPU';