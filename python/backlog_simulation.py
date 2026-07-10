"""
backlog_simulation.py
======================
Projects each process's backlog forward day by day, given forecasted
inflow (volume) and available processing capacity (available_fte x
productivity standard x hours x utilization).

Core simulation logic, run per process per day in date order:

    capacity_today   = available_fte x productivity_standard x hours x utilization
    backlog_tomorrow = max(0, backlog_today + inflow_today - capacity_today)

This is a simple inventory/queue model: backlog only grows when inflow
outpaces capacity, and capacity can only clear what's actually in the
queue (it can't "borrow" future work). Starting backlog is taken from the
real current open-item count per process (from work_items).

Writes results to a new `backlog_projection` table:
    process_id, date, inflow, capacity, backlog_start, backlog_end

Usage:
    python backlog_simulation.py
"""

import pandas as pd

from etl_pipeline import (
    get_processes,
    get_work_items,
    extract_table,
    load_dataframe,
    apply_kpi_views,
)


def get_starting_backlog() -> pd.Series:
    """
    Current open item count per process (completed_date IS NULL),
    used as day-zero backlog for the simulation.
    """
    apply_kpi_views()
    items = get_work_items()
    open_items = items[items["completed_date"].isna()]
    return open_items.groupby("process_id").size()


def simulate_process_backlog(process_id: int, fte_df: pd.DataFrame, starting_backlog: float) -> pd.DataFrame:
    fte_df = fte_df.sort_values("date").reset_index(drop=True)

    rows = []
    backlog = starting_backlog

    for _, row in fte_df.iterrows():
        inflow = row["forecasted_volume"]

        # Capacity in items/day = available_fte x (items-per-FTE implied by
        # this day's required_fte calc), which backs out the per-agent
        # daily throughput (productivity_standard x hours x utilization)
        # without needing to re-import those constants here.
        items_per_fte = (inflow / row["required_fte"]) if row["required_fte"] > 0 else 0
        capacity = row["available_fte"] * items_per_fte

        backlog_start = backlog
        backlog_end = max(0.0, backlog_start + inflow - capacity)
        backlog = backlog_end

        rows.append({
            "process_id": process_id,
            "date": row["date"],
            "inflow": round(inflow, 1),
            "capacity": round(capacity, 1),
            "backlog_start": round(backlog_start, 1),
            "backlog_end": round(backlog_end, 1),
        })

    return pd.DataFrame(rows)


def main():
    processes = get_processes().set_index("process_id")
    fte_requirements = extract_table("fte_requirements")
    starting_backlog = get_starting_backlog()

    print("Starting backlog (current open items) by process:")
    for pid in processes.index:
        count = starting_backlog.get(pid, 0)
        print(f"  {processes.loc[pid, 'process_name']}: {count}")

    all_results = []
    for pid, proc in processes.iterrows():
        proc_fte = fte_requirements[fte_requirements["process_id"] == pid]
        start_backlog = float(starting_backlog.get(pid, 0))
        result = simulate_process_backlog(pid, proc_fte, start_backlog)
        all_results.append(result)

        end_backlog = result.iloc[-1]["backlog_end"]
        peak_backlog = result["backlog_end"].max()
        print(f"\n{proc['process_name']}: starts at {start_backlog:.0f}, "
              f"peaks at {peak_backlog:.0f}, ends projection at {end_backlog:.0f}")

    final_df = pd.concat(all_results, ignore_index=True)
    load_dataframe(final_df, "backlog_projection")
    print(f"\nWrote {len(final_df)} rows to backlog_projection")


if __name__ == "__main__":
    main()
