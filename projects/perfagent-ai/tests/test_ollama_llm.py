import json

from typer.testing import CliRunner

from perfagent.cli import app
from perfagent.config import load_run_config, resolve_evaluate_options
from perfagent.llm.client import explain_with_ollama


runner = CliRunner()


def test_config_loads_ollama_settings(tmp_path):
    config = tmp_path / "perfagent.yaml"
    config.write_text(
        """
service_name: payments-api
llm:
  enabled: true
  provider: ollama
  model: llama3.2
  base_url: http://localhost:11434
""".lstrip()
    )

    resolved = resolve_evaluate_options(load_run_config(config), {})

    assert resolved["llm"]["enabled"] is True
    assert resolved["llm"]["provider"] == "ollama"
    assert resolved["llm"]["model"] == "llama3.2"


def test_explain_with_ollama_parses_json_response(monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(
                {
                    "response": json.dumps(
                        {
                            "summary": "Baseline passed and stress failed.",
                            "bottleneck": "database_connection_pool_saturation",
                            "confidence": "medium",
                            "evidence": ["postgres pool reached 99%"],
                            "recommendations": ["Increase pool size"],
                            "missing_metrics": [],
                        }
                    )
                }
            ).encode()

    calls = []

    def fake_urlopen(req, timeout):
        calls.append(json.loads(req.data.decode()))
        return Response()

    monkeypatch.setattr("perfagent.llm.client.request.urlopen", fake_urlopen)

    result = explain_with_ollama(
        {"features": {"release_decision": "WARN"}},
        model="llama3.2",
        base_url="http://localhost:11434",
    )

    assert calls[0]["model"] == "llama3.2"
    assert calls[0]["stream"] is False
    assert result["enabled"] is True
    assert result["provider"] == "ollama"
    assert result["summary"] == "Baseline passed and stress failed."


def test_evaluate_with_ollama_writes_ai_analysis(tmp_path, monkeypatch):
    def fake_explain(evidence, *, model, base_url, timeout_seconds=30):
        return {
            "enabled": True,
            "provider": "ollama",
            "model": model,
            "summary": "AI narrative from structured evidence.",
            "bottleneck": "none_detected",
            "confidence": "medium",
            "evidence": ["deterministic evidence only"],
            "recommendations": ["keep testing"],
            "missing_metrics": [],
        }

    monkeypatch.setattr("perfagent.workflow.explain_with_ollama", fake_explain)
    output = tmp_path / "run"
    result = runner.invoke(
        app,
        [
            "evaluate",
            "--service-name",
            "payments-api",
            "--openapi",
            "examples/sample-openapi.yaml",
            "--target-url",
            "http://localhost:8080",
            "--runtime",
            "go",
            "--slo-p95-ms",
            "500",
            "--slo-error-rate",
            "1",
            "--output",
            str(output),
            "--skip-run",
            "--llm-provider",
            "ollama",
            "--llm-model",
            "llama3.2",
        ],
    )

    assert result.exit_code == 0, result.output
    assert (output / "processed" / "ai_analysis.json").exists()
    html = (output / "reports" / "report.html").read_text()
    assert "AI Analysis" in html
    assert "AI narrative from structured evidence." in html
