"""
WAT tool: Time-series forecasting of AMR resistance rates from database history.

Primary method: Facebook Prophet (if installed).
Fallback method: 3-period moving average + linear regression slope
  (pure stdlib/numpy — always available).

Minimum 6 historical time points required. Returns "insufficient_data" status
if fewer points exist.

Install Prophet: pip install prophet  (requires pystan + C++ compiler)
If Prophet is not installed, the tool gracefully falls back without error.

Input JSON (--input or --input-file):
{
  "db_path": ".tmp/wat_genomics.db",
  "forecast_type": "resistance_rate",   // resistance_rate | mdr_rate | gene_frequency
  "filters": {
    "antibiotic": "Meropenem",
    "region": "Punjab",
    "pathogen": "Klebsiella pneumoniae",
    "days_back": 730
  },
  "forecast_horizon_months": 6,
  "output_file": ".tmp/forecast_result.json"
}

Output JSON:
{
  "status": "ok",
  "forecast_type": "resistance_rate",
  "method": "prophet | moving_average",
  "historical_data_points": 24,
  "trend_direction": "rising | falling | stable",
  "trend_slope_per_month": 1.4,
  "forecast": [
    {
      "period": "2026-06",
      "predicted_rate": 78.3,
      "lower_bound": 71.2,
      "upper_bound": 85.4
    }
  ],
  "output_file": ".tmp/forecast_result.json"
}
"""

import argparse
import json
import math
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DEFAULT_DB = ".tmp/wat_genomics.db"
MIN_DATA_POINTS = 6


