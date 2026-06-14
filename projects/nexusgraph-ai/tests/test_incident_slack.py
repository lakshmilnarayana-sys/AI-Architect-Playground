from src.incident.slack import (
    slugify, channel_name, event_to_slack_message, filter_messages, ROLE_AVATARS,
)


def test_slugify_and_channel_name():
    assert slugify("Playback Latency SEV1") == "playback-latency-sev1"
    assert channel_name({"title": "Playback Latency SEV1"}) == "#inc-playback-latency-sev1"


def test_event_to_slack_message_maps_fields_and_avatar():
    event = {"ts": "10:02:00", "phase": "declare", "actor": "Incident Bot",
             "role": "bot", "kind": "message", "text": "SEV1 declared"}
    msg = event_to_slack_message(event)
    assert msg["author"] == "Incident Bot"
    assert msg["phase"] == "declare"
    assert msg["avatar"] == ROLE_AVATARS["bot"]
    assert msg["text"] == "SEV1 declared"


def test_filter_messages_matches_text_author_and_phase():
    messages = [
        {"ts": "1", "author": "TriageAgent", "role": "triage", "phase": "triage",
         "text": "owner is Playback Platform", "avatar": "x"},
        {"ts": "2", "author": "Incident Bot", "role": "bot", "phase": "declare",
         "text": "SEV1 declared", "avatar": "y"},
    ]
    assert len(filter_messages(messages, "")) == 2          # empty = all
    assert len(filter_messages(messages, "playback")) == 1  # text
    assert len(filter_messages(messages, "bot")) == 1       # author
    assert len(filter_messages(messages, "triage")) == 1    # phase
    assert filter_messages(messages, "PLAYBACK")[0]["author"] == "TriageAgent"  # case-insensitive
