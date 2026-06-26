package main

import (
	"encoding/json"
	"log"
	"net/http"
)

var store = NewAlertStore(100)

// Alertmanager webhook payload (subset).
type amPayload struct {
	Status string `json:"status"`
	Alerts []struct {
		Status      string            `json:"status"`
		Labels      map[string]string `json:"labels"`
		Annotations map[string]string `json:"annotations"`
	} `json:"alerts"`
}

func handleWebhook(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "POST only", http.StatusMethodNotAllowed)
		return
	}
	var p amPayload
	if err := json.NewDecoder(r.Body).Decode(&p); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	for _, a := range p.Alerts {
		store.Add(ReceivedAlert{Status: a.Status, Labels: a.Labels, Annotations: a.Annotations})
		log.Printf("alert %s status=%s service=%s failure_mode=%s runbook=%s",
			a.Labels["alertname"], a.Status, a.Labels["service"],
			a.Labels["failure_mode"], a.Annotations["runbook_url"])
	}
	w.WriteHeader(http.StatusOK)
	w.Write([]byte(`{"received":true}`))
}

func handleAlerts(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set("content-type", "application/json")
	json.NewEncoder(w).Encode(store.List())
}

func main() {
	mux := http.NewServeMux()
	mux.HandleFunc("/webhook", handleWebhook)
	mux.HandleFunc("/alerts", handleAlerts)
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) { w.Write([]byte("ok")) })
	log.Printf("alert-sink listening on :8080")
	log.Fatal(http.ListenAndServe(":8080", mux))
}
