"""Generate Kubernetes manifests for StreamFlix services from the graph CSVs."""
import argparse
import csv
import re
from pathlib import Path

NAMESPACE = "streamflix-prod"


def _short(service_id: str) -> str:
    return service_id.split(":", 1)[1]


def _safe_label(value: str) -> str:
    """Sanitize a string so it is a valid Kubernetes label value (max 63 chars,
    alphanumeric / '-' / '_' / '.', starts and ends with alphanumeric)."""
    # Replace any invalid character with '-'
    sanitized = re.sub(r"[^A-Za-z0-9._-]", "-", value)
    # Collapse consecutive dashes
    sanitized = re.sub(r"-{2,}", "-", sanitized)
    # Strip leading/trailing non-alphanumeric
    sanitized = sanitized.strip("-._")
    # Truncate to 63 chars, then strip again in case truncation left a dash
    sanitized = sanitized[:63].rstrip("-._")
    return sanitized or "unknown"


def _k8s_name(short: str) -> str:
    """Kubernetes Service/Deployment name for a service short-id, avoiding a doubled -service suffix."""
    return short if short.endswith("-service") else f"{short}-service"


def load_services(nodes_path: Path) -> list[dict]:
    services = []
    with open(nodes_path, newline="") as fh:
        for row in csv.DictReader(fh):
            if row.get("label") != "Service":
                continue
            services.append({
                "id": row["id"],
                "short": _short(row["id"]),
                "name": row["name"],
                "tier": row.get("description", "internal").strip(),
            })
    return services


def load_dependencies(edges_path: Path) -> dict[str, list[str]]:
    deps: dict[str, list[str]] = {}
    with open(edges_path, newline="") as fh:
        for row in csv.DictReader(fh):
            if row.get("relationship") != "DEPENDS_ON":
                continue
            deps.setdefault(row["source"], []).append(row["target"])
    return deps


def render_service(svc: dict, deps: list[str], image: str) -> str:
    name = _k8s_name(svc['short'])
    downstreams = ",".join(f"{_short(d)}={_k8s_name(_short(d))}:8080/" for d in deps)
    tier_label = _safe_label(svc['tier'])
    return f"""---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {name}
  namespace: {NAMESPACE}
  labels: {{app: {name}, tier: "{tier_label}"}}
spec:
  replicas: 1
  selector: {{matchLabels: {{app: {name}}}}}
  template:
    metadata:
      labels: {{app: {name}}}
      annotations: {{prometheus.io/scrape: "true", prometheus.io/port: "8080"}}
    spec:
      containers:
        - name: {name}
          image: {image}
          ports: [{{containerPort: 8080}}]
          env:
            - {{name: SERVICE_NAME, value: "{name}"}}
            - {{name: SERVICE_TIER, value: "{svc['tier']}"}}
            - {{name: DOWNSTREAMS, value: "{downstreams}"}}
            - {{name: BASE_LATENCY_MS, value: "20"}}
            - {{name: ERROR_RATE, value: "0"}}
          readinessProbe: {{httpGet: {{path: /readyz, port: 8080}}, initialDelaySeconds: 2}}
          livenessProbe: {{httpGet: {{path: /healthz, port: 8080}}, initialDelaySeconds: 5}}
          resources:
            requests: {{cpu: "50m", memory: "32Mi"}}
            limits: {{cpu: "300m", memory: "128Mi"}}
---
apiVersion: v1
kind: Service
metadata:
  name: {name}
  namespace: {NAMESPACE}
  labels: {{app: {name}}}
spec:
  selector: {{app: {name}}}
  ports: [{{port: 8080, targetPort: 8080, name: http}}]
"""


def main(out_dir: str, image: str, nodes: str, edges: str) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    services = load_services(Path(nodes))
    deps = load_dependencies(Path(edges))
    for svc in services:
        manifest = render_service(svc, deps.get(svc["id"], []), image)
        (out / f"{_k8s_name(svc['short'])}.yaml").write_text(manifest)
    print(f"Generated {len(services)} service manifests in {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="platform/cluster/generated")
    ap.add_argument("--image", default="localhost:5001/streamflix-service:dev")
    ap.add_argument("--nodes", default="graph/nodes.csv")
    ap.add_argument("--edges", default="graph/edges.csv")
    args = ap.parse_args()
    main(args.out, args.image, args.nodes, args.edges)
