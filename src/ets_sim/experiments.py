"""Seeded replications and the experiments.

Replication r of every scenario uses seed base_seed + r, and inside the model each train has
its own random stream keyed by (seed, trip_id). So scenario A and scenario B see the same
primary disturbances on the same trains, and differences between them come from the scenario,
not from luck (common random numbers).

Run all experiments and write CSVs to results/:
    python -m ets_sim.experiments
    python -m ets_sim.experiments --reps 20 --only buffer speed
"""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass, replace

import pandas as pd

from ets_sim import metrics
from ets_sim.config import load_config, project_path
from ets_sim.loader import load_processed
from ets_sim.model import SimParams, Supplement, params_from_config, simulate, total_slack_s
from ets_sim.topology import Topology
from ets_sim.train import Trip, add_synthetic_trips, apply_buffer, trips_from_frames


@dataclass
class Scenario:
    """Everything one simulation run needs besides the seed."""

    topo: Topology
    trips: list[Trip]
    params: SimParams
    threshold_s: float
    profile_min: tuple[float, ...] = ()  # extra on-time thresholds for benchmarking


@dataclass
class Replications:
    summary: pd.DataFrame      # one row per replication
    events: pd.DataFrame       # all replications, with a `rep` column
    increments: pd.DataFrame


def baseline(cfg: dict) -> Scenario:
    """Scenario built straight from config.yaml and the processed timetable."""
    tt = load_processed(cfg)
    return Scenario(
        topo=Topology(tt.stations, float(cfg["network"]["max_block_km"])),
        trips=trips_from_frames(tt.trips, tt.stop_times),
        params=params_from_config(cfg),
        threshold_s=float(cfg["metrics"]["late_threshold_min"]) * 60,
        profile_min=tuple(float(t) for t in cfg["metrics"].get("benchmark_thresholds_min", [])),
    )


def run_replications(sc: Scenario, n_reps: int, base_seed: int, keep_frames: bool = True) -> Replications:
    rows, evs, incs = [], [], []
    for r in range(n_reps):
        res = simulate(sc.topo, sc.trips, sc.params, seed=base_seed + r)
        row = metrics.summary(res.events, res.increments, sc.threshold_s, sc.profile_min)
        row["rep"] = r
        rows.append(row)
        if keep_frames:
            evs.append(res.events.assign(rep=r))
            incs.append(res.increments.assign(rep=r))
    return Replications(
        pd.DataFrame(rows),
        pd.concat(evs, ignore_index=True) if evs else pd.DataFrame(),
        pd.concat(incs, ignore_index=True) if incs else pd.DataFrame(),
    )


def _ci_row(label: dict, summary: pd.DataFrame, cols: list[str]) -> dict:
    row = dict(label)
    for c in cols:
        m, lo, hi = metrics.mean_ci(summary[c])
        row[c], row[f"{c}_lo"], row[f"{c}_hi"] = m, lo, hi
    return row


HEADLINE = ["on_time_all_pct", "on_time_dest_pct", "avg_dest_delay_min", "knock_on_min",
            "timetable_conflict_min", "recovered_min"]


# ------------------------------------------------------------------ experiments


def buffer_sweep(sc: Scenario, buffers_min: list[float], n_reps: int, seed: int) -> pd.DataFrame:
    """Experiment 1: on-time % against journey-level buffer, with the timetable cost."""
    rows = []
    base_journey = sum(t.journey_s for t in sc.trips) / len(sc.trips)
    for b in buffers_min:
        trips = [apply_buffer(t, b * 60) for t in sc.trips]
        rep = run_replications(replace(sc, trips=trips), n_reps, seed, keep_frames=False)
        journey = sum(t.journey_s for t in trips) / len(trips)
        rows.append(_ci_row({"buffer_min": b, "avg_journey_increase_min": (journey - base_journey) / 60},
                            rep.summary, HEADLINE))
    return pd.DataFrame(rows)


