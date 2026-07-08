# Back-Office WFM Capacity & Productivity Analytics

An end-to-end workforce management analytics pipeline for a multi-process
back-office / BPO operation — simulating volume forecasting, FTE capacity
planning, backlog projection, and cross-process staff reallocation, with
results surfaced in Power BI.

**Status:** 🚧 In progress — built as a portfolio project.

## The problem this solves

Back-office operations (claims processing, billing, onboarding, etc.) run on
a constant tension: **turnaround-time (TAT) compliance vs staffing cost**.
Understaff a process and backlog piles up, breaching SLA. Overstaff it and
you're burning payroll on idle capacity. When an operation runs *multiple*
processes/LOBs with shared, cross-trained staff, the real skill is knowing
when to move people between queues before backlog becomes a problem — not
after.

This project builds that analysis end-to-end:

- **SQL** — a relational schema modeling agents, processes, work items, and
  productivity logs, with KPI views for TAT compliance, backlog aging, and
  utilization.
- **Python** — volume forecasting, an FTE capacity model, a backlog
  simulation, and a cross-process reallocation model.
- **Power BI** — dashboards for execs, capacity planners, and team leads.

## Architecture

```
Synthetic data generator (Python)
        │
        ▼
   SQLite database  ──►  KPI views (SQL)
        │
        ▼
Python modeling layer (forecast → FTE capacity → backlog sim → reallocation)
        │
        ▼
   Power BI dashboard
```

## Repo structure

```
backoffice-wfm-analytics/
├── data/
│   └── generate_synthetic_data.py   # builds the SQLite database
├── sql/
│   ├── schema.sql                   # table definitions
│   └── views_kpis.sql               # TAT, productivity, backlog, utilization views
├── python/
│   ├── etl_pipeline.py
│   ├── forecast_volume.py
│   ├── fte_capacity_model.py
│   ├── backlog_simulation.py
│   └── reallocation_model.py
├── powerbi/
│   └── wfm_dashboard.pbix
└── docs/
    └── architecture_diagram.png
```

## How to run it

```bash
pip install -r requirements.txt

cd data
python generate_synthetic_data.py   # creates ../backoffice_wfm.db
```

This generates ~18 months of data across 3 simulated processes (Claims
Processing, Billing & Invoicing, Client Onboarding), each with a distinct
volume pattern (steady, month-end spikes, growing trend), ~90 agents with
~18% cross-trained across processes, and realistic SLA breaches so the
dashboards have something real to show.

## Glossary

- **TAT (turnaround time):** how long a work item takes from receipt to completion.
- **SLA:** the TAT target a process is measured against.
- **Backlog aging:** open items bucketed by how long they've been waiting.
- **Utilization:** productive hours vs total hours logged.
- **Shrinkage:** the inverse — time lost to breaks, idle time, training, etc.
- **Productivity standard:** the benchmark items/hour a process expects.
- **FTE (full-time equivalent):** a staffing unit; `Required FTE = Forecasted Volume / (Productivity Standard × Available Hours × Utilization Rate)`.

## Next steps / roadmap

See [`docs/project-plan.md`](docs/project-plan.md) for the full phased build
plan this project follows.
