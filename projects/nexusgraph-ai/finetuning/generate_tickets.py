#!/usr/bin/env python
"""Generate finetuning/streamflix_tickets.csv — synthetic StreamFlix support tickets
for the Gen Academy Week 5 custom project (LoRA ticket router).

Ground truth comes from the knowledge graph (single source of truth):
  service --OWNED_BY_EXTERNAL_TEAM--> team   (graph/edges.csv)
Each ticket concerns exactly one service; its label is the short human queue name
of the owning team. Ticket phrasing is synthesized from real seed data in
data/incident_scenarios.yaml, data/service_logs.yaml, and the failure modes in
data/kubernetes_resources.yaml, varied across channel style, verbosity, and tone.

Deterministic: random.Random(42). Output schema mirrors the stock Week 5
support_tickets.csv: header `category_truth,text` (label first).

Hard guarantees enforced by assertions before writing:
  * no ticket text contains its own label (or any of the 7 labels), case-insensitive
  * no duplicate ticket texts
  * exact label balance (ROWS_PER_LABEL per queue)
"""

from __future__ import annotations

import csv
import random
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EDGES_CSV = REPO_ROOT / "graph" / "edges.csv"
OUT_CSV = Path(__file__).resolve().parent / "streamflix_tickets.csv"

SEED = 42
ROWS_PER_LABEL = 120  # 7 labels * 120 = 840 rows

# ---------------------------------------------------------------------------
# 1. Ground truth: service -> owning team, from the knowledge graph
# ---------------------------------------------------------------------------

def team_slug_to_queue(team_id: str) -> str:
    """team:identity-platform-team -> 'Identity Platform'."""
    slug = team_id.split(":", 1)[1]
    if slug.endswith("-team"):
        slug = slug[: -len("-team")]
    return " ".join(w.capitalize() for w in slug.split("-"))


def load_service_owning_team() -> dict[str, str]:
    """Parse graph/edges.csv for OWNED_BY_EXTERNAL_TEAM edges."""
    mapping: dict[str, str] = {}
    with EDGES_CSV.open() as fh:
        for row in csv.DictReader(fh):
            if row["relationship"] == "OWNED_BY_EXTERNAL_TEAM":
                service = row["source"].split(":", 1)[1]
                mapping[service] = team_slug_to_queue(row["target"])
    return mapping


# Human-readable service names used inside ticket text (graph id -> display name,
# matching graph/nodes.csv display names).
SERVICE_DISPLAY = {
    "playback": "playback-service",
    "manifest": "manifest-service",
    "cdn-routing": "cdn-routing-service",
    "recommendation": "recommendation-service",
    "billing": "billing-service",
    "observability": "observability-service",
    "feature-store": "feature-store-service",
}

# ---------------------------------------------------------------------------
# 2. Symptom seed banks per service.
#    "ops"  = technical phrasing seeded from incident_scenarios.yaml signals,
#             service_logs.yaml messages, and kubernetes_resources.yaml
#             failure-mode symptoms/triggers.
#    "user" = the same faults as an end user would experience them.
#    Placeholders are filled with seeded random values for per-ticket variety.
# ---------------------------------------------------------------------------

