from pathlib import Path

APP = Path("app/streamlit_app.py").read_text()


def test_slack_logo_asset_exists_and_is_svg():
    svg = Path("app/assets/slack-logo.svg")
    assert svg.exists()
    assert "<svg" in svg.read_text()[:300]


def test_render_slack_channel_defined():
    assert "def render_slack_channel(" in APP


def test_slack_channel_has_search_and_scroll():
    assert "filter_messages(" in APP        # search wired in
    assert "st.text_input" in APP and "Search messages" in APP
    assert "height=" in APP                  # scrollable fixed-height container


def test_incident_section_wired():
    assert "def render_incident_response_simulation(" in APP
    assert "render_incident_response_simulation()" in APP   # called in main script
    assert "Incident Response Simulation" in APP            # expander title
    assert "stream_incident(" in APP                        # timed playback driver
    assert "load_scenarios(" in APP                         # scenario picker
    assert "time.sleep(" in APP                             # timed streaming pacing
