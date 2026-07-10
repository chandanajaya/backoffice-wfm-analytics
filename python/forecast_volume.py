"""
forecast_volume.py
===================
Forecasts daily work-item volume per process using a regression-based
model: linear trend + day-of-week seasonality + day-of-month effect
(captures month-end spikes like Billing & Invoicing).

Deliberately avoids heavyweight forecasting libraries (statsmodels,
Prophet) — they add install friction (Prophet in particular needs a C++
toolchain on Windows) for a project this size. A well-explained regression
model is easier to defend in an interview anyway: you can walk through
exactly what each coefficient means.

Writes results to a new `volume_forecast_model` table:
    process_id, forecast_date, actual_volume, model_forecast, is_holdout

Usage:
    python forecast_volume.py
"""

import numpy as np
import pandas as pd

from etl_pipeline import get_volume_forecast_actuals, get_processes, load_dataframe

HOLDOUT_DAYS = 30       # last N days used to validate the model
FORECAST_HORIZON = 30    # days to forecast beyond the end of the dataset


def build_features(dates: pd.Series) -> np.ndarray:
    """
    Build the design matrix for the regression:
      - linear trend (days since start)
      - day-of-week dummies (6 columns, Monday is the reference)
      - day-of-month proximity-to-month-end (captures spikes)
      - intercept
    """
    start = dates.min()
    trend = (dates - start).dt.days.to_numpy()

    dow = dates.dt.dayofweek.to_numpy()  # 0=Mon .. 6=Sun
    dow_dummies = np.zeros((len(dates), 6))
    for d in range(1, 7):  # skip Monday (0) as reference category
        dow_dummies[:, d - 1] = (dow == d).astype(float)

    days_in_month = dates.dt.days_in_month.to_numpy()
    day_of_month = dates.dt.day.to_numpy()
    month_end_proximity = np.exp(-((days_in_month - day_of_month) ** 2) / 8.0)

    intercept = np.ones(len(dates))

    return np.column_stack([intercept, trend, dow_dummies, month_end_proximity])


def fit_and_forecast(process_df: pd.DataFrame, process_id: int) -> pd.DataFrame:
    process_df = process_df.sort_values("forecast_date").reset_index(drop=True)

    train_df = process_df.iloc[:-HOLDOUT_DAYS]
    holdout_df = process_df.iloc[-HOLDOUT_DAYS:]

    X_train = build_features(train_df["forecast_date"])
    y_train = train_df["actual_volume"].to_numpy()

    coeffs, *_ = np.linalg.lstsq(X_train, y_train, rcond=None)

    # In-sample + holdout predictions
    X_all = build_features(process_df["forecast_date"])
    process_df = process_df.copy()
    process_df["model_forecast"] = np.clip(X_all @ coeffs, 0, None)
    process_df["is_holdout"] = process_df["forecast_date"].isin(holdout_df["forecast_date"])

    # Evaluate holdout accuracy
    holdout_actuals = holdout_df["actual_volume"].to_numpy()
    holdout_preds = process_df.loc[process_df["is_holdout"], "model_forecast"].to_numpy()
    mae = np.mean(np.abs(holdout_actuals - holdout_preds))
    mape = np.mean(np.abs((holdout_actuals - holdout_preds) / np.maximum(holdout_actuals, 1))) * 100
    print(f"  Process {process_id}: holdout MAE={mae:.1f}, MAPE={mape:.1f}%")

    # Forecast forward beyond the end of the dataset
    last_date = process_df["forecast_date"].max()
    future_dates = pd.Series(pd.date_range(last_date + pd.Timedelta(days=1), periods=FORECAST_HORIZON))
    X_future = build_features(pd.concat([train_df["forecast_date"], future_dates], ignore_index=True))
    X_future = X_future[-FORECAST_HORIZON:]  # only keep the future rows' features
    future_forecast = np.clip(X_future @ coeffs, 0, None)

    future_df = pd.DataFrame({
        "process_id": process_id,
        "forecast_date": future_dates,
        "actual_volume": np.nan,
        "model_forecast": future_forecast,
        "is_holdout": False,
    })

    process_df["process_id"] = process_id
    result = pd.concat([
        process_df[["process_id", "forecast_date", "actual_volume", "model_forecast", "is_holdout"]],
        future_df
    ], ignore_index=True)

    return result


def main():
    processes = get_processes()
    volume_df = get_volume_forecast_actuals()

    all_results = []
    print("Fitting per-process forecast models...")
    for _, proc in processes.iterrows():
        process_id = proc["process_id"]
        process_volume = volume_df[volume_df["process_id"] == process_id]
        result = fit_and_forecast(process_volume, process_id)
        all_results.append(result)

    final_df = pd.concat(all_results, ignore_index=True)
    final_df["forecast_date"] = final_df["forecast_date"].dt.strftime("%Y-%m-%d")

    load_dataframe(final_df, "volume_forecast_model")
    print(f"\nWrote {len(final_df)} rows to volume_forecast_model")
    print(f"  (includes {FORECAST_HORIZON} days of forward forecast per process, beyond the historical data)")


if __name__ == "__main__":
    main()