SYMPTOMS: dict[str, dict[str, list[str]]] = {
    # ---- Streaming Platform ------------------------------------------------
    "playback": {
        "ops": [
            "p99 playback start latency breached the 2500ms SLO in {region} for {minutes}m, currently {p99}ms, and customers report buffering",
            "playback-api pods are being OOMKilled, memory working set exceeded the 1024Mi limit, restart count up {small} on pod playback-api-{podhash}",
            "playback-api is in CrashLoopBackOff after the canary rollout, exit code 137 with {small} restarts, session starts are failing",
            "playback-cache-pvc is showing DiskIOPSSaturation, volume latency {pvclat}ms and cache reads timing out",
            "CPUThrottlingHigh on playback-api, throttled ratio 0.{ratio} with p99 start latency {p99}ms",
            "playback-api RSS is growing ~{mb}MB/min since the latest deploy, GC pauses near {gcms}ms and pod evictions rising",
            "{region} ingress is returning {pct}% 5xx on /v1/playback/start after an upstream routing change, {count} upstream resets",
            "retransmits spiking to {rps}/s in use1-az2 with ~{pct}% packet loss, clients seeing intermittent buffering",
            "playback HPA is pinned at max replicas while StartPlayback queue depth keeps rising, now {queue}",
            "the new playback rollout is stuck in ImagePullBackOff, registry answered {registryerr} for the hotfix tag",
            "playback start requests are timing out waiting on manifest-service at {tmo}ms, retry traffic is amplifying load",
            "a config rollout set manifest.cache_ttl_seconds from 120 to 0 and playback start error rate doubled within minutes",
            "multiple playback pods evicted from pressure nodes, node memory available down to {small}%",
        ],
        "user": [
            "movies keep buffering every couple of minutes tonight, I tried two different devices",
            "videos take forever to start, I stare at a spinner for 15+ seconds before anything plays",
            "playback keeps pausing to load even though my internet speed tests fine",
            "shows will not start at all, I just get an error after a long wait",
            "the stream froze three times during one episode and then kicked me out",
        ],
    },
    "manifest": {
        "ops": [
            "manifest fetch p99 is at {p99}ms and players are falling back to stale manifests",
            "manifest endpoints returning intermittent 5xx since the cache TTL change, {pct}% of fetches affected",
            "manifest generation lagging behind encoder output by {minutes}m for new titles",
        ],
        "user": [
            "video quality is stuck at the lowest setting and never adapts up",
            "the stream starts and then immediately errors out with a media error code",
        ],
    },
    "cdn-routing": {
        "ops": [
            "edge selection is routing {region} viewers to a distant POP, rebuffer ratio up {pct}%",
            "cdn-routing-service weights look wrong after the last config push, cache hit ratio dropped to {pct}%",
            "POP failover flapped {small} times in an hour and session throughput is sawtoothing",
        ],
        "user": [
            "streams are really choppy tonight even on fast wifi, the quality keeps dropping",
            "video keeps stalling only in the evenings, mornings are fine on the same connection",
        ],
    },
    "license-service": {
        "ops": [
            "DRM license acquisition is failing for ~{pct}% of session starts, license grants timing out at {tmo}ms",
            "license-service error rate jumped after the key-rotation job, {count} denials in the last hour",
        ],
        "user": [
            "I keep getting a licensing error when I try to play anything",
            "a movie says content not licensed for playback but it played fine yesterday",
        ],
    },
    "subtitle-service": {
        "ops": [
            "subtitle fetches returning 404 for newly published titles, {count} errors in the last hour",
            "subtitle-service sidecar sync is lagging {minutes}m so tracks are missing on fresh titles",
        ],
        "user": [
            "subtitles are out of sync by a few seconds on everything I watch",
            "captions will not turn on at all for some shows even though the setting is enabled",
        ],
    },
    # ---- Monetization Platform --------------------------------------------
    "billing": {
        "ops": [
            "duplicate payment captures detected in the ledger reconciliation job, {count} duplicates in batch ledger-20260617-{small2}",
            "billing-ledger DB connection pool is exhausted at 100% with a wait queue of {queue}, ledger writes blocked and captures timing out",
            "payment-captures consumers are {lag}k messages behind and reconciliation freshness has breached its SLO, oldest lag {minutes}m",
            "payments.idempotency.window_minutes regressed from 60 to 5 and the duplicate capture detector is firing",
            "billing-api capture latency at {tmo}ms with CPUThrottlingHigh, throttled ratio 0.{ratio}",
        ],
        "user": [
            "I was charged twice for this month, two identical charges a minute apart on my statement",
            "my card was billed two times for the same subscription period and I need one refunded",
        ],
    },
    "payment-service": {
        "ops": [
            "payment-gateway authorizations timing out at {tmo}ms on {pct}% of attempts, retries piling up",
            "card authorization error rate up {pct}% since {time}, issuer responses slow across the board",
        ],
        "user": [
            "my payment keeps failing at checkout even though the card works everywhere else",
            "I cannot update my card details, the page errors out every time I hit save",
        ],
    },
    "invoice-service": {
        "ops": [
            "invoice generation job has been failing since {time}, {count} invoices stuck in pending",
            "invoice PDFs rendering with the wrong tax lines after the template deploy",
        ],
        "user": [
            "my invoice for last month never arrived and the billing history page shows nothing",
            "the receipt I got shows a different amount than what my bank was actually charged",
        ],
    },
    "subscription-service": {
        "ops": [
            "plan-change events are not applying, {count} accounts stuck between tiers since the deploy",
            "renewal processing backlog at {count} accounts and renewals are failing silently",
        ],
        "user": [
            "I upgraded to the premium plan but my account still shows the basic tier",
            "I cancelled last week but it still says my subscription renews tomorrow",
        ],
    },
    # ---- Identity Platform -------------------------------------------------
    "auth-service": {
        "ops": [
            "admin lockout spike after the MFA provider policy refresh, {count} lockouts with northstar-mfa enforcement flipped from gradual to strict",
            "mTLS handshakes failing since the identity-api service certificate expired, {count} handshake failures and counting",
            "Redis hot key on session:tenant:enterprise-admins at {kops}k ops/s, Redis p99 {p99}ms, enterprise logins degraded",
            "login queue depth at {queue} with MFA verification latency {tmo}ms and the HPA already at max replicas",
            "token refresh failures at {pct}% since the {time} deploy, sessions dropping mid-stream",
        ],
        "user": [
            "I am locked out of my account after the MFA prompt, the code is never accepted",
            "I cannot log in at all, it says my credentials are wrong but a password reset did not help",
            "the login page loops back to itself every time I enter the verification code",
        ],
    },
    "profile-service": {
        "ops": [
            "profile reads returning 500s for ~{pct}% of requests since {time}",
            "profile preference writes timing out at {tmo}ms after the session cache change",
        ],
        "user": [
            "all my profiles disappeared, only the default one shows up now",
            "avatar and settings changes will not save, everything reverts when I go back",
        ],
    },
    "account-service": {
        "ops": [
            "account creation flow erroring at the final step for {pct}% of signups since {time}",
            "account detail lookups slow at {tmo}ms p99, downstream callers timing out",
        ],
        "user": [
            "trying to create an account but it errors every single time on the last step",
            "my account details page will not load, it just spins forever",
        ],
    },
    "device-auth-service": {
        "ops": [
            "device activation code validation failing, {pct}% of TV sign-ins erroring since the {time} deploy",
            "device token issuance p99 at {tmo}ms and set-top boxes retry-storming",
        ],
        "user": [
            "my TV keeps asking me to sign in again every time I open the app",
            "the activation code from my TV always says expired even when I type it in right away",
        ],
    },
    # ---- Content Discovery -------------------------------------------------
    "catalog-service": {
        "ops": [
            "titles published {small}h ago are still not visible in the catalog API, publish pipeline consumer stalled",
            "catalog listing endpoints returning partial rows, {pct}% of shelf requests missing items",
        ],
        "user": [
            "the new season released today but it does not show up anywhere in the app",
            "a movie I was watching yesterday has vanished from the entire catalog",
        ],
    },
    "metadata-service": {
        "ops": [
            "metadata reads serving stale artwork and descriptions after a cache invalidation misfired, {pct}% mismatch rate",
            "metadata enrichment queue backed up {minutes}m, new titles rendering with placeholder text",
        ],
        "user": [
            "episode descriptions are attached to the wrong shows and the thumbnails are mixed up too",
            "every title on my home screen shows the wrong runtime and a missing synopsis",
        ],
    },
    "search-service": {
        "ops": [
            "search p99 at {p99}ms with {pct}% of queries timing out since the index rebuild",
            "search index shard {small} is red and results are missing recent titles",
        ],
        "user": [
            "search returns nothing for titles I know exist, even with the exact name",
            "searching anything just shows a loading spinner and then an empty page",
        ],
    },
    "recommendation": {
        "ops": [
            "ranker-v42 inference errors spiked after the canary promotion, {pct}% error rate and homepage personalization degraded",
            "online feature freshness lag exceeds {minutes}m and ranking quality metrics are regressing",
            "recommendation-api OOMKilled with the model cache at {mb}MB, restarts climbing",
            "recommendation-api calls to its feature backend timing out at {tmo}ms, {pct}% timeout rate",
        ],
        "user": [
            "my homepage rows are completely generic today, none of my usual picks show up",
            "the app keeps suggesting kids' cartoons on my adult profile out of nowhere",
        ],
    },
    "personalization-service": {
        "ops": [
            "continue-watching row assembly failing for {pct}% of sessions since {time}",
            "personalized shelf ordering is falling back to editorial defaults, override rate {pct}%",
        ],
        "user": [
            "my continue watching row vanished and my list order is completely scrambled",
            "resume points are gone, every episode starts from the beginning again",
        ],
    },
    # ---- User Engagement ---------------------------------------------------
    "notification-service": {
        "ops": [
            "in-app notification fanout delayed {minutes}m, queue depth {queue} and climbing",
            "notification dedupe cache flushed during the deploy, users receiving repeats",
        ],
        "user": [
            "I keep getting the same new-episode notification five times in a row",
            "notifications show up hours after the episode actually dropped",
        ],
    },
    "email-service": {
        "ops": [
            "transactional email bounce rate up {pct}% since {time}, password-reset sends stuck in queue",
            "outbound SMTP relay throttling us, {count} messages deferred in the last hour",
        ],
        "user": [
            "I never received the password reset email, tried four times and checked spam",
            "signup confirmation emails are not arriving so I cannot verify my address",
        ],
    },
    "push-service": {
        "ops": [
            "APNs and FCM push delivery failing for {pct}% of devices since the token migration",
            "push token refresh job crashlooping, delivery receipts down {pct}% day over day",
        ],
        "user": [
            "push notifications stopped arriving on my phone entirely this week",
            "I get pushes on my tablet but my phone has been silent for days, same account",
        ],
    },
    "watchlist-service": {
        "ops": [
            "watchlist writes returning 409 conflicts, {count} per minute after the schema change",
            "watchlist reads intermittently empty, cache and store disagree for {pct}% of users",
        ],
        "user": [
            "titles I add to my list disappear as soon as I refresh",
            "my whole watchlist is empty this morning, it had about forty titles",
        ],
    },
    "ratings-service": {
        "ops": [
            "ratings ingestion lagging {minutes}m, thumbs signals not persisting downstream",
            "ratings write path erroring for {pct}% of events since {time}",
        ],
        "user": [
            "my thumbs-up ratings do not stick, everything resets when I reopen the app",
            "I rated a dozen shows and none of it saved or changed my suggestions",
        ],
    },
    # ---- Core Platform -----------------------------------------------------
    "api-gateway": {
        "ops": [
            "gateway returning 502 and 504 across multiple upstreams, {pct}% of requests failing since {time}",
            "rate limiter misconfiguration throttling legitimate traffic at {rps} rps, retry storms building",
            "gateway worker restarts spiking after the timeout tuning change, {small} restarts in 20m",
        ],
        "user": [
            "the whole app errors out intermittently, different screens but the same something-went-wrong message",
            "every few minutes the app logs me to an error page no matter what I tap",
        ],
    },
    "edge-router": {
        "ops": [
            "TLS handshake errors at the edge in {region}, {count} per minute and upstream resets climbing",
            "edge-router config reload is flapping listeners, brief full outages every {small}m",
        ],
        "user": [
            "the site will not load at all from my location, it times out before anything appears",
        ],
    },
    "config-service": {
        "ops": [
            "config rollout stuck at {pct}%, flags not propagating and pods holding stale values",
            "config watchers disconnected after the etcd failover, {count} stale clients",
        ],
        "user": [
            "half the app shows the new layout and half the old one, it flips between refreshes",
        ],
    },
    "experiment-service": {
        "ops": [
            "experiment assignments flapping between variants mid-session, exposure logging down since {time}",
            "assignment cache stampede at {rps} rps after the deploy, allocation service saturated",
        ],
        "user": [
            "the app keeps switching between two different home screen designs every time I open it",
        ],
    },
    "observability": {
        "ops": [
            "Fluent Bit buffers at {pct}% capacity and Loki push errors are dropping production logs, {small}% already lost",
            "Prometheus active series exploded to {mil}M after a request_id label landed on a hot metric, head memory at {gb}GB",
            "otel-collector OOMKilled against the 2Gi limit, span queue depth {queue}",
            "tail sampling error-rate policy was disabled in a config rollout, {pct}% of error traces dropped",
            "tempo-distributor writes timing out at {tmo}ms, {pct}% of spans failing to persist",
        ],
        "user": [
            "dashboards for my service show gaps for the last hour, traces are missing too",
        ],
    },
    # ---- Data Platform -----------------------------------------------------
    "event-ingestion-service": {
        "ops": [
            "ingest topic backlog at {mil}M events, consumer lag growing {count}k per minute",
            "event-ingestion-service dropping malformed batches since the schema bump, {pct}% reject rate",
        ],
        "user": [
            "client events from last night are missing downstream, there is a gap starting around {time}",
        ],
    },
    "analytics-service": {
        "ops": [
            "nightly aggregation job failed {small} times in a row, exec dashboards stale by {small2}h",
            "analytics query layer p99 at {p99}ms after the warehouse migration",
        ],
        "user": [
            "the engagement dashboard has not updated since yesterday morning",
        ],
    },
    "feature-store": {
        "ops": [
            "online feature freshness lag at {minutes}m on redis-feature-online, {pct}% stale features being served",
            "offline-to-online feature sync job is crashlooping since {time}, materialization stalled",
        ],
        "user": [
            "downstream ranking consumers report our features are {minutes} minutes stale and quality metrics are dipping",
        ],
    },
    "ml-ranking-service": {
        "ops": [
            "ranking endpoint p99 at {p99}ms with {pct}% inference errors after the model refresh",
            "ml-ranking-service pods evicted under node memory pressure, scores falling back to popularity",
        ],
        "user": [
            "score responses from the ranking endpoint are timing out for our batch job since {time}",
        ],
    },
}

