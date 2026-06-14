from pathlib import Path

import sys

from perfagent.collectors.profiling_collector import (
    build_profile_capture_plan,
    collect_profiling_artifacts,
    execute_profile_capture_plan,
    summarize_profile_artifact,
)


def test_collect_profiling_artifacts_copies_existing_profiles(tmp_path):
    source = tmp_path / "cpu.pprof"
    source.write_text("profile-data")
    output_dir = tmp_path / "run" / "raw" / "profiles"

    result = collect_profiling_artifacts([source], output_dir)

    assert result["enabled"] is True
    assert result["artifacts"] == [str(output_dir / "cpu.pprof")]
    assert (output_dir / "cpu.pprof").read_text() == "profile-data"
    assert result["warnings"] == []
    assert result["profiles"][0]["source_path"] == str(source)
    assert result["profiles"][0]["type"] == "pprof"
    assert result["profiles"][0]["summary"]["available"] is True


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

    assert result["profiles"][0]["source_path"] == str(source)
    assert result["profiles"][0]["artifact_path"] == str(output_dir / "cpu.svg")
    assert result["profiles"][0]["type"] == "flamegraph"
    assert result["profiles"][0]["render_status"] == "provided"
    assert result["profiles"][0]["summary"]["type"] == "flamegraph"


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
    assert plan["execute_supported"] is True


def test_build_profile_capture_plan_prefers_ebpf_mode(tmp_path):
    plan = build_profile_capture_plan(runtime="go", output_dir=tmp_path, mode="ebpf", pid="123")

    assert plan["mode"] == "ebpf"
    assert plan["commands"][0]["binary"] == "perf"
    assert "123" in plan["commands"][0]["argv"]


def test_summarize_collapsed_stack_profile_extracts_top_functions(tmp_path):
    profile = tmp_path / "profile.collapsed"
    profile.write_text("main;handler;dbQuery 7\nmain;handler;render 3\n")

    summary = summarize_profile_artifact(profile, "collapsed-stacks")

    assert summary["top_functions"][0]["name"] == "dbQuery"
    assert summary["top_functions"][0]["percent"] == 70


def test_execute_profile_capture_plan_runs_available_commands(tmp_path):
    plan = {
        "runtime": "python",
        "duration_seconds": 1,
        "output_dir": str(tmp_path / "captured"),
        "warnings": [],
        "commands": [
            {
                "binary": sys.executable,
                "available": True,
                "argv": [sys.executable, "-c", "print('captured')"],
                "command": "capture",
                "description": "test capture",
                "phase": "capture",
            },
            {
                "binary": sys.executable,
                "available": True,
                "argv": [sys.executable, "-c", "print('rendered')"],
                "command": "render",
                "description": "test render",
                "phase": "render",
            },
        ],
    }

    result = execute_profile_capture_plan(plan, log_dir=tmp_path / "logs", timeout_seconds=5)

    assert result["started_count"] == 1
    assert result["completed"][0]["exit_code"] == 0
    assert result["rendered"][0]["exit_code"] == 0
