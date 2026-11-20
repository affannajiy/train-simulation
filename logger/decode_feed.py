"""Decode a GTFS-Realtime vehicle-position protobuf into flat rows.

Every field is kept as delivered. `trip_id` is NOT trusted: on 2026-11-20 it disagreed
with the scheduled position for 6 of 7 ETS vehicles (see docs/decisions.md, item 8).
"""

from __future__ import annotations

import datetime as dt

from google.transit import gtfs_realtime_pb2

COLUMNS = [
    "observed_at_utc",     # when this logger received the feed
    "feed_timestamp_utc",  # header timestamp from the feed
    "vehicle_timestamp_utc",  # timestamp reported for this vehicle
    "entity_id",
    "trip_id",
    "route_id",
    "vehicle_id",
    "vehicle_label",       # trainset, for example ETS303
    "lat",
    "lon",
    "bearing",
    "speed",
    "current_status",
    "stop_id",
    "current_stop_sequence",
    "bad_position",
]

_STATUS = {0: "INCOMING_AT", 1: "STOPPED_AT", 2: "IN_TRANSIT_TO"}


def _iso(ts: int) -> str:
    if not ts:
        return ""
    return dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc).isoformat()


def is_bad_position(lat: float, lon: float, bbox: dict) -> bool:
    """True for (0, 0) defaults and anything outside the configured bounding box."""
    if abs(lat) < 0.1 and abs(lon) < 0.1:
        return True
    return not (bbox["lat_min"] <= lat <= bbox["lat_max"] and bbox["lon_min"] <= lon <= bbox["lon_max"])


def decode(payload: bytes, observed_at: dt.datetime, bbox: dict) -> list[dict]:
    """Parse one feed payload. Raises on a payload that is not a valid FeedMessage."""
    msg = gtfs_realtime_pb2.FeedMessage()
    msg.ParseFromString(payload)
    header_ts = _iso(msg.header.timestamp)
    rows = []
    for ent in msg.entity:
        if not ent.HasField("vehicle"):
            continue
        v = ent.vehicle
        lat, lon = v.position.latitude, v.position.longitude
        rows.append({
            "observed_at_utc": observed_at.isoformat(),
            "feed_timestamp_utc": header_ts,
            "vehicle_timestamp_utc": _iso(v.timestamp),
            "entity_id": ent.id,
            "trip_id": v.trip.trip_id,
            "route_id": v.trip.route_id,
            "vehicle_id": v.vehicle.id,
            "vehicle_label": v.vehicle.label,
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "bearing": round(v.position.bearing, 1) if v.position.HasField("bearing") else "",
            "speed": round(v.position.speed, 2) if v.position.HasField("speed") else "",
            "current_status": _STATUS.get(v.current_status, str(v.current_status)) if v.HasField("current_status") else "",
            "stop_id": v.stop_id,
            "current_stop_sequence": v.current_stop_sequence if v.HasField("current_stop_sequence") else "",
            "bad_position": is_bad_position(lat, lon, bbox),
        })
    return rows