# ---------------------------------------------------------------------------
# 3. Channel / tone / verbosity rendering
# ---------------------------------------------------------------------------

REGIONS = ["us-east-1", "us-west-2", "eu-west-1", "ap-south-1"]
NAMES = ["Sam", "Priya", "Jordan", "Alex", "Maya", "Chris", "Devon", "Nina",
         "Omar", "Lena", "Ravi", "Kate", "Marco", "Ingrid", "Tunde", "Yuki"]
SEVERITIES = ["SEV1", "SEV2", "SEV3"]

EMAIL_GREETINGS = ["Hi team,", "Hello,", "Hi there,", "Hey,", "Hi support,", "Good morning,", "To whom it may concern,"]
EMAIL_CLOSINGS = ["Thanks!", "Thanks in advance.", "Please advise.", "Appreciate any help.",
                  "Can someone take a look?", "Hope this can be sorted soon.", "Let me know if you need more details."]
EMAIL_SIGNOFFS = ["Best,", "Thanks,", "Regards,", "Cheers,", "- "]

SLACK_OPENERS = ["hey folks,", "heads up -", "fyi -", "anyone else seeing this?", "quick flag:",
                 "raising this here first:", "not sure if known, but"]
SLACK_CLOSERS = ["can someone take a look?", "who owns this?", "happy to hop on a call.",
                 "will open a ticket if it persists.", "cc on-call.", "thread me if you need logs.", ""]

