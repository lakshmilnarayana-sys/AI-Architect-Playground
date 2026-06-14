from pathlib import Path

from perfagent.collectors.profiling_collector import build_profile_capture_plan, collect_profiling_artifacts


def test_collect_profiling_artifacts_copies_existing_profiles(tmp_path):
    source = tmp_path / "cpu.pprof"
    source.write_text("profile-data")
    output_dir = tmp_path / "run" / "raw" / "profiles"

    result = collect_profiling_artifacts([source], output_dir)

    assert result["enabled"] is True
    assert result["artifacts"] == [str(output_dir / "cpu.pprof")]
    assert (output_dir / "cpu.pprof").read_text() == "profile-data"
    assert result["warnings"] == []
    assert result["profiles"] == [
        {
            "source_path": str(source),
            "artifact_path": str(output_dir / "cpu.pprof"),
            "type": "pprof",
            "render_status": "not_rendered",
            "warnings": ["Rendering is not implemented for pprof profiles yet."],
        }
    ]


def test_collect_profiling_artifacts_warns_for_missing_profiles(tmp_path):
    missing = tmp_path / "missing.jfr"
    output_dir = tmp_path / "run" / "raw" / "profiles"

    result = collect_profiling_artifacts([missing], output_dir)

    assert result["enabled"] is True
    assert result["artifacts"] == []
    assert result["warnings"] == [f"Profiling artifact not found: {missing}"]
    assert result["profiles"] == [
        {
            "source_path": str(missing),
            "artifact_path": None,
            "type": "jfr",
            "render_status": "missing",
            "warnings": [f"Profiling artifact not found: {missing}"],
        }
    ]


def test_collect_profiling_artifacts_classifies_supported_profile_names(tmp_path):
    sources = [
        tmp_path / "cpu.pprof",
        tmp_path / "recording.jfr",
        tmp_path / "py-spy.speedscope.json",
        tmp_path / "clinic-flame.html",
        tmp_path / "stacks.collapsed",
        tmp_path / "isolate.cpuprofile",
    ]
    for source in sources:
        source.write_text(source.name)
    output_dir = tmp_path / "run" / "raw" / "profiles"

    result = collect_profiling_artifacts(sources, output_dir)

    assert [profile["type"] for profile in result["profiles"]] == [
        "pprof",
        "jfr",
        "speedscope",
        "clinic",
        "collapsed-stacks",
        "v8-cpuprofile",
    ]
    assert result["artifacts"] == [str(output_dir / source.name) for source in sources]


def test_collect_profiling_artifacts_marks_svg_flamegraphs_visible(tmp_path):
    source = tmp_path / "cpu.svg"
    source.write_text("<svg></svg>")
    output_dir = tmp_path / "run" / "raw" / "profiles"

    result = collect_profiling_artifacts([source], output_dir)

    assert result["profiles"] == [
        {
            "source_path": str(source),
            "artifact_path": str(output_dir / "cpu.svg"),
            "type": "flamegraph",
            "render_status": "provided",
            "warnings": [],
        }
    ]


def test_build_profile_capture_plan_for_go_pprof(tmp_path):
    plan = build_profile_capture_plan(
        runtime="go",
        output_dir=tmp_path,
        duration_seconds=30,
        profile_endpoint="http://svc:6060/debug/pprof",
    )

    assert plan["runtime"] == "go"
    assert plan["commands"][0]["binary"] == "go"
    assert "profile?seconds=30" in plan["commands"][0]["command"]
    assert plan["execute_supported"] is False
