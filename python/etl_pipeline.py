"""
etl_pipeline.py
================
Central data-access layer for the WFM analytics pipeline. Every other
Python script (forecast_volume.py, fte_capacity_model.py, backlog_simulation.py,
reallocation_model.py) imports from here rather than opening its own
database connection — one place to change if the DB path changes.

Uses plain sqlite3 rather than SQLAlchemy: the project is SQLite-only,
so this keeps the dependency list smaller. If you later migrate to
Postgres, this is the only file you'd need to change.

Usage as a library:
    from etl_pipeline import extract_table, extract_query, load_dataframe

Usage standalone (sanity check):
    python etl_pipeline.py
"""

import sqlite3
from pathlib import Path

import pandas as pd

# Resolve the DB path relative to this file, so it works regardless of
# what directory you run the script from.
DB_PATH = Path(__file__).resolve().parent.parent / "backoffice_wfm.db"


def get_connection() -> sqlite3.Connection:
    """Return a sqlite3 connection to the project's database."""
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Database not found at {DB_PATH}. "
            "Run data/generate_synthetic_data.py first."
        )
    return sqlite3.connect(DB_PATH)


def extract_table(table_name: str) -> pd.DataFrame:
    """Pull an entire table (or view) into a DataFrame."""
    with get_connection() as conn:
        return pd.read_sql_query(f"SELECT * FROM {table_name}", conn)


def extract_query(sql: str, params: tuple = ()) -> pd.DataFrame:
    """Run an arbitrary SQL query and return the result as a DataFrame."""
    with get_connection() as conn:
        return pd.read_sql_query(sql, conn, params=params)


def load_dataframe(df: pd.DataFrame, table_name: str, if_exists: str = "replace") -> None:
    """
    Write a DataFrame back to the database as a new/derived table.
    Used by the modeling scripts to persist their outputs
    (e.g. fte_requirements, backlog_projection, reallocation_recommendations)
    so Power BI has one place to read everything from.
    """
    with get_connection() as conn:
        df.to_sql(table_name, conn, if_exists=if_exists, index=False)


def apply_kpi_views() -> None:
    """(Re)create the KPI views defined in sql/views_kpis.sql on this database."""
    views_path = Path(__file__).resolve().parent.parent / "sql" / "views_kpis.sql"
    with get_connection() as conn:
        conn.executescript(views_path.read_text())


# ---------------------------------------------------------
# Convenience extractors for the core fact/dimension tables
# ---------------------------------------------------------
def get_processes() -> pd.DataFrame:
    return extract_table("processes")


def get_agents() -> pd.DataFrame:
    return extract_table("agents")


def get_agent_process_skills() -> pd.DataFrame:
    return extract_table("agent_process_skills")


def get_work_items() -> pd.DataFrame:
    df = extract_table("work_items")
    for col in ["received_date", "due_date", "completed_date"]:
        df[col] = pd.to_datetime(df[col])
    return df


def get_productivity_logs() -> pd.DataFrame:
    df = extract_table("productivity_logs")
    df["log_date"] = pd.to_datetime(df["log_date"])
    return df


def get_volume_forecast_actuals() -> pd.DataFrame:
    df = extract_table("volume_forecast_actuals")
    df["forecast_date"] = pd.to_datetime(df["forecast_date"])
    return df


def get_attrition() -> pd.DataFrame:
    df = extract_table("attrition")
    df["exit_date"] = pd.to_datetime(df["exit_date"])
    return df


if __name__ == "__main__":
    # Quick sanity check when run directly: confirm the DB is reachable,
    # KPI views apply cleanly, and every core table has rows.
    apply_kpi_views()

    checks = {
        "processes": get_processes(),
        "agents": get_agents(),
        "agent_process_skills": get_agent_process_skills(),
        "work_items": get_work_items(),
        "productivity_logs": get_productivity_logs(),
        "volume_forecast_actuals": get_volume_forecast_actuals(),
        "attrition": get_attrition(),
    }
    print(f"Connected to: {DB_PATH}\n")
    for name, df in checks.items():
        print(f"{name:28s} {len(df):>8,} rows")