ALERT_OPENERS = ["Paraphrasing the page we just got:", "Alertmanager fired and here is the summary:",
                 "Monitoring picked this up a few minutes ago:", "On-call summary from the last page:",
                 "Translating the alert for this queue:"]
ALERT_CLOSERS = ["Runbook link was stale, routing to you.", "Auto-remediation did not kick in.",
                 "Paging felt premature so filing here.", "Needs an owner before it breaches further.", ""]

EXTRA_DETAILS = [
    "Started around {time} UTC.",
    "Mostly {region} traffic from what we can tell.",
    "Happens on both web and the TV app.",
    "Retried after clearing cache, no change.",
    "First noticed by the {sev} bridge during triage.",
    "Roughly {pct}% of attempts are affected.",
    "Reference {ticket} from an earlier report that looks related.",
    "Nothing obvious in the last deploy diff.",
    "Impact is still growing per the last check.",
    "A restart made it better for about ten minutes.",
]

SUBJECT_PREFIXES = ["Issue:", "Problem with", "Urgent:", "Help needed -", "Ongoing issue:", "[Customer report]"]


def _fill(template: str, rng: random.Random) -> str:
    """Fill any known placeholders in a template with seeded random values."""
    values = {
        "region": rng.choice(REGIONS),
        "minutes": rng.randint(8, 55),
        "p99": rng.choice([1800, 2100, 2400, 2700, 3100, 3420, 3800, 4200]),
        "pct": rng.randint(6, 38),
        "small": rng.randint(2, 9),
        "small2": rng.randint(10, 48),
        "count": rng.choice([74, 120, 218, 340, 640, 980, 1840, 2400, 3200]),
        "queue": rng.choice([1860, 2600, 4200, 6800, 9300, 11800]),
        "pvclat": rng.choice([330, 420, 500, 610, 740]),
        "ratio": rng.choice([49, 58, 66, 72, 81]),
        "mb": rng.choice([72, 88, 132, 144, 160, 940]),
        "gcms": rng.choice([540, 760, 980]),
        "rps": rng.choice([800, 1200, 2400, 5200]),
        "registryerr": rng.choice(["429 Too Many Requests", "manifest unknown", "TLS handshake timeout", "blob unknown"]),
        "tmo": rng.choice([1800, 2000, 2500, 3000]),
        "lag": rng.choice([96, 140, 184, 210]),
        "kops": rng.choice([48, 66, 92]),
        "mil": rng.choice([9, 12, 14.5, 18]),
        "gb": rng.choice([28, 36, 42]),
        "podhash": f"{rng.randrange(16**4):04x}",
        "time": f"{rng.randint(0, 23):02d}:{rng.choice([0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55]):02d}",
        "sev": rng.choice(SEVERITIES),
        "ticket": f"SF-{rng.randint(1000, 9999)}",
    }
    return template.format(**values)


