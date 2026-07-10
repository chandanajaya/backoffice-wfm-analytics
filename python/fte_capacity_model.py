"""
fte_capacity_model.py
======================
Converts forecasted volume into required headcount (FTE) per process per day.

The core back-office WFM formula:

    Required FTE = Forecasted Volume / (Productivity Standard x Available Hours x Utilization Rate)

Where:
    - Forecasted Volume     : items expected that day (from volume_forecast_model)
    - Productivity Standard : target items/hour for that process (from processes table)
    - Available Hours       : standard shift length (assumed 8 hrs/day here)
    - Utilization Rate      : productive hours / hours logged, i.e. 1 - shrinkage
                              (derived from actual historical productivity_logs,
                              per process, so it reflects real observed shrinkage
                              rather than an assumed constant)

Also computes Available FTE (actual headcount scheduled/available per process
per day, from agent_process_skills) and the resulting capacity Gap:

    Gap = Available FTE - Required FTE
    (negative gap = understaffed, positive = overstaffed)

Writes results to a new `fte_requirements` table:
    process_id, date, forecasted_volume, required_fte, available_fte, capacity_gap

Usage:
    python fte_capacity_model.py
"""

import numpy as np
import pandas as pd

from etl_pipeline import (
    get_processes,
    get_agents,
    get_agent_process_skills,
    get_productivity_logs,
    extract_table,
    load_dataframe,
)

AVAILABLE_HOURS_PER_DAY = 8.0


def compute_utilization_by_process(productivity_logs: pd.DataFrame) -> pd.Series:
    """
    Observed utilization rate per process = productive hours / hours logged,
    averaged across all historical productivity logs for that process.
    """
    logs = productivity_logs.copy()
    logs["productive_hours"] = logs["hours_logged"] - logs["idle_time"] - logs["aux_time"]
    logs["productive_hours"] = logs["productive_hours"].clip(lower=0)

    grouped = logs.groupby("process_id").agg(
        total_productive=("productive_hours", "sum"),
        total_logged=("hours_logged", "sum"),
    )
    grouped["utilization_rate"] = grouped["total_productive"] / grouped["total_logged"]
    return grouped["utilization_rate"]


def compute_available_fte(agent_skills: pd.DataFrame) -> pd.Series:
    """
    Available FTE per process = count of agents skilled on that process.
    (A simplifying assumption for this project: every skilled agent is
    counted as 1.0 FTE available every day. A more advanced version could
    weight this by actual scheduled hours per day.)
    """
    return agent_skills.groupby("process_id")["agent_id"].nunique()


def main():
    processes = get_processes().set_index("process_id")
    agent_skills = get_agent_process_skills()
    productivity_logs = get_productivity_logs()
    forecast = extract_table("volume_forecast_model")

    utilization_by_process = compute_utilization_by_process(productivity_logs)
    available_fte_by_process = compute_available_fte(agent_skills)

    print("Observed utilization rate by process:")
    for pid, rate in utilization_by_process.items():
        print(f"  Process {pid} ({processes.loc[pid, 'process_name']}): {rate:.1%}")

    print("\nAvailable FTE (cross-trained headcount) by process:")
    for pid, count in available_fte_by_process.items():
        print(f"  Process {pid} ({processes.loc[pid, 'process_name']}): {count}")

    results = []
    for pid, proc in processes.iterrows():
        proc_forecast = forecast[forecast["process_id"] == pid].copy()

        standard = proc["productivity_standard"]
        utilization = utilization_by_process.get(pid, 0.75)  # fallback if missing
        available_fte = available_fte_by_process.get(pid, 0)

        # Use model_forecast as the volume driver (works for both historical
        # and forward-forecasted rows, unlike actual_volume which is NaN
        # for future dates)
        proc_forecast["required_fte"] = proc_forecast["model_forecast"] / (
            standard * AVAILABLE_HOURS_PER_DAY * utilization
        )
        proc_forecast["available_fte"] = available_fte
        proc_forecast["capacity_gap"] = proc_forecast["available_fte"] - proc_forecast["required_fte"]

        results.append(proc_forecast[[
            "process_id", "forecast_date", "model_forecast",
            "required_fte", "available_fte", "capacity_gap"
        ]])

    final_df = pd.concat(results, ignore_index=True)
    final_df = final_df.rename(columns={"model_forecast": "forecasted_volume", "forecast_date": "date"})
    final_df["required_fte"] = final_df["required_fte"].round(2)
    final_df["capacity_gap"] = final_df["capacity_gap"].round(2)

    load_dataframe(final_df, "fte_requirements")

    print(f"\nWrote {len(final_df)} rows to fte_requirements")

    # Quick summary: how many understaffed days per process, on average gap
    print("\nCapacity gap summary (negative = understaffed):")
    summary = final_df.groupby("process_id").agg(
        avg_gap=("capacity_gap", "mean"),
        pct_understaffed_days=("capacity_gap", lambda x: (x < 0).mean() * 100),
    )
    for pid, row in summary.iterrows():
        name = processes.loc[pid, "process_name"]
        print(f"  {name}: avg gap {row['avg_gap']:+.2f} FTE, understaffed on {row['pct_understaffed_days']:.0f}% of days")


if __name__ == "__main__":
    main()
