# Back-Office WFM Capacity & Productivity Analytics — Project Plan

**Goal:** Build a portfolio-ready, end-to-end project (SQL → Python → Power BI) simulating multi-process/LOB back-office WFM capacity planning, hosted on GitHub.

**Suggested timeline:** ~10–12 working days at 6–7 hrs/day (roughly 2 weeks). Each phase has a clear "done" state so you always know what's next.

---

## Phase 0 — Setup (Day 1, ~2–3 hrs)
- [ ] Create GitHub repo: `backoffice-wfm-analytics`
- [ ] Set up local folder structure:
  ```
  backoffice-wfm-analytics/
  ├── README.md
  ├── data/
  ├── sql/
  ├── python/
  ├── powerbi/
  └── docs/
  ```
- [ ] Install tools: PostgreSQL or SQLite, Python 3.x, Power BI Desktop
- [ ] Set up a virtual environment; create `requirements.txt` (pandas, numpy, sqlalchemy, prophet or statsmodels, pulp, faker)
- [ ] Write a placeholder README with the project pitch (one paragraph — you'll expand it later)

**Done when:** repo exists, environment runs, empty folders committed.

---

## Phase 1 — Data Model (Day 1 afternoon – Day 2)
- [ ] Design and write `sql/schema.sql`:
  - `processes` (process_id, process_name, LOB, sla_days, productivity_standard, complexity_tier)
  - `agents` (agent_id, name, primary_process_id, hire_date, shift_pattern, tenure_band)
  - `agent_process_skills` (agent_id, process_id) — bridge table for cross-training
  - `work_items` (item_id, process_id, received_date, due_date, completed_date, agent_id, priority)
  - `productivity_logs` (agent_id, date, process_id, items_processed, hours_logged, idle_time, aux_time)
  - `volume_forecast_actuals` (process_id, date, forecasted_volume, actual_volume)
  - `attrition` (agent_id, exit_date, reason) — optional
- [ ] Decide 3 processes/LOBs and their personalities (e.g., steady, month-end-spiky, growing-trend)
- [ ] Draw a simple ER diagram (draw.io or dbdiagram.io) → save to `docs/`

**Done when:** schema.sql runs cleanly and creates all tables with correct foreign keys.

---

## Phase 2 — Synthetic Data Generator (Days 3–4)
- [ ] Write `data/generate_synthetic_data.py` using `faker` + `numpy`/`pandas`
- [ ] Generate ~50–150 agents across 3 processes, ~10–20% cross-trained
- [ ] Generate 12–18 months of daily volume per process, each with its own pattern:
  - Process A: steady + mild weekly seasonality
  - Process B: month-end spikes
  - Process C: upward trend over time
- [ ] Generate work items with realistic received/completed dates (some breaching SLA on purpose — you need visible problems for the dashboard to be interesting)
- [ ] Generate productivity logs and occasional attrition events
- [ ] Load all generated data into your SQL database
- [ ] Sanity-check row counts and spot-check a few records manually

**Done when:** database is populated and querying `SELECT COUNT(*)` on each table gives sensible numbers.

---

## Phase 3 — SQL Analytics Layer (Day 5)
- [ ] Write `sql/views_kpis.sql` with views for:
  - TAT/SLA compliance % by process/month
  - Productivity per agent/process (items per hour vs standard)
  - Backlog aging buckets (0–1 day, 1–3 days, 3+ days) by process
  - Utilization/shrinkage (logged hours vs available hours)
  - Rolling attrition rate (window function)
- [ ] Test each view independently with a few manual queries
- [ ] Document each view's purpose in a short comment block at the top of the SQL file

**Done when:** all views return correct, sensible numbers you could explain to a non-technical person.

---

## Phase 4 — Python Modeling Layer (Days 6–8)
Build in this order — each script depends conceptually on the previous. At 6–7 hrs/day you can realistically do ~1.5 scripts per day:

1. [ ] `python/etl_pipeline.py` — pulls raw data from SQL into pandas DataFrames (build this first so the rest can reuse it)
2. [ ] `python/forecast_volume.py` — time series forecast per process (Prophet or statsmodels), validate against held-out actuals
3. [ ] `python/fte_capacity_model.py` — implements:
   `Required FTE = Forecasted Volume / (Productivity Standard × Available Hours × Utilization Rate)`
   per process/date
4. [ ] `python/backlog_simulation.py` — projects backlog forward per process given forecasted inflow + current capacity
5. [ ] `python/reallocation_model.py` — decide rule-based vs optimization (see note below), then implement:
   - Identify surplus/deficit processes per day
   - Reassign cross-trained agents accordingly
   - Recompute capacity gap after reallocation
- [ ] Have each script write its output back to SQL (new tables, e.g., `fte_requirements`, `backlog_projection`, `reallocation_recommendations`) so Power BI has one place to read from

**Decision point (make before step 5):** rule-based reallocation (simpler, faster) vs linear-programming optimization with `pulp` (more impressive, more build time). Pick based on how much time you have left in your timeline.

**Done when:** running the full pipeline end-to-end (`etl → forecast → capacity → backlog → reallocation`) produces new tables in SQL with no errors.

---

## Phase 5 — Power BI Dashboard (Days 9–11)
- [ ] Connect Power BI to your SQL database
- [ ] Build data model / relationships (should mirror your SQL schema)
- [ ] Page 1 — Executive Summary: TAT/SLA compliance, backlog trend, utilization, attrition (all-process aggregate)
- [ ] Page 2 — Capacity Plan: forecasted volume vs required FTE vs actual staffing, by process/month
- [ ] Page 3 — Productivity Scorecard: items/hour by agent/team vs standard
- [ ] Page 4 — Backlog Aging & Risk: aging buckets + projected backlog trend
- [ ] Page 5 — Cross-Process Capacity & Reallocation: required vs available FTE by process, reallocation recommendation table
- [ ] Add a process/LOB slicer that filters across all pages
- [ ] Polish: consistent color theme, clear titles, tooltips explaining each KPI

**Done when:** you can click through all 5 pages and tell a coherent story without needing to explain anything verbally.

---

## Phase 6 — Documentation & GitHub Polish (Day 12)
- [ ] Write the full README:
  - Business problem framing (TAT/SLA vs cost tradeoff across LOBs)
  - Architecture diagram (data flow: SQL → Python → Power BI)
  - Screenshots of each dashboard page
  - How to run it locally (setup steps)
  - Key terminology glossary (TAT, shrinkage, utilization, productivity standard) — signals domain fluency
- [ ] Record a 3–5 min walkthrough video (Loom/YouTube unlisted) and link it in the README
- [ ] Clean up code: comments, consistent naming, remove dead code
- [ ] Add a LICENSE file
- [ ] Final commit + tag a `v1.0` release

**Done when:** a stranger could land on your repo, read the README top to bottom, and understand exactly what you built and why it matters — without opening a single code file.

---

## Stretch goals (optional, if you have extra time)
- [ ] Add a simple Streamlit app as an alternative front-end to Power BI (shows versatility)
- [ ] Add unit tests for the FTE and backlog models
- [ ] Add a GitHub Actions workflow that regenerates synthetic data and refreshes SQL on a schedule
- [ ] Write a short Medium/LinkedIn post summarizing the project and link it from the README