def _maybe_extra(rng: random.Random) -> str:
    """Verbosity variation: 0-2 extra detail sentences."""
    n = rng.choice([0, 0, 1, 1, 1, 2])
    picks = rng.sample(EXTRA_DETAILS, n)
    return " ".join(_fill(p, rng) for p in picks)


def render_email(service: str, symptom: str, rng: random.Random) -> str:
    subject = f"{rng.choice(SUBJECT_PREFIXES)} {rng.choice(['streaming account', 'my account', 'the app', service, 'service degradation', 'production issue'])}"
    body = symptom[0].upper() + symptom[1:]
    extra = _maybe_extra(rng)
    parts = [f"Subject: {subject}", "", f"{rng.choice(EMAIL_GREETINGS)} {body}."]
    if extra:
        parts.append(extra)
    parts.append(rng.choice(EMAIL_CLOSINGS))
    signoff = rng.choice(EMAIL_SIGNOFFS)
    sep = "" if signoff.endswith("- ") else "\n"
    parts.append(f"{signoff}{sep}{rng.choice(NAMES)}")
    return "\n".join(parts)


def render_slack(service: str, symptom: str, rng: random.Random) -> str:
    mention = rng.choice([f"{service}:", f"seeing this on {service} -", f"re {service}:", f"{service} in prod:"])
    pieces = [rng.choice(SLACK_OPENERS), mention, symptom + "."]
    extra = _maybe_extra(rng)
    if extra:
        pieces.append(extra.lower())
    closer = rng.choice(SLACK_CLOSERS)
    if closer:
        pieces.append(closer)
    return " ".join(pieces)


