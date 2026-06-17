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
    assert "unique_slack_messages(" in APP
    assert "st.text_input" in APP and "Search messages" in APP
    assert 'key=f"slack_search_{channel_key}"' in APP
    assert "height=" in APP                  # scrollable fixed-height container


def test_incident_section_wired():
    assert "def render_incident_response_simulation(" in APP
    assert "render_incident_response_simulation()" in APP   # called in main script
    assert "Incident Response Simulation" in APP            # expander title
    assert "stream_incident(" in APP                        # timed playback driver
    assert "load_scenarios(" in APP                         # scenario picker
    assert "time.sleep(" in APP                             # timed streaming pacing


def test_incident_ui_has_failure_injection_controls():
    assert "Enable Kubernetes failure simulation" in APP
    assert "Failure mode" in APP
    assert "oom_kill" in APP
    assert "pod_restart" in APP
    assert "disk_iops" in APP
    assert "cpu_throttle" in APP


def test_incident_ui_surfaces_logs_and_observability():
    assert "Static production logs" in APP
    assert "Observability evidence" in APP
    assert "OpenSearch" in APP
    assert "Grafana Cloud" in APP


def test_incident_ui_surfaces_firehydrant_style_automation():
    assert "Runbook automation" in APP
    assert "Incident channel" in APP
    assert "Tracking ticket" in APP
    assert "Status update draft" in APP


def test_incident_ui_surfaces_jira_metrics_and_hitl_status_update():
    assert "Jira incident metrics" in APP
    assert "Human approval required" in APP
    assert "Publish to Slack and status page" in APP
    assert "Approve publish" in APP
    assert "Reject publish" in APP
    assert "status_publish_decision" in APP


def test_incident_ui_has_agent_flowchart():
    assert "def render_agent_flowchart(" in APP
    assert "def agent_name_for_message(" in APP
    assert "Agent operations flow" in APP
    assert "workflow-shell" in APP
    assert "workflow-node" in APP
    assert "workflow-edge" in APP
    assert "marker id=\"arrow\"" in APP
    assert "workflow_events = final_messages or unique_messages" in APP
    assert "nodes_per_row = 6" in APP
    assert "row = index // nodes_per_row" in APP
    assert "overflow:auto" in APP
    assert "agent-flow-compact" in APP
    assert "service_label" in APP
    assert "Current backend action" in APP
    assert "active_action" in APP
    assert "agent-state-working" in APP
    assert "Observability Agent" in APP
    assert "Incident Commander Agent" in APP
    assert "FireHydrant Automation" in APP
    assert "Scribe Agent" in APP


def test_incident_ui_exposes_backend_agent_trace_and_json_download():
    assert "def render_backend_agent_trace(" in APP
    assert "Backend agent trace" in APP
    assert "Rendered from LangGraph incident state" in APP
    assert "Download agent run JSON" in APP
    assert "final[\"timeline\"]" in APP
    assert "json.dumps(final" in APP
    assert "_backend_provenance" in APP
    assert "Run ID" in APP
    assert "Thread ID" in APP
    assert "backend compute seconds" in APP
    assert "produced_findings" in APP
    assert "observability_events" in APP
    assert "on_final=lambda final" in APP
    assert "ui-summary" not in APP


def test_incident_ui_has_concept_demo_delay():
    assert "Concept demo pacing" in APP
    assert "demo_delay_seconds = 10" in APP
    assert "value=True" in APP
    assert "for message in messages:" in APP


def test_operator_mode_infers_service_for_automation():
    assert "def infer_incident_service(" in APP
    assert "inferred_service = service or infer_incident_service" in APP
    assert 'return "playback-service"' in APP