def bottleneck_finder(sc: Scenario, n_reps: int, seed: int) -> dict[str, pd.DataFrame]:
    """Experiment 2: rank sections/platforms and trains by the secondary delay they generate."""
    rep = run_replications(sc, n_reps, seed)
    return {
        "locations": metrics.bottlenecks(rep.increments, n_reps),
        "trains": metrics.train_impact(rep.increments, n_reps),
        "stations": metrics.station_delay(rep.events),
    }


def speed_comparison(sc: Scenario, speeds_kmh: list[float], n_reps: int, seed: int) -> pd.DataFrame:
    """Experiment 3: idealised line-speed sensitivity. Higher speed = more recoverable slack."""
    rows = []
    for v in speeds_kmh:
        slack_s, infeasible = total_slack_s(sc.trips, sc.topo, v)
        rep = run_replications(replace(sc, params=replace(sc.params, line_speed_kmh=v)), n_reps, seed,
                               keep_frames=False)
        rows.append(_ci_row({"line_speed_kmh": v, "total_slack_min": slack_s / 60,
                             "blocks_below_min_time": infeasible}, rep.summary, HEADLINE))
    return pd.DataFrame(rows)


def frequency_stress(sc: Scenario, extra_trips: list[int], offset_min: float, target_pct: float,
                     n_reps: int, seed: int) -> pd.DataFrame:
    """Experiment 4: add synthetic daily trips; flag where on-time % falls below the target."""
    rows = []
    for n in extra_trips:
        trips = add_synthetic_trips(sc.trips, n, offset_min * 60)
        rep = run_replications(replace(sc, trips=trips), n_reps, seed, keep_frames=False)
        rows.append(_ci_row({"extra_trips": n, "total_trips": len(trips)}, rep.summary, HEADLINE))
    out = pd.DataFrame(rows)
    out["below_target"] = out["on_time_all_pct"] < target_pct
    return out


def timetable_supplements(sc: Scenario) -> pd.DataFrame:
    """Scheduled running time against the idealised minimum at line speed, per stop-to-stop leg,
    grouped by section. supplement_pct = (scheduled - minimum) / minimum, the quantity that
    UIC 451-1 and ProRail prescribe (a few per cent). Large values mean the minimum is
    unrealistic (acceleration, speed limits and shared track are not modelled), not that the
    timetable is generous."""
    rows = []
    for t in sc.trips:
        for a, b in zip(t.stops, t.stops[1:]):
            path = sc.topo.path(a.station, b.station)
            km = sum(sc.topo.section_km(x, y) for x, y in zip(path, path[1:]))
            rows.append((a.station, b.station, km, b.arr_s - a.dep_s, km / sc.params.line_speed_kmh * 3600))
    d = pd.DataFrame(rows, columns=["from_station", "to_station", "km", "sched_s", "min_s"])
    g = d.groupby(["from_station", "to_station"]).agg(trips=("km", "size"), km=("km", "first"),
                                                     sched_min=("sched_s", "median"), min_min=("min_s", "first"))
    g[["sched_min", "min_min"]] /= 60
    g["supplement_pct"] = (g["sched_min"] - g["min_min"]) / g["min_min"] * 100
    g["avg_speed_kmh"] = g["km"] / (g["sched_min"] / 60)
    return g.sort_values("supplement_pct").reset_index()