def render_portal(service: str, symptom: str, rng: random.Random) -> str:
    summary = symptom.split(",")[0]
    impact = rng.choice([
        "Multiple customers affected", "Single account affected", "Internal workflow blocked",
        "Revenue impacting", "Widespread, still growing", "Intermittent but recurring",
    ])
    lines = [
        f"Issue summary: {summary[0].upper() + summary[1:]}",
        f"Affected area: {rng.choice([service, 'production', service + ' (prod)'])}",
        f"Description: {symptom[0].upper() + symptom[1:]}. {_maybe_extra(rng)}".rstrip(),
        f"Impact: {impact}",
        f"First noticed: {_fill('{time}', rng)} UTC",
    ]
    return "\n".join(lines)


def render_alert(service: str, symptom: str, rng: random.Random) -> str:
    sev = rng.choice(SEVERITIES)
    pieces = [
        rng.choice(ALERT_OPENERS),
        f"{service} ({sev}) -",
        symptom + ".",
    ]
    extra = _maybe_extra(rng)
    if extra:
        pieces.append(extra)
    closer = rng.choice(ALERT_CLOSERS)
    if closer:
        pieces.append(closer)
    return " ".join(pieces)


# channel -> (renderer, preferred symptom register weights (user, ops))
CHANNELS = [
    ("user_email", render_email, (0.75, 0.25)),
    ("slack", render_slack, (0.15, 0.85)),
    ("portal", render_portal, (0.5, 0.5)),
    ("alert", render_alert, (0.0, 1.0)),
]

