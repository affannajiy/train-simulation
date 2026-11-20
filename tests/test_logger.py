"""Realtime decoder tests with a hand-built FeedMessage (no network)."""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

from google.transit import gtfs_realtime_pb2

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "logger"))
from decode_feed import decode  # noqa: E402

BBOX = {"lat_min": 0.5, "lat_max": 7.5, "lon_min": 99.0, "lon_max": 105.0}


def _feed() -> bytes:
    msg = gtfs_realtime_pb2.FeedMessage()
    msg.header.gtfs_realtime_version = "2.0"
    msg.header.timestamp = 1_795_000_000
    for i, (lat, lon) in enumerate([(2.58, 102.58), (0.0, 0.0)]):
        e = msg.entity.add()
        e.id = str(i)
        e.vehicle.trip.trip_id = f"95{i}"
        e.vehicle.vehicle.label = f"ETS30{i}"
        e.vehicle.position.latitude = lat
        e.vehicle.position.longitude = lon
    return msg.SerializeToString()


def test_decode_keeps_fields_and_flags_bad_positions():
    rows = decode(_feed(), dt.datetime(2026, 11, 20, tzinfo=dt.timezone.utc), BBOX)
    assert [r["vehicle_label"] for r in rows] == ["ETS300", "ETS301"]
    assert [r["bad_position"] for r in rows] == [False, True]
    assert rows[0]["trip_id"] == "950"
    assert rows[0]["current_status"] == ""  # not set in feed, so not invented
