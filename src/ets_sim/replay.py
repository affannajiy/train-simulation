"""Replay a real incident as a section outage and compare with the reported delays.

The news report names the affected trains and their delays but not when the outage began or
how long it lasted. So the replay fits both by grid search: for every (start, duration) pair
it runs the model once with primary delays switched off, and scores the mean absolute error
between each named train's peak simulated delay and its reported delay.

With the best fit it then runs seeded replications with the normal primary delays on, to show
how many trains the incident reaches once everyday disturbances are added (RQ1).

    python -m ets_sim.replay                       # every replay in config.yaml
    python -m ets_sim.replay --name tiroi_seremban_2026_06_14 --reps 20
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ets_sim import metrics
from ets_sim.config import load_config, project_path
from ets_sim.experiments import Scenario, baseline
from ets_sim.model import SectionOutage, simulate


def hhmm_to_s(text: str) -> float:
    """'10:15' -> 36900.0 seconds from the start of the service day."""
    h, m = str(text).split(":")
    return float(int(h) * 3600 + int(m) * 60)


def s_to_hhmm(seconds: float) -> str:
    m = int(round(seconds / 60))
    return f"{m // 60:02d}:{m % 60:02d}"


@dataclass(frozen=True)
class ReplaySpec:
    name: str
    source: str
    from_station: str
    to_station: str
    both_directions: bool
    reported_min: dict[str, float]
    starts_s: tuple[float, ...]
    durations_s: tuple[float, ...]

    def outage(self, start_s: float, duration_s: float) -> SectionOutage:
        return SectionOutage(self.name, self.from_station, self.to_station, start_s, duration_s,
                             self.both_directions)


def spec_from_config(name: str, cfg: dict) -> ReplaySpec:
    r = cfg["replays"][name]
    fit = r["fit"]
    step = float(fit["step_min"]) * 60
    if step <= 0:
        raise ValueError(f"Replay {name}: fit.step_min must be positive")
    starts = np.arange(hhmm_to_s(fit["start_from"]), hhmm_to_s(fit["start_to"]) + 1e-9, step)
    durs = np.arange(float(fit["duration_from_min"]) * 60, float(fit["duration_to_min"]) * 60 + 1e-9, step)
    return ReplaySpec(name, str(r.get("source", "")), r["from_station"], r["to_station"],
                      bool(r.get("both_directions", True)),
                      {str(k): float(v) for k, v in r["reported_delay_min"].items()},
                      tuple(float(s) for s in starts), tuple(float(d) for d in durs))


def compare(spec: ReplaySpec, events: pd.DataFrame) -> pd.DataFrame:
    """Per named train: reported delay, peak simulated delay, and the error (simulated - reported)."""
    peak = events.groupby("trip_id")["delay_s"].max() / 60
    rows = []
    for tid, rep in spec.reported_min.items():
        sim = float(peak.get(tid, math.nan))
        rows.append({"trip_id": tid, "reported_min": rep, "simulated_min": sim, "error_min": sim - rep})
    return pd.DataFrame(rows)


def fit(spec: ReplaySpec, sc: Scenario) -> pd.DataFrame:
    """Score every (start, duration) pair. One deterministic run each, primary delays off."""
    missing = [t for t in spec.reported_min if t not in {tr.trip_id for tr in sc.trips}]
    if missing:
        raise ValueError(f"Replay {spec.name}: trips not in the timetable: {missing}")
    params = sc.params.no_disruption()
    rows = []
    for start in spec.starts_s:
        for dur in spec.durations_s:
            res = simulate(sc.topo, sc.trips, params, outages=[spec.outage(start, dur)])
            err = compare(spec, res.events)["error_min"]
            rows.append({"start": s_to_hhmm(start), "start_s": start, "duration_min": dur / 60,
                         "mae_min": float(err.abs().mean()), "rmse_min": float(np.sqrt((err ** 2).mean())),
                         "bias_min": float(err.mean())})
    return pd.DataFrame(rows).sort_values("mae_min", kind="stable").reset_index(drop=True)


def reach_with_noise(spec: ReplaySpec, sc: Scenario, outage: SectionOutage, n_reps: int, seed: int) -> pd.DataFrame:
    """Seeded replications with primary delays on: how far the incident spreads (RQ1)."""
    rows = []
    for r in range(n_reps):
        res = simulate(sc.topo, sc.trips, sc.params, seed=seed + r, outages=[outage])
        reach = metrics.incident_reach(res.events, res.increments, outage.root_id)
        late = reach[reach["peak_delay_min"] > sc.threshold_s / 60]
        rows.append({"rep": r,
                     "trains_reached": len(reach),
                     "trains_late_from_incident": len(late),
                     "named_trains_reached": int(reach["trip_id"].isin(list(spec.reported_min)).sum()),
                     "outage_min": float(reach["direct_min"].sum()),
                     "knock_on_min": float(reach["knock_on_min"].sum())})
    df = pd.DataFrame(rows)
    df["knock_on_per_outage_min"] = df["knock_on_min"] / df["outage_min"].where(df["outage_min"] > 0)
    return df


def run_replay(name: str, cfg: dict, n_reps: int, seed: int) -> dict[str, pd.DataFrame]:
    sc = baseline(cfg)
    spec = spec_from_config(name, cfg)
    grid = fit(spec, sc)
    best = grid.iloc[0]
    outage = spec.outage(float(best["start_s"]), float(best["duration_min"]) * 60)

    det = simulate(sc.topo, sc.trips, sc.params.no_disruption(), outages=[outage])
    reach = metrics.incident_reach(det.events, det.increments, outage.root_id)
    reach["named_in_report"] = reach["trip_id"].isin(list(spec.reported_min))
    noisy = reach_with_noise(spec, sc, outage, n_reps, seed)
    cols = ["trains_reached", "trains_late_from_incident", "named_trains_reached", "outage_min",
            "knock_on_min", "knock_on_per_outage_min"]
    summary = pd.DataFrame([{"metric": c, **dict(zip(("mean", "ci_lo", "ci_hi"), metrics.mean_ci(noisy[c])))}
                            for c in cols])
    return {"fit_grid": grid, "comparison": compare(spec, det.events), "reach": reach,
            "noise_summary": summary}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config")
    parser.add_argument("--name", nargs="*", help="replay names from config.yaml (default: all)")
    parser.add_argument("--reps", type=int, help="replications with primary delays on (default from config)")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    ex = cfg["experiments"]
    n, seed = args.reps or int(ex["replications"]), int(ex["base_seed"])
    out = project_path(cfg["data"]["results_dir"])
    out.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.width", 160)

    for name in args.name or list(cfg.get("replays") or {}):
        res = run_replay(name, cfg, n, seed)
        best = res["fit_grid"].iloc[0]
        print(f"\n== replay {name} ==")
        print(f"Best fit: outage from {best['start']} for {best['duration_min']:.0f} min, "
              f"MAE {best['mae_min']:.1f} min, bias {best['bias_min']:+.1f} min")
        print("\nNamed trains (peak simulated delay vs reported):")
        print(res["comparison"].round(1).to_string(index=False))
        print("\nTrains reached in the best-fit run (primary delays off):")
        print(res["reach"].round(1).to_string(index=False))
        print(f"\nWith primary delays on ({n} reps, mean and 95% CI):")
        print(res["noise_summary"].round(2).to_string(index=False))
        for key, df in res.items():
            df.to_csv(out / f"replay_{name}_{key}.csv", index=False)
    print(f"\nResults written to {out}")


if __name__ == "__main__":
    main()
