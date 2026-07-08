-- =========================================================
-- KPI Views for Back-Office WFM Analytics
-- =========================================================

-- 1) TAT / SLA compliance % by process and month
CREATE VIEW IF NOT EXISTS v_tat_sla_compliance AS
SELECT
    p.process_id,
    p.process_name,
    strftime('%Y-%m', wi.completed_date) AS completion_month,
    COUNT(*) AS items_completed,
    SUM(CASE WHEN julianday(wi.completed_date) - julianday(wi.received_date) <= p.sla_days
             THEN 1 ELSE 0 END) AS items_within_sla,
    ROUND(100.0 * SUM(CASE WHEN julianday(wi.completed_date) - julianday(wi.received_date) <= p.sla_days
             THEN 1 ELSE 0 END) / COUNT(*), 2) AS sla_compliance_pct
FROM work_items wi
JOIN processes p ON p.process_id = wi.process_id
WHERE wi.completed_date IS NOT NULL
GROUP BY p.process_id, p.process_name, completion_month;

-- 2) Productivity per agent/process vs standard
CREATE VIEW IF NOT EXISTS v_productivity_scorecard AS
SELECT
    a.agent_id,
    a.agent_name,
    p.process_id,
    p.process_name,
    pl.log_date,
    pl.items_processed,
    pl.hours_logged,
    ROUND(pl.items_processed / NULLIF(pl.hours_logged, 0), 2) AS items_per_hour,
    p.productivity_standard,
    ROUND(100.0 * (pl.items_processed / NULLIF(pl.hours_logged, 0)) / p.productivity_standard, 1) AS pct_of_standard
FROM productivity_logs pl
JOIN agents a ON a.agent_id = pl.agent_id
JOIN processes p ON p.process_id = pl.process_id;

-- 3) Backlog aging buckets by process
-- Uses the max date present in the dataset as the "as of" reference date,
-- rather than the real current date — important since this is historical
-- synthetic data, not a live feed. Swap the subquery for CURRENT_DATE once
-- you're running this against a live/production database.
CREATE VIEW IF NOT EXISTS v_backlog_aging AS
WITH as_of AS (
    SELECT MAX(forecast_date) AS ref_date FROM volume_forecast_actuals
)
SELECT
    p.process_id,
    p.process_name,
    CASE
        WHEN julianday((SELECT ref_date FROM as_of)) - julianday(wi.received_date) <= 1 THEN '0-1 day'
        WHEN julianday((SELECT ref_date FROM as_of)) - julianday(wi.received_date) <= 3 THEN '1-3 days'
        ELSE '3+ days'
    END AS age_bucket,
    COUNT(*) AS open_items
FROM work_items wi
JOIN processes p ON p.process_id = wi.process_id
WHERE wi.completed_date IS NULL
GROUP BY p.process_id, p.process_name, age_bucket;

-- 4) Utilization / shrinkage per agent per day
CREATE VIEW IF NOT EXISTS v_utilization_shrinkage AS
SELECT
    a.agent_id,
    a.agent_name,
    pl.log_date,
    pl.hours_logged,
    pl.idle_time,
    pl.aux_time,
    ROUND(100.0 * (pl.idle_time + pl.aux_time) / NULLIF(pl.hours_logged, 0), 1) AS shrinkage_pct,
    ROUND(100.0 * (pl.hours_logged - pl.idle_time - pl.aux_time) / NULLIF(pl.hours_logged, 0), 1) AS utilization_pct
FROM productivity_logs pl
JOIN agents a ON a.agent_id = pl.agent_id;

-- 5) Rolling attrition rate (30-day) — SQLite window function
CREATE VIEW IF NOT EXISTS v_rolling_attrition AS
SELECT
    exit_date,
    COUNT(*) OVER (
        ORDER BY julianday(exit_date)
        RANGE BETWEEN 30 PRECEDING AND CURRENT ROW
    ) AS exits_last_30_days
FROM attrition;
