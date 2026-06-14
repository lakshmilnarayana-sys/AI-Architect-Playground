from pathlib import Path


def test_makefile_exposes_report_suite_targets():
    content = Path("Makefile").read_text()

    assert "report-suite:" in content
    assert "evaluate-grpc-artifacts:" in content
    assert "evaluate-websocket-artifacts:" in content
    assert "evaluate-ui-artifacts:" in content
    assert "--engine grpc" in content
    assert "--engine websocket" in content
    assert "--engine ui" in content
    assert "--no-store" in content
