from pathlib import Path

from perfagent.collectors.profiling_collector import collect_profiling_artifacts


def test_collect_profiling_artifacts_copies_existing_profiles(tmp_path):
    source = tmp_path / "cpu.pprof"
    source.write_text("profile-data")
    output_dir = tmp_path / "run" / "raw" / "profiles"

    result = collect_profiling_artifacts([source], output_dir)

    assert result["enabled"] is True
    assert result["artifacts"] == [str(output_dir / "cpu.pprof")]
    assert (output_dir / "cpu.pprof").read_text() == "profile-data"
    assert result["warnings"] == []


def test_collect_profiling_artifacts_warns_for_missing_profiles(tmp_path):
    missing = tmp_path / "missing.jfr"
    output_dir = tmp_path / "run" / "raw" / "profiles"

    result = collect_profiling_artifacts([missing], output_dir)

    assert result["enabled"] is True
    assert result["artifacts"] == []
    assert result["warnings"] == [f"Profiling artifact not found: {missing}"]
