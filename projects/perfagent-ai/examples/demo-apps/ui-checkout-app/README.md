# UI Checkout Demo

Browser-facing checkout app for UI-oriented performance experiments.

Endpoints:

- `GET /` serves the checkout page.
- `POST /api/checkout` authorizes a synthetic checkout.
- `GET /openapi.json` exposes the API contract for the checkout endpoint.
- `GET /metrics` exposes simple Prometheus-style counters.

Run:

```bash
docker compose --profile demo up --build demo-ui-checkout
```

Open: `http://localhost:8083`
