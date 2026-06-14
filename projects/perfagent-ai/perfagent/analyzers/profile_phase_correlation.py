from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


def analyze_profile_phase_correlation(
    profiling_artifacts: dict[str, Any],
    aligned_timeseries: list[dict[str, Any]],
    *,
    features: dict[str, Any],
    bucket_seconds: int = 10,
) -> dict[str, Any]:
    phase_windows = _phase_windows(aligned_timeseries, bucket_seconds=bucket_seconds)
    breach_window = _breach_window(features, aligned_timeseries, bucket_seconds=bucket_seconds)
    capture_windows = _capture_windows(profiling_artifacts, phase_windows, breach_window)
    artifacts = _profile_artifacts(profiling_artifacts)
    warnings: list[str] = []
    if profiling_artifacts.get("enabled") and not capture_windows:
        warnings.append("capture window metadata missing; profile artifacts cannot be aligned to test phases")

    artifact_correlations = []
    for artifact in artifacts:
        window = capture_windows[0] if capture_windows else None
        artifact_correlations.append(
            {
                "artifact_path": artifact.get("artifact_path") or artifact.get("source_path"),
                "type": artifact.get("type", "unknown"),
                "capture_window": window.get("capture_window") if window else None,
                "overlapped_phases": window.get("overlapped_phases", []) if window else [],
                "breach_overlap": bool(window.get("breach_overlap")) if window else False,
                "overlap_confidence": window.get("overlap_confidence", "low") if window else "low",
                "top_functions": artifact.get("summary", {}).get("top_functions", [])[:10],
            }
        )

    return {
        "enabled": bool(profiling_artifacts.get("enabled") or artifacts),
        "phase_windows": phase_windows,
        "breach_window": breach_window,
        "capture_windows": capture_windows,
        "artifact_correlations": artifact_correlations,
        "warnings": warnings,
    }


def _phase_windows(rows: list[dict[str, Any]], *, bucket_seconds: int) -> list[dict[str, Any]]:
    ordered = [_row_with_time(row) for row in rows]
    ordered = [row for row in ordered if row["_timestamp"] is not None]
    ordered.sort(key=lambda row: row["_timestamp"])
    windows_by_phase: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(ordered):
        start = row["_timestamp"]
        next_start = ordered[index + 1]["_timestamp"] if index + 1 < len(ordered) else None
        end = next_start or start + timedelta(seconds=bucket_seconds)
        phase = str(row.get("phase") or "unknown")
        current = windows_by_phase.get(phase)
        if not current:
            windows_by_phase[phase] = {"phase": phase, "started_at": start, "ended_at": end}
        else:
            current["started_at"] = min(current["started_at"], start)
            current["ended_at"] = max(current["ended_at"], end)
    return [
        {
            "phase": window["phase"],
            "started_at": _iso(window["started_at"]),
            "ended_at": _iso(window["ended_at"]),
            "duration_seconds": round((window["ended_at"] - window["started_at"]).total_seconds(), 4),
        }
        for window in sorted(windows_by_phase.values(), key=lambda item: item["started_at"])
    ]


def _breach_window(features: dict[str, Any], rows: list[dict[str, Any]], *, bucket_seconds: int) -> dict[str, Any] | None:
    timestamp = _parse_time(features.get("first_slo_breach_timestamp"))
    if timestamp is None:
        return None
    phase = features.get("first_slo_breach_phase")
    ordered_times = sorted(_parse_time(row.get("timestamp")) for row in rows if _parse_time(row.get("timestamp")) is not None)
    next_time = next((item for item in ordered_times if item > timestamp), None)
    end = next_time or timestamp + timedelta(seconds=bucket_seconds)
    return {
        "timestamp": _iso(timestamp),
        "phase": phase,
        "started_at": _iso(timestamp),
        "ended_at": _iso(end),
        "duration_seconds": round((end - timestamp).total_seconds(), 4),
    }


def _capture_windows(
    profiling_artifacts: dict[str, Any],
    phase_windows: list[dict[str, Any]],
    breach_window: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    auto_capture = profiling_artifacts.get("auto_capture") or {}
    windows = []
    raw_windows = []
    if auto_capture.get("capture_window"):
        raw_windows.append(auto_capture["capture_window"])
    for item in auto_capture.get("completed", []):
        raw_windows.append(
            {
                "started_at": item.get("started_at"),
                "ended_at": item.get("ended_at"),
                "duration_seconds": item.get("duration_seconds"),
                "command": item.get("command"),
                "pid": item.get("pid"),
            }
        )
    target = auto_capture.get("profile_target") or auto_capture.get("plan", {}).get("profile_target") or {}
    seen = set()
    for raw_window in raw_windows:
        start = _parse_time(raw_window.get("started_at"))
        end = _parse_time(raw_window.get("ended_at"))
        if start is None or end is None:
            continue
        key = (_iso(start), _iso(end), raw_window.get("command"))
        if key in seen:
            continue
        seen.add(key)
        overlapped = _overlapped_phases(start, end, phase_windows)
        windows.append(
            {
                "capture_window": {
                    "started_at": _iso(start),
                    "ended_at": _iso(end),
                    "duration_seconds": raw_window.get("duration_seconds")
                    if raw_window.get("duration_seconds") is not None
                    else round((end - start).total_seconds(), 4),
                },
                "profile_command": raw_window.get("command"),
                "target_pid": target.get("pid"),
                "target_container": target.get("container"),
                "overlapped_phases": overlapped,
                "breach_overlap": _overlaps_window(start, end, breach_window),
                "overlap_confidence": "high" if overlapped else "low",
            }
        )
    return windows


def _profile_artifacts(profiling_artifacts: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        *profiling_artifacts.get("profiles", []),
        *profiling_artifacts.get("auto_capture", {}).get("artifacts", []),
    ]


def _overlapped_phases(start: datetime, end: datetime, phase_windows: list[dict[str, Any]]) -> list[str]:
    phases = []
    for window in phase_windows:
        phase_start = _parse_time(window.get("started_at"))
        phase_end = _parse_time(window.get("ended_at"))
        if phase_start is None or phase_end is None:
            continue
        if start < phase_end and end > phase_start:
            phases.append(str(window.get("phase")))
    return phases


def _overlaps_window(start: datetime, end: datetime, window: dict[str, Any] | None) -> bool:
    if not window:
        return False
    window_start = _parse_time(window.get("started_at"))
    window_end = _parse_time(window.get("ended_at"))
    if window_start is None or window_end is None:
        return False
    return start < window_end and end > window_start


def _row_with_time(row: dict[str, Any]) -> dict[str, Any]:
    return row | {"_timestamp": _parse_time(row.get("timestamp"))}


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")
