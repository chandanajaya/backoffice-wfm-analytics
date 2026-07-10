# Back-Office WFM Capacity & Productivity Analytics

An end-to-end workforce management analytics pipeline for a multi-process
back-office / BPO operation — forecasting volume, calculating required
headcount, projecting backlog, and recommending cross-process staff
reallocation, with results surfaced in Power BI.

**Stack:** SQLite/SQL · Python (pandas, numpy) · Power BI

## The problem this solves

Back-office operations (claims processing, billing, onboarding, etc.) run on
a constant tension: **turnaround-time (TAT) compliance vs. staffing cost**.
Understaff a process and backlog piles up, breaching SLA. Overstaff it and
you're burning payroll on idle capacity. When an operation runs *multiple*
processes/LOBs with shared, cross-trained staff, the real skill is knowing
when to move people between queues before backlog becomes a problem — not
after.

This project simulates that exact situation across 3 processes and answers
it with data, end to end: SQL for the data model, Python for the forecasting
and staffing math, Power BI for the decision-maker view.

## What the analysis actually found

Running the full pipeline against 18 months of simulated data across three
processes (Claims Processing, Billing & Invoicing, Client Onboarding — the
latter with a deliberately growing volume trend and fixed headcount) turned
up a real, specific finding:

| Process | Understaffed days | Avg. capacity gap | Backlog: start → end |
|---|---|---|---|
| Claims Processing | 0% | +5.05 FTE | 4,860 → 0 |
| Billing & Invoicing | 0% | +5.51 FTE | 6,921 → 0 |
| **Client Onboarding** | **2%** | **+2.05 FTE** | **4,671 → 9.5 (climbing near the forecast horizon)** |

Two independently-built models — the FTE capacity calculation and the
day-by-day backlog simulation — agree on the same story: Onboarding's
volume grows over time while its headcount doesn't, so it's the one process
where backlog risk is real. The reallocation model then finds a fix: moving
a specific cross-trained agent from Billing to Onboarding on 9 identified
dates brings Onboarding's understaffed days from 2% down to 0%.

That's the kind of finding a WFM analyst would actually bring to a
capacity-planning meeting — not just a dashboard, but a recommendation.

## Architecture

```
Synthetic data generator (Python)
        │
        ▼
   SQLite database  ──►  KPI views (SQL: TAT, productivity, backlog aging, utilization)
        │
        ▼
Python modeling layer
  ├─ forecast_volume.py        (regression: trend + day-of-week + month-end seasonality)
  ├─ fte_capacity_model.py     (Required FTE = Volume / (Productivity × Hours × Utilization))
  ├─ backlog_simulation.py     (day-by-day queue projection)
  └─ reallocation_model.py     (rule-based cross-process staff reallocation)
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
│   ├── etl_pipeline.py              # shared data-access layer
│   ├── forecast_volume.py
│   ├── fte_capacity_model.py
│   ├── backlog_simulation.py
│   └── reallocation_model.py
├── powerbi/
│   └── wfm_dashboard.pbix
└── docs/
    └── project-plan.md              # phased build plan this project followed
```

## How to run it

```bash
pip install -r requirements.txt

cd data
python generate_synthetic_data.py      # builds ../backoffice_wfm.db

cd ../python
python etl_pipeline.py                 # sanity check: prints row counts
python forecast_volume.py              # volume forecast per process
python fte_capacity_model.py           # required vs available FTE per process/day
python backlog_simulation.py           # backlog projection per process/day
python reallocation_model.py           # cross-process reallocation recommendations
```

This generates ~18 months of data across 3 simulated processes, each with a
distinct volume pattern (steady, month-end spikes, growing trend), 16 agents
(~40% cross-trained across processes), and realistic SLA breaches — so the
resulting dashboards have something genuine to show, not just clean-looking
placeholder charts.

## Design decisions worth noting

- **No Prophet/statsmodels for forecasting.** Prophet in particular needs a
  C++ build toolchain that's a pain on Windows. A regression model
  (linear trend + day-of-week dummies + a month-end proximity term) hits
  3–5% MAPE on holdout data and is fully explainable coefficient by
  coefficient — a stronger interview answer than "I called `.fit()` on a
  black box."
- **Rule-based reallocation, not linear programming.** With only 3
  processes and 16 agents, a greedy day-by-day rule finds essentially the
  same answer an LP solver would, without the extra dependency. Noted in
  `reallocation_model.py` as a clear "if this scaled to dozens of
  processes, I'd switch to `pulp`/OR-Tools" extension point.
- **Agent headcount was deliberately calibrated**, not just randomly
  generated, so that capacity tension is real rather than either
  trivially oversupplied or undersuppplied. See the git history on
  `generate_synthetic_data.py` for how that number was derived from the
  underlying productivity-standard math.

## Glossary

- **TAT (turnaround time):** how long a work item takes from receipt to completion.
- **SLA:** the TAT target a process is measured against.
- **Backlog aging:** open items bucketed by how long they've been waiting.
- **Utilization:** productive hours vs. total hours logged.
- **Shrinkage:** the inverse — time lost to breaks, idle time, training, etc.
- **Productivity standard:** the benchmark items/hour a process expects.
- **FTE (full-time equivalent):** a staffing unit; `Required FTE = Forecasted Volume / (Productivity Standard × Available Hours × Utilization Rate)`.

## Roadmap

See [`docs/project-plan.md`](docs/project-plan.md) for the full phased build
plan. Current status: SQL + Python modeling layers complete; Power BI
dashboard in progress.

## License

MIT — see [LICENSE](LICENSE).
