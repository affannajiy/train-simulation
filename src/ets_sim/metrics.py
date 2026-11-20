"""Reliability metrics from simulation output.

All functions take the `events` and `increments` frames produced by model.simulate (or
several replications concatenated with a `rep` column) and return plain DataFrames or dicts.
"""

from __future__ import annotations

import math

import pandas as pd

# Two-sided 95% Student t critical values by degrees of freedom; above 30 the normal value is used.
_T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262,
        10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110,
        18: 2.101, 19: 2.093, 20: 2.086, 21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060,
        26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042}


def mean_ci(values: pd.Series) -> tuple[float, float, float]:
    """Mean and 95% confidence interval across replications (Student t)."""
    v = pd.Series(values, dtype=float).dropna()
    n = len(v)
    if n == 0:
        return (math.nan, math.nan, math.nan)
    m = float(v.mean())
    if n == 1:
        return (m, m, m)
    half = _T95.get(n - 1, 1.96) * float(v.std(ddof=1)) / math.sqrt(n)
    return (m, m - half, m + half)


def _arrivals(events: pd.DataFrame) -> pd.DataFrame:
    return events[events["kind"] == "arr"]


def on_time(events: pd.DataFrame, threshold_s: float) -> dict[str, float]:
    """On-time % at every stop arrival, and at destinations only."""
    arr = _arrivals(events)
    dest = arr[arr["is_destination"]]
    return {
        "on_time_all_pct": 100.0 * float((arr["delay_s"] <= threshold_s).mean()) if len(arr) else math.nan,
        "on_time_dest_pct": 100.0 * float((dest["delay_s"] <= threshold_s).mean()) if len(dest) else math.nan,
    }


def station_delay(events: pd.DataFrame) -> pd.DataFrame:
    """Average and maximum arrival delay per station, in minutes."""
    arr = _arrivals(events)
    out = arr.groupby("station")["delay_s"].agg(["mean", "max", "count"]) / [60, 60, 1]
    out.columns = ["avg_delay_min", "max_delay_min", "arrivals"]
    return out.sort_values("avg_delay_min", ascending=False).reset_index()


def delay_by_cause(increments: pd.DataFrame) -> dict[str, float]:
    """Total minutes added per cause. Recovery is reported as a positive amount won back."""
    s = increments.groupby("cause")["amount_s"].sum() / 60
    return {
        "primary_min": float(s.get("primary", 0.0)),
        "knock_on_min": float(s.get("knock_on", 0.0)),
        "timetable_conflict_min": float(s.get("timetable_conflict", 0.0)),
        "recovered_min": float(-s.get("recovery", 0.0)),
    }


def primary_impact(increments: pd.DataFrame) -> pd.DataFrame:
    """For each primary delay: its size, the knock-on it caused, and how many other trains it reached."""
    prim = increments[increments["cause"] == "primary"]
    if prim.empty:
        return pd.DataFrame(columns=["root_id", "trip_id", "station", "primary_min", "knock_on_min",
                                     "trains_affected"])
    keys = ["rep", "root_id"] if "rep" in increments.columns else ["root_id"]
    base = prim.groupby(keys).agg(trip_id=("trip_id", "first"), station=("location", "first"),
                                  primary_min=("amount_s", "sum"))
    base["primary_min"] /= 60
    ko = increments[increments["cause"] == "knock_on"]
    # Root ids look like "P:<trip_id>@<station>". A train is not "affected" by its own delay.
    ko = ko[ko["trip_id"] != ko["root_id"].str.slice(2).str.split("@").str[0]]
    spread = ko.groupby(keys).agg(knock_on_min=("amount_s", "sum"), trains_affected=("trip_id", "nunique"))
    spread["knock_on_min"] /= 60
    out = base.join(spread, how="left").fillna({"knock_on_min": 0.0, "trains_affected": 0})
    out["trains_affected"] = out["trains_affected"].astype(int)
    return out.reset_index()


def bottlenecks(increments: pd.DataFrame, n_reps: int = 1) -> pd.DataFrame:
    """Rank locations (block sections and platforms) by the secondary delay generated there.

    Secondary = knock_on + timetable_conflict. Values are per replication averages.
    """
    sec = increments[increments["cause"].isin(["knock_on", "timetable_conflict"])]
    if sec.empty:
        return pd.DataFrame(columns=["location", "location_type", "knock_on_min", "timetable_conflict_min",
                                     "secondary_min", "waits"])
    piv = sec.pivot_table(index=["location", "location_type"], columns="cause", values="amount_s",
                          aggfunc="sum", fill_value=0.0)
    for col in ("knock_on", "timetable_conflict"):
        if col not in piv:
            piv[col] = 0.0
    out = pd.DataFrame({
        "knock_on_min": piv["knock_on"] / 60 / n_reps,
        "timetable_conflict_min": piv["timetable_conflict"] / 60 / n_reps,
    })
    out["secondary_min"] = out["knock_on_min"] + out["timetable_conflict_min"]
    out["waits"] = sec.groupby(["location", "location_type"]).size() / n_reps
    return out.sort_values("secondary_min", ascending=False).reset_index()


def train_impact(increments: pd.DataFrame, n_reps: int = 1) -> pd.DataFrame:
    """Rank trains by how many other trains they held up and the minutes they passed on."""
    sec = increments[increments["cause"].isin(["knock_on", "timetable_conflict"]) &
                     (increments["blocking_trip_id"] != "")]
    if sec.empty:
        return pd.DataFrame(columns=["blocking_trip_id", "trains_held", "minutes_passed_on"])
    keys = ["rep", "blocking_trip_id"] if "rep" in sec.columns else ["blocking_trip_id"]
    per = sec.groupby(keys).agg(trains_held=("trip_id", "nunique"), minutes_passed_on=("amount_s", "sum"))
    per["minutes_passed_on"] /= 60
    out = per.groupby("blocking_trip_id").sum() / n_reps
    return out.sort_values("minutes_passed_on", ascending=False).reset_index()


def summary(events: pd.DataFrame, increments: pd.DataFrame, threshold_s: float) -> dict[str, float]:
    """One row of headline numbers for a single replication."""
    out = on_time(events, threshold_s)
    arr = _arrivals(events)
    dest = arr[arr["is_destination"]]
    out["avg_dest_delay_min"] = float(dest["delay_s"].mean() / 60) if len(dest) else math.nan
    out["max_delay_min"] = float(arr["delay_s"].max() / 60) if len(arr) else math.nan
    out.update(delay_by_cause(increments))
    imp = primary_impact(increments)
    out["primary_events"] = int(len(imp))
    out["avg_trains_affected_per_primary"] = float(imp["trains_affected"].mean()) if len(imp) else 0.0
    return out