def get_conn(db_path: str) -> sqlite3.Connection:
    if not Path(db_path).exists():
        raise FileNotFoundError(f"Database not found: {db_path}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def fetch_resistance_rate_history(conn, filters: dict) -> list:
    antibiotic = filters.get("antibiotic")
    region = filters.get("region")
    pathogen = filters.get("pathogen")
    days_back = filters.get("days_back", 730)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    params = [cutoff]
    where = ["ps.created_at >= ?"]
    if antibiotic:
        where.append("ar.antibiotic = ?")
        params.append(antibiotic)
    if region:
        where.append("ps.region = ?")
        params.append(region)
    if pathogen:
        where.append("ps.pathogen_name = ?")
        params.append(pathogen)

    rows = conn.execute(
        f"""SELECT strftime('%Y-%m', ps.created_at) as period,
                   COUNT(*) as total,
                   SUM(CASE WHEN ar.interpretation='R' THEN 1 ELSE 0 END) as resistant
            FROM ast_records ar
            JOIN phenotypic_samples ps ON ar.pheno_sample_pk = ps.pheno_sample_pk
            WHERE {' AND '.join(where)}
            GROUP BY period
            ORDER BY period""",
        params,
    ).fetchall()

    return [
        {
            "period": r["period"],
            "rate": round(r["resistant"] / r["total"] * 100, 1) if r["total"] > 0 else 0.0,
            "total": r["total"],
            "resistant": r["resistant"],
        }
        for r in rows
    ]


def fetch_mdr_rate_history(conn, filters: dict) -> list:
    region = filters.get("region")
    pathogen = filters.get("pathogen")
    days_back = filters.get("days_back", 730)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    params = [cutoff]
    where = ["ps.created_at >= ?"]
    if region:
        where.append("ps.region = ?")
        params.append(region)
    if pathogen:
        where.append("ps.pathogen_name = ?")
        params.append(pathogen)

    rows = conn.execute(
        f"""SELECT strftime('%Y-%m', ps.created_at) as period,
                   COUNT(*) as total,
                   SUM(CASE WHEN mc.mdr_category IN ('MDR','XDR','PDR') THEN 1 ELSE 0 END) as mdr_count
            FROM mdr_classifications mc
            JOIN phenotypic_samples ps ON mc.pheno_sample_pk = ps.pheno_sample_pk
            WHERE {' AND '.join(where)}
            GROUP BY period
            ORDER BY period""",
        params,
    ).fetchall()

    return [
        {
            "period": r["period"],
            "rate": round(r["mdr_count"] / r["total"] * 100, 1) if r["total"] > 0 else 0.0,
            "total": r["total"],
        }
        for r in rows
    ]


def fetch_gene_frequency_history(conn, filters: dict) -> list:
    gene = filters.get("gene")
    region = filters.get("region")
    days_back = filters.get("days_back", 730)
    if not gene:
        raise ValueError("'gene' filter required for gene_frequency forecast")

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    params = [gene, cutoff]
    where = ["ah.gene = ?", "pr.timestamp >= ?"]
    if region:
        where.append("pr.region = ?")
        params.append(region)

    rows = conn.execute(
        f"""SELECT strftime('%Y-%m', pr.timestamp) as period,
                   COUNT(DISTINCT s.sample_id) as gene_count
            FROM amr_hits ah
            JOIN amr_results ar ON ah.amr_pk = ar.amr_pk
            JOIN samples s ON ar.sample_pk = s.sample_pk
            JOIN pipeline_runs pr ON ar.run_id = pr.run_id
            WHERE {' AND '.join(where)}
            GROUP BY period
            ORDER BY period""",
        params,
    ).fetchall()

    return [{"period": r["period"], "rate": float(r["gene_count"]), "total": r["gene_count"]}
            for r in rows]


def linear_slope(xs: list, ys: list) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    xm = sum(xs) / n
    ym = sum(ys) / n
    num = sum((x - xm) * (y - ym) for x, y in zip(xs, ys))
    den = sum((x - xm) ** 2 for x in xs)
    return num / den if den != 0 else 0.0


def moving_average_forecast(data: list, horizon_months: int) -> tuple:
    rates = [d["rate"] for d in data]
    periods = [d["period"] for d in data]

    # Slope using period ordinals
    xs = list(range(len(rates)))
    slope = linear_slope(xs, rates)
    direction = "rising" if slope > 0.5 else "falling" if slope < -0.5 else "stable"

    # 3-period moving average for last known point
    window = min(3, len(rates))
    base_rate = sum(rates[-window:]) / window

    # Std dev for uncertainty bands
    if len(rates) > 1:
        mean = sum(rates) / len(rates)
        std = math.sqrt(sum((r - mean) ** 2 for r in rates) / (len(rates) - 1))
    else:
        std = 5.0

    # Generate future periods
    last_period = periods[-1]  # e.g., "2026-04"
    year, month = int(last_period[:4]), int(last_period[5:7])

    forecast = []
    for i in range(1, horizon_months + 1):
        month += 1
        if month > 12:
            month = 1
            year += 1
        predicted = base_rate + slope * i
        predicted = max(0.0, min(100.0, predicted))
        lower = max(0.0, predicted - 1.5 * std)
        upper = min(100.0, predicted + 1.5 * std)
        forecast.append({
            "period": f"{year}-{month:02d}",
            "predicted_rate": round(predicted, 1),
            "lower_bound": round(lower, 1),
            "upper_bound": round(upper, 1),
        })

    return forecast, direction, round(slope, 3)


def prophet_forecast(data: list, horizon_months: int) -> tuple:
    from prophet import Prophet
    import pandas as pd

    df = pd.DataFrame({
        "ds": pd.to_datetime([d["period"] + "-01" for d in data]),
        "y": [d["rate"] for d in data],
    })

    model = Prophet(yearly_seasonality=True, weekly_seasonality=False,
                    daily_seasonality=False, interval_width=0.95)
    model.fit(df)

    future = model.make_future_dataframe(periods=horizon_months, freq="MS")
    forecast_df = model.predict(future)

    forecast_rows = forecast_df.tail(horizon_months)
    forecast = [
        {
            "period": row["ds"].strftime("%Y-%m"),
            "predicted_rate": round(max(0.0, min(100.0, row["yhat"])), 1),
            "lower_bound": round(max(0.0, row["yhat_lower"]), 1),
            "upper_bound": round(min(100.0, row["yhat_upper"]), 1),
        }
        for _, row in forecast_rows.iterrows()
    ]

    rates = [d["rate"] for d in data]
    xs = list(range(len(rates)))
    slope = linear_slope(xs, rates)
    direction = "rising" if slope > 0.5 else "falling" if slope < -0.5 else "stable"
    return forecast, direction, round(slope, 3)


def main():
    parser = argparse.ArgumentParser(description="Forecast AMR resistance trends")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--input", help="JSON string spec")
    group.add_argument("--input-file", help="Path to JSON spec file")
    parser.add_argument("--output-file", help="Optional path to write result JSON")
    args = parser.parse_args()

    try:
        if args.input_file:
            with open(args.input_file) as f:
                spec = json.load(f)
        else:
            spec = json.loads(args.input)

        db_path = spec.get("db_path", DEFAULT_DB)
        forecast_type = spec.get("forecast_type", "resistance_rate")
        filters = spec.get("filters", {})
        horizon = spec.get("forecast_horizon_months", 6)

        conn = get_conn(db_path)
        try:
            if forecast_type == "resistance_rate":
                history = fetch_resistance_rate_history(conn, filters)
            elif forecast_type == "mdr_rate":
                history = fetch_mdr_rate_history(conn, filters)
            elif forecast_type == "gene_frequency":
                history = fetch_gene_frequency_history(conn, filters)
            else:
                raise ValueError(
                    f"Unknown forecast_type '{forecast_type}'. "
                    "Use: resistance_rate, mdr_rate, gene_frequency"
                )
        finally:
            conn.close()

        if len(history) < MIN_DATA_POINTS:
            result = {
                "status": "insufficient_data",
                "message": (
                    f"Need ≥{MIN_DATA_POINTS} monthly data points for forecasting; "
                    f"found {len(history)}. Add more historical phenotypic data."
                ),
                "historical_data_points": len(history),
                "forecast_type": forecast_type,
                "filters": filters,
            }
        else:
            # Try Prophet first, fall back to moving average
            try:
                forecast, direction, slope = prophet_forecast(history, horizon)
                method = "prophet"
            except ImportError:
                forecast, direction, slope = moving_average_forecast(history, horizon)
                method = "moving_average"

            result = {
                "status": "ok",
                "forecast_type": forecast_type,
                "method": method,
                "filters": filters,
                "historical_data_points": len(history),
                "historical": history,
                "trend_direction": direction,
                "trend_slope_per_month": slope,
                "forecast_horizon_months": horizon,
                "forecast": forecast,
            }

        output_file = spec.get("output_file", ".tmp/forecast_result.json")
        os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)
        with open(output_file, "w") as f:
            json.dump(result, f, indent=2)
        result["output_file"] = output_file

    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}), file=sys.stderr)
        sys.exit(1)

    output = json.dumps(result, indent=2)
    print(output)

    if args.output_file:
        os.makedirs(os.path.dirname(args.output_file) or ".", exist_ok=True)
        with open(args.output_file, "w") as f:
            f.write(output)


if __name__ == "__main__":
    main()