def recovery_benchmark(sc: Scenario, benchmarks: dict[str, list[float]], n_reps: int, seed: int) -> pd.DataFrame:
    """Experiment 5: how much do results depend on the recovery model?

    'line speed' is the v1 model. Each benchmark is [pct, minutes per 100 km]: the late train
    may win back only that running time supplement, as UIC 451-1 or ProRail would plan it.
    Reported with on-time % at the benchmark thresholds (SBB/NS 3 min and so on).
    """
    cases = [("line speed (v1)", None)] + [(name, Supplement(float(v[0]), float(v[1])))
                                           for name, v in benchmarks.items()]
    rows = []
    for name, sup in cases:
        params = replace(sc.params, running_supplement_pct=sup.pct if sup else None,
                         supplement_min_per_100km=sup.per_100km_min if sup else 0.0)
        slack_s, infeasible = total_slack_s(sc.trips, sc.topo, params.line_speed_kmh, params.supplement)
        rep = run_replications(replace(sc, params=params), n_reps, seed, keep_frames=False)
        cols = HEADLINE + [c for c in rep.summary.columns if c.startswith("on_time_") and c.endswith("min_pct")]
        rows.append(_ci_row({"recovery_model": name, "total_slack_min": slack_s / 60,
                             "blocks_below_min_time": infeasible}, rep.summary, cols))
    return pd.DataFrame(rows)


def block_length_sensitivity(sc: Scenario, stations: pd.DataFrame, block_km: list[float], n_reps: int,
                             seed: int) -> pd.DataFrame:
    """Extra check: how much do results depend on the assumed fixed-block length?"""
    rows = []
    for km in block_km:
        rep = run_replications(replace(sc, topo=Topology(stations, km)), n_reps, seed, keep_frames=False)
        rows.append(_ci_row({"max_block_km": km}, rep.summary, HEADLINE))
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ CLI


ALL = ("baseline", "buffer", "bottleneck", "speed", "frequency", "blocks", "benchmark")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config")
    parser.add_argument("--reps", type=int, help="replications per scenario (default from config)")
    parser.add_argument("--only", nargs="*", choices=ALL, default=list(ALL))
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    ex = cfg["experiments"]
    n, seed = args.reps or int(ex["replications"]), int(ex["base_seed"])
    sc = baseline(cfg)
    out = project_path(cfg["data"]["results_dir"])
    out.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.width", 160)

    def done(name: str, df: pd.DataFrame, t0: float) -> None:
        df.to_csv(out / f"{name}.csv", index=False)
        print(f"\n== {name} ({time.time() - t0:.0f} s, {n} reps) ==")
        print(df.round(2).head(15).to_string(index=False))

    if "baseline" in args.only:
        t0 = time.time()
        no_dis = run_replications(replace(sc, params=sc.params.no_disruption()), 1, seed)
        rep = run_replications(sc, n, seed, keep_frames=False)
        df = pd.DataFrame([_ci_row({"scenario": "no primary delays"}, no_dis.summary, HEADLINE),
                           _ci_row({"scenario": "baseline"}, rep.summary, HEADLINE)])
        done("baseline", df, t0)
    if "buffer" in args.only:
        t0 = time.time()
        done("buffer_sweep", buffer_sweep(sc, ex["buffer_minutes"], n, seed), t0)
    if "bottleneck" in args.only:
        t0 = time.time()
        res = bottleneck_finder(sc, n, seed)
        for k, df in res.items():
            done(f"bottleneck_{k}", df, t0)
    if "speed" in args.only:
        t0 = time.time()
        done("speed_comparison", speed_comparison(sc, ex["line_speeds_kmh"], n, seed), t0)
    if "frequency" in args.only:
        t0 = time.time()
        done("frequency_stress", frequency_stress(sc, ex["frequency_extra_trips"], float(ex["frequency_offset_min"]),
                                                   float(ex["on_time_target_pct"]), n, seed), t0)
    if "blocks" in args.only:
        t0 = time.time()
        tt = load_processed(cfg)
        done("block_length", block_length_sensitivity(sc, tt.stations, ex["block_km_values"], n, seed), t0)
    if "benchmark" in args.only:
        t0 = time.time()
        done("timetable_supplements", timetable_supplements(sc), t0)
        done("recovery_benchmark", recovery_benchmark(sc, ex["recovery_benchmarks"], n, seed), t0)
    print(f"\nResults written to {out}")


if __name__ == "__main__":
    main()
