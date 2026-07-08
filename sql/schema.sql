-- =========================================================
-- Back-Office WFM Analytics — Schema
-- Works on SQLite and PostgreSQL (minor type tweaks noted)
-- =========================================================

-- Dimension: processes / lines of business
CREATE TABLE IF NOT EXISTS processes (
    process_id          INTEGER PRIMARY KEY,
    process_name        TEXT NOT NULL,
    lob                  TEXT NOT NULL,
    sla_days             INTEGER NOT NULL,          -- turnaround-time target, in days
    productivity_standard REAL NOT NULL,             -- target items per hour
    complexity_tier      TEXT                        -- e.g. 'low', 'medium', 'high'
);

-- Dimension: agents
CREATE TABLE IF NOT EXISTS agents (
    agent_id            INTEGER PRIMARY KEY,
    agent_name          TEXT NOT NULL,
    primary_process_id  INTEGER NOT NULL REFERENCES processes(process_id),
    hire_date           DATE NOT NULL,
    shift_pattern       TEXT,                        -- e.g. 'Day', 'Night', 'Rotational'
    tenure_band         TEXT                         -- e.g. '0-6mo', '6-12mo', '1-2yr', '2yr+'
);

-- Bridge: which agents are cross-trained on which processes
CREATE TABLE IF NOT EXISTS agent_process_skills (
    agent_id    INTEGER NOT NULL REFERENCES agents(agent_id),
    process_id  INTEGER NOT NULL REFERENCES processes(process_id),
    PRIMARY KEY (agent_id, process_id)
);

-- Fact: individual work items processed (claims, invoices, tickets, etc.)
CREATE TABLE IF NOT EXISTS work_items (
    item_id         INTEGER PRIMARY KEY,
    process_id      INTEGER NOT NULL REFERENCES processes(process_id),
    received_date   DATE NOT NULL,
    due_date        DATE NOT NULL,
    completed_date  DATE,                            -- NULL = still open / in backlog
    agent_id        INTEGER REFERENCES agents(agent_id),
    priority        TEXT                              -- e.g. 'Standard', 'Urgent'
);

-- Fact: daily productivity logs per agent
CREATE TABLE IF NOT EXISTS productivity_logs (
    log_id          INTEGER PRIMARY KEY,
    agent_id        INTEGER NOT NULL REFERENCES agents(agent_id),
    process_id      INTEGER NOT NULL REFERENCES processes(process_id),
    log_date        DATE NOT NULL,
    items_processed INTEGER NOT NULL,
    hours_logged    REAL NOT NULL,
    idle_time       REAL DEFAULT 0,                  -- hours
    aux_time        REAL DEFAULT 0                   -- hours (breaks, training, meetings)
);

-- Fact: daily volume forecast vs actual, per process
CREATE TABLE IF NOT EXISTS volume_forecast_actuals (
    process_id          INTEGER NOT NULL REFERENCES processes(process_id),
    forecast_date       DATE NOT NULL,
    forecasted_volume   REAL,
    actual_volume       REAL,
    PRIMARY KEY (process_id, forecast_date)
);

-- Fact: attrition events (optional but nice for the exec dashboard)
CREATE TABLE IF NOT EXISTS attrition (
    agent_id   INTEGER NOT NULL REFERENCES agents(agent_id),
    exit_date  DATE NOT NULL,
    reason     TEXT
);

-- =========================================================
-- Helper indexes for common query patterns
-- =========================================================
CREATE INDEX IF NOT EXISTS idx_work_items_process_date ON work_items(process_id, received_date);
CREATE INDEX IF NOT EXISTS idx_prod_logs_agent_date ON productivity_logs(agent_id, log_date);
CREATE INDEX IF NOT EXISTS idx_volume_process_date ON volume_forecast_actuals(process_id, forecast_date);
