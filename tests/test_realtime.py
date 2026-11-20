"""Deploy helpers: remote realtime URL building and the snapshot fallback loader."""

from __future__ import annotations

import copy
import datetime as dt

import pytest

from ets_sim import realtime
from ets_sim.config import load_config
from ets_sim.loader import load_or_build


@pytest.fixture
def cfg():
    return copy.deepcopy(load_config())


@pytest.mark.parametrize("repo", ["", "OWNER/train-simulation", "bad repo/x", "a/b/c", "../x"])
def test_remote_base_off_for_placeholder_or_invalid(cfg, repo):
    cfg["data"]["realtime_repo"] = repo
    assert realtime.remote_base(cfg) is None
    assert realtime.remote_days(cfg) == {}


def test_remote_base_url(cfg):
    cfg["data"]["realtime_repo"] = "someone/train-simulation"
    assert realtime.remote_base(cfg) == (
        "https://raw.githubusercontent.com/someone/train-simulation/realtime-data/data/realtime")


def test_remote_days_probes_last_n_dates_oldest_first(cfg, monkeypatch):
    cfg["data"]["realtime_repo"] = "someone/train-simulation"
    cfg["data"]["realtime_remote_days"] = 3
    present = {"2026-11-19", "2026-11-20"}
    asked = []

    class Resp:
        def __init__(self, code):
            self.status_code = code

    def fake_head(self, url, **kw):
        day = url.rsplit("/", 1)[1][:-4]
        asked.append(day)
        return Resp(200 if day in present else 404)

    monkeypatch.setattr(realtime.requests.Session, "head", fake_head)
    days = realtime.remote_days(cfg, today=dt.date(2026, 11, 20))
    assert asked == ["2026-11-18", "2026-11-19", "2026-11-20"]
    assert list(days) == ["2026-11-19", "2026-11-20"]


def test_load_or_build_from_snapshot(cfg, tmp_path):
    cfg["data"]["processed_dir"] = str(tmp_path / "processed")
    tt = load_or_build(cfg)
    assert len(tt.trips) > 0 and len(tt.stop_times) > 0
    assert (tmp_path / "processed" / "trips.csv").exists()
    # Second call reads the CSVs it just wrote and gives the same timetable.
    again = load_or_build(cfg)
    assert len(again.trips) == len(tt.trips)


def test_read_day_keeps_ids_as_text_and_flag_as_bool(tmp_path):
    path = tmp_path / "2026-11-20.csv"
    path.write_text("observed_at_utc,trip_id,vehicle_label,lat,lon,bad_position\n"
                    "2026-11-20T10:00:00+00:00,9510,303,3.1,101.6,False\n"
                    "2026-11-20T10:00:00+00:00,,,0.0,0.0,True\n", encoding="utf-8")
    df = realtime.read_day(path)
    assert df["vehicle_label"].iloc[0] == "303"
    assert df["trip_id"].iloc[0] == "9510"
    assert df["bad_position"].dtype == bool
    assert list(df["bad_position"]) == [False, True]
    # The app joins these columns as text; numeric labels used to raise TypeError here.
    assert list(df["vehicle_label"].fillna("?") + " (" + df["trip_id"].fillna("?") + ")") == [
        "303 (9510)", "? (?)"]