# ---------------------------------------------------------------------------
# 4. Generation loop with balance / dedupe / leakage guarantees
# ---------------------------------------------------------------------------

def make_ticket(service_id: str, rng: random.Random) -> str:
    display = SERVICE_DISPLAY.get(service_id, service_id)
    bank = SYMPTOMS[service_id]
    _, renderer, (w_user, _w_ops) = CHANNELS[rng.randrange(len(CHANNELS))]
    register = "user" if (bank["user"] and rng.random() < w_user) else "ops"
    symptom = _fill(rng.choice(bank[register] or bank["ops"]), rng)
    return renderer(display, symptom, rng)


def main() -> None:
    rng = random.Random(SEED)
    owning = load_service_owning_team()

    # queue label -> sorted list of its services (deterministic order)
    by_label: dict[str, list[str]] = {}
    for svc, label in sorted(owning.items()):
        by_label.setdefault(label, []).append(svc)
    labels = sorted(by_label)
    assert len(labels) == 7, f"expected 7 owning-team queues, got {labels}"

    missing = [s for svcs in by_label.values() for s in svcs if s not in SYMPTOMS]
    assert not missing, f"services without symptom banks: {missing}"

    rows: list[tuple[str, str]] = []
    seen: set[str] = set()
    for label in labels:
        services = by_label[label]
        for i in range(ROWS_PER_LABEL):
            service_id = services[i % len(services)]  # round-robin for intra-team spread
            for _attempt in range(60):
                text = make_ticket(service_id, rng)
                low = text.lower()
                if text not in seen and not any(lb.lower() in low for lb in labels):
                    break
            else:
                raise RuntimeError(f"could not produce a unique, leak-free ticket for {service_id}")
            seen.add(text)
            rows.append((label, text))

    rng.shuffle(rows)

    # Final hard checks
    counts = Counter(lbl for lbl, _ in rows)
    assert all(counts[lb] == ROWS_PER_LABEL for lb in labels), counts
    assert len({t for _, t in rows}) == len(rows), "duplicate ticket texts"
    for lbl, text in rows:
        assert lbl.lower() not in text.lower(), f"label leakage: {lbl!r} in ticket"

    with OUT_CSV.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["category_truth", "text"])  # mirrors stock support_tickets.csv
        writer.writerows(rows)

    print(f"wrote {len(rows)} rows -> {OUT_CSV}")
    print("label distribution:")
    for lb in labels:
        print(f"  {lb:<24} {counts[lb]}")
    print("leakage check: PASS (no ticket contains any queue label, case-insensitive)")
    print("duplicate check: PASS (0 duplicate texts)")


if __name__ == "__main__":
    main()
