"""
Generate synthetic multi-process back-office WFM data and load it into a
SQLite database (backoffice_wfm.db) for the rest of the pipeline to use.

Run:
    pip install pandas numpy
    python generate_synthetic_data.py
"""

import sqlite3
import random
from datetime import date, timedelta

import numpy as np
import pandas as pd

random.seed(42)
np.random.seed(42)

FIRST_NAMES = ["Aisha", "Ben", "Carlos", "Diya", "Ethan", "Fatima", "Grace", "Hiro",
               "Ines", "Jack", "Kavya", "Liam", "Maya", "Noah", "Olivia", "Priya",
               "Quinn", "Rohan", "Sofia", "Tariq", "Uma", "Victor", "Wei", "Ximena",
               "Yusuf", "Zoe", "Amara", "Ben", "Chidi", "Dev"]
LAST_NAMES = ["Patel", "Garcia", "Kim", "Nguyen", "Smith", "Khan", "Silva", "Muller",
              "Okafor", "Rossi", "Tanaka", "Ivanov", "Costa", "Haddad", "Lindberg",
              "Osei", "Fischer", "Alvarez", "Chowdhury", "Novak"]


def fake_name():
    return f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"


def fake_date_between(start_date, end_date):
    delta = (end_date - start_date).days
    return start_date + timedelta(days=random.randint(0, max(delta, 0)))

DB_PATH = "../backoffice_wfm.db"
SCHEMA_PATH = "../sql/schema.sql"

START_DATE = date(2024, 1, 1)
END_DATE = date(2025, 6, 30)
N_DAYS = (END_DATE - START_DATE).days + 1
N_AGENTS = 90

# ---------------------------------------------------------
# 1) Processes — each with a distinct volume "personality"
# ---------------------------------------------------------
PROCESSES = [
    {"process_id": 1, "process_name": "Claims Processing", "lob": "Insurance Ops",
     "sla_days": 3, "productivity_standard": 6.0, "complexity_tier": "medium",
     "pattern": "steady"},
    {"process_id": 2, "process_name": "Billing & Invoicing", "lob": "Finance Ops",
     "sla_days": 2, "productivity_standard": 10.0, "complexity_tier": "low",
     "pattern": "month_end_spike"},
    {"process_id": 3, "process_name": "Client Onboarding", "lob": "Growth Ops",
     "sla_days": 5, "productivity_standard": 4.0, "complexity_tier": "high",
     "pattern": "growing_trend"},
]


def daily_volume(process, day_index, the_date):
    base = {"steady": 120, "month_end_spike": 150, "growing_trend": 60}[process["pattern"]]

    if process["pattern"] == "steady":
        weekly = 1 + 0.1 * np.sin(2 * np.pi * day_index / 7)
        noise = np.random.normal(0, 8)
        return max(0, base * weekly + noise)

    if process["pattern"] == "month_end_spike":
        days_in_month = 30
        day_of_month = the_date.day
        spike = 1 + 1.2 * np.exp(-((days_in_month - day_of_month) ** 2) / 8) if day_of_month >= 24 else 1.0
        noise = np.random.normal(0, 10)
        return max(0, base * spike + noise)

    if process["pattern"] == "growing_trend":
        trend = 1 + (day_index / N_DAYS) * 1.5  # up to +150% by end of period
        weekly = 1 + 0.15 * np.sin(2 * np.pi * day_index / 7)
        noise = np.random.normal(0, 6)
        return max(0, base * trend * weekly + noise)


# ---------------------------------------------------------
# 2) Agents + cross-training
# ---------------------------------------------------------
def generate_agents():
    agents = []
    shift_patterns = ["Day", "Night", "Rotational"]
    tenure_bands = ["0-6mo", "6-12mo", "1-2yr", "2yr+"]

    for i in range(1, N_AGENTS + 1):
        primary = random.choice(PROCESSES)["process_id"]
        hire_date = fake_date_between(date(2021, 7, 1), date(2025, 6, 1))
        agents.append({
            "agent_id": i,
            "agent_name": fake_name(),
            "primary_process_id": primary,
            "hire_date": hire_date,
            "shift_pattern": random.choice(shift_patterns),
            "tenure_band": random.choice(tenure_bands),
        })
    return pd.DataFrame(agents)


