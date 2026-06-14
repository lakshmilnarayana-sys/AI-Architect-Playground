from perfagent.generators.ui_generator import generate_ui_journey_test


def test_generate_ui_journey_test_uses_configured_selectors(tmp_path):
    output = tmp_path / "ui_journey.py"

    generate_ui_journey_test(
        service_name="checkout-ui",
        target_url="http://localhost:8083",
        output_path=output,
        config={"path": "/checkout", "action_selector": "#pay", "wait_selector": "#checkout"},
    )

    content = output.read_text()
    assert "sync_playwright" in content
    assert "PATH = '/checkout'" in content
    assert "ACTION_SELECTOR = '#pay'" in content
    assert "json.dumps(run(" in content
