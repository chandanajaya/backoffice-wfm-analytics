"""
reallocation_model.py
======================
Rule-based reallocation: on any given day, if a process is understaffed
(negative capacity_gap) and another process has spare capacity (positive
capacity_gap), move cross-trained agents from the surplus process to the
deficit process for that day.

Why rule-based rather than an LP/optimization solver: with only 3 processes
and ~16 agents, the search space is tiny — a greedy day-by-day rule gets
the same practical answer as an optimizer would, without the extra
dependency (pulp/OR-Tools) or the harder-to-explain math. If this were
scaled to dozens of processes and hundreds of agents, optimization would
be the better choice; noted here as a clear "if I had more time" extension.

Algorithm, per day:
    1. Split processes into surplus (capacity_gap > 0) and deficit (< 0).
    2. For each deficit process (largest deficit first), look for agents
       whose primary process is a surplus process AND who are cross-trained
       on this deficit process.
    3. Move one agent at a time from the surplus process to the deficit
       process until either the deficit is covered or no eligible agents
       remain — decrementing the source process's surplus as agents move,
       so the same agent-day isn't double-counted across processes.

Writes two tables:
    reallocation_recommendations: date, agent_id, agent_name, from_process_id, to_process_id
    fte_requirements_post_reallocation: process_id, date, required_fte, available_fte,
                                         capacity_gap_before, capacity_gap_after

Usage:
    python reallocation_model.py
"""

import pandas as pd

from etl_pipeline import get_agents, get_agent_process_skills, extract_table, load_dataframe


def build_cross_trained_lookup(agents: pd.DataFrame, skills: pd.DataFrame) -> pd.DataFrame:
    """
    Agents who are cross-trained: they have a skill row for a process that
    isn't their primary process. Returns one row per (agent, secondary_process).
    """
    merged = skills.merge(agents[["agent_id", "primary_process_id", "agent_name"]], on="agent_id")
    cross_trained = merged[merged["process_id"] != merged["primary_process_id"]].copy()
    cross_trained = cross_trained.rename(columns={"process_id": "secondary_process_id"})
    return cross_trained[["agent_id", "agent_name", "primary_process_id", "secondary_process_id"]]


def reallocate_for_day(day_gaps: pd.DataFrame, cross_trained: pd.DataFrame) -> tuple[list, dict]:
    """
    day_gaps: DataFrame with process_id, capacity_gap for a single date.
    Returns (list of recommendation dicts, dict of {process_id: adjusted_gap}).
    """
    gaps = dict(zip(day_gaps["process_id"], day_gaps["capacity_gap"]))
    recommendations = []

    deficit_processes = sorted(
        [pid for pid, g in gaps.items() if g < 0],
        key=lambda pid: gaps[pid]  # most negative (biggest deficit) first
    )

    for deficit_pid in deficit_processes:
        while gaps[deficit_pid] < 0:
            # Find a cross-trained agent whose primary process currently has
            # surplus and who is skilled on this deficit process
            candidates = cross_trained[
                (cross_trained["secondary_process_id"] == deficit_pid) &
                (cross_trained["primary_process_id"].map(lambda pid: gaps.get(pid, 0) > 0))
            ]
            if candidates.empty:
                break  # no one available to help this process today

            agent = candidates.iloc[0]
            from_pid = agent["primary_process_id"]

            # Move 1.0 FTE for the day
            gaps[from_pid] -= 1.0
            gaps[deficit_pid] += 1.0

            recommendations.append({
                "agent_id": agent["agent_id"],
                "agent_name": agent["agent_name"],
                "from_process_id": from_pid,
                "to_process_id": deficit_pid,
            })

            # Remove this agent from further consideration today (can't be
            # in two places on the same day)
            cross_trained = cross_trained[cross_trained["agent_id"] != agent["agent_id"]]

    return recommendations, gaps


def main():
    agents = get_agents()
    skills = get_agent_process_skills()
    fte_requirements = extract_table("fte_requirements")

    cross_trained_master = build_cross_trained_lookup(agents, skills)
    print(f"Found {cross_trained_master['agent_id'].nunique()} cross-trained agents "
          f"across {len(cross_trained_master)} process pairings.\n")

    all_recommendations = []
    post_reallocation_rows = []

    for day, day_gaps in fte_requirements.groupby("date"):
        recs, adjusted_gaps = reallocate_for_day(
            day_gaps[["process_id", "capacity_gap"]],
            cross_trained_master
        )

        for rec in recs:
            rec["date"] = day
            all_recommendations.append(rec)

        for _, row in day_gaps.iterrows():
            post_reallocation_rows.append({
                "process_id": row["process_id"],
                "date": day,
                "required_fte": row["required_fte"],
                "available_fte": row["available_fte"],
                "capacity_gap_before": row["capacity_gap"],
                "capacity_gap_after": round(adjusted_gaps[row["process_id"]], 2),
            })

    recs_df = pd.DataFrame(all_recommendations, columns=[
        "agent_id", "agent_name", "from_process_id", "to_process_id", "date"
    ])
    post_df = pd.DataFrame(post_reallocation_rows)

    load_dataframe(recs_df, "reallocation_recommendations")
    load_dataframe(post_df, "fte_requirements_post_reallocation")

    print(f"Generated {len(recs_df)} reallocation recommendations "
          f"across {recs_df['date'].nunique() if not recs_df.empty else 0} distinct days.\n")

    # Before/after summary per process
    processes = extract_table("processes").set_index("process_id")
    print("Understaffed-days before vs after reallocation:")
    for pid in processes.index:
        proc_rows = post_df[post_df["process_id"] == pid]
        before_pct = (proc_rows["capacity_gap_before"] < 0).mean() * 100
        after_pct = (proc_rows["capacity_gap_after"] < 0).mean() * 100
        print(f"  {processes.loc[pid, 'process_name']}: {before_pct:.0f}% -> {after_pct:.0f}%")


if __name__ == "__main__":
    main()