def generate_agent_skills(agents_df, cross_train_pct=0.18):
    rows = []
    # every agent knows their primary process
    for _, row in agents_df.iterrows():
        rows.append({"agent_id": row["agent_id"], "process_id": row["primary_process_id"]})

    # ~18% of agents are cross-trained on one additional process
    n_cross = int(len(agents_df) * cross_train_pct)
    cross_agents = agents_df.sample(n=n_cross, random_state=42)
    for _, row in cross_agents.iterrows():
        other_processes = [p["process_id"] for p in PROCESSES if p["process_id"] != row["primary_process_id"]]
        secondary = random.choice(other_processes)
        rows.append({"agent_id": row["agent_id"], "process_id": secondary})

    return pd.DataFrame(rows).drop_duplicates()


# ---------------------------------------------------------
# 3) Volume forecast/actuals
# ---------------------------------------------------------
def generate_volume_data():
    rows = []
    for process in PROCESSES:
        for day_index in range(N_DAYS):
            the_date = START_DATE + timedelta(days=day_index)
            actual = daily_volume(process, day_index, the_date)
            # forecast = actual with some forecasting error baked in
            forecast_error = np.random.normal(0, 0.08) * actual
            forecast = max(0, actual - forecast_error)
            rows.append({
                "process_id": process["process_id"],
                "forecast_date": the_date.isoformat(),
                "forecasted_volume": round(forecast, 1),
                "actual_volume": round(actual, 1),
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------
# 4) Work items (drives backlog + TAT/SLA)
# ---------------------------------------------------------
def generate_work_items(volume_df, agents_df, skills_df):
    rows = []
    item_id = 1
    process_lookup = {p["process_id"]: p for p in PROCESSES}

    for _, vrow in volume_df.iterrows():
        process_id = vrow["process_id"]
        received_date = date.fromisoformat(vrow["forecast_date"])
        n_items = int(round(vrow["actual_volume"]))
        process = process_lookup[process_id]

        eligible_agents = skills_df[skills_df["process_id"] == process_id]["agent_id"].tolist()
        if not eligible_agents:
            continue

        for _ in range(n_items):
            due_date = received_date + timedelta(days=process["sla_days"])
            # 85% completed within a realistic window, 15% breach SLA or stay open
            agent_id = random.choice(eligible_agents)
            completion_offset = np.random.choice(
                [process["sla_days"] - 1, process["sla_days"], process["sla_days"] + 2, None],
                p=[0.45, 0.35, 0.13, 0.07]
            )
            completed_date = None if completion_offset is None else (received_date + timedelta(days=int(completion_offset)))
            # don't let items "complete" in the future relative to END_DATE
            if completed_date and completed_date > END_DATE:
                completed_date = None

            rows.append({
                "item_id": item_id,
                "process_id": process_id,
                "received_date": received_date.isoformat(),
                "due_date": due_date.isoformat(),
                "completed_date": completed_date.isoformat() if completed_date else None,
                "agent_id": agent_id,
                "priority": random.choices(["Standard", "Urgent"], weights=[0.85, 0.15])[0],
            })
            item_id += 1

    return pd.DataFrame(rows)


# ---------------------------------------------------------
# 5) Productivity logs
# ---------------------------------------------------------
def generate_productivity_logs(agents_df, skills_df):
    rows = []
    log_id = 1
    process_lookup = {p["process_id"]: p for p in PROCESSES}

    for _, agent in agents_df.iterrows():
        agent_processes = skills_df[skills_df["agent_id"] == agent["agent_id"]]["process_id"].tolist()
        for day_index in range(0, N_DAYS, 1):
            the_date = START_DATE + timedelta(days=day_index)
            if the_date.weekday() >= 5:  # skip weekends
                continue
            if random.random() < 0.04:  # ~4% absenteeism
                continue

            process_id = random.choice(agent_processes)
            standard = process_lookup[process_id]["productivity_standard"]
            hours_logged = round(np.random.normal(8, 0.3), 2)
            idle_time = round(max(0, np.random.normal(0.4, 0.2)), 2)
            aux_time = round(max(0, np.random.normal(0.8, 0.3)), 2)
            productive_hours = max(0.5, hours_logged - idle_time - aux_time)
            items_processed = int(max(0, np.random.normal(standard, standard * 0.15) * productive_hours))

            rows.append({
                "log_id": log_id,
                "agent_id": agent["agent_id"],
                "process_id": process_id,
                "log_date": the_date.isoformat(),
                "items_processed": items_processed,
                "hours_logged": hours_logged,
                "idle_time": idle_time,
                "aux_time": aux_time,
            })
            log_id += 1

    return pd.DataFrame(rows)


# ---------------------------------------------------------
# 6) Attrition
# ---------------------------------------------------------
def generate_attrition(agents_df, attrition_rate=0.15):
    n_exits = int(len(agents_df) * attrition_rate)
    exiting_agents = agents_df.sample(n=n_exits, random_state=7)
    reasons = ["Better opportunity", "Relocation", "Performance", "Personal reasons", "Career break"]

    rows = []
    for _, agent in exiting_agents.iterrows():
        exit_date = fake_date_between(START_DATE, END_DATE)
        rows.append({"agent_id": agent["agent_id"], "exit_date": exit_date.isoformat(),
                      "reason": random.choice(reasons)})
    return pd.DataFrame(rows)


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------
def main():
    print("Generating processes...")
    processes_df = pd.DataFrame([{k: v for k, v in p.items() if k != "pattern"} for p in PROCESSES])

    print("Generating agents...")
    agents_df = generate_agents()

    print("Generating agent-process skills (cross-training)...")
    skills_df = generate_agent_skills(agents_df)

    print("Generating volume forecast/actuals...")
    volume_df = generate_volume_data()

    print("Generating work items (this can take a bit)...")
    work_items_df = generate_work_items(volume_df, agents_df, skills_df)

    print("Generating productivity logs...")
    productivity_df = generate_productivity_logs(agents_df, skills_df)

    print("Generating attrition events...")
    attrition_df = generate_attrition(agents_df)

    print("Writing to SQLite database...")
    conn = sqlite3.connect(DB_PATH)
    with open(SCHEMA_PATH, "r") as f:
        conn.executescript(f.read())

    processes_df.to_sql("processes", conn, if_exists="append", index=False)
    agents_df.to_sql("agents", conn, if_exists="append", index=False)
    skills_df.to_sql("agent_process_skills", conn, if_exists="append", index=False)
    volume_df.to_sql("volume_forecast_actuals", conn, if_exists="append", index=False)
    work_items_df.to_sql("work_items", conn, if_exists="append", index=False)
    productivity_df.to_sql("productivity_logs", conn, if_exists="append", index=False)
    attrition_df.to_sql("attrition", conn, if_exists="append", index=False)

    conn.commit()
    conn.close()

    print("Done.")
    print(f"  processes:            {len(processes_df)}")
    print(f"  agents:                {len(agents_df)}")
    print(f"  agent_process_skills:  {len(skills_df)}")
    print(f"  volume rows:           {len(volume_df)}")
    print(f"  work_items:            {len(work_items_df)}")
    print(f"  productivity_logs:     {len(productivity_df)}")
    print(f"  attrition:             {len(attrition_df)}")
    print(f"\nDatabase written to: {DB_PATH}")


if __name__ == "__main__":
    main()
