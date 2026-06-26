package main

import (
	"encoding/json"
	"log"
	"net/http"
	"os"
	"strings"
)

type OncallEntry struct {
	Schedule string `json:"schedule"`
	Person   string `json:"person"`
	Team     string `json:"team"`
}
type EscalationEntry struct {
	Policy string   `json:"policy"`
	Steps  []string `json:"steps"`
}
type Seed struct {
	Oncall     map[string]OncallEntry     `json:"oncall"`
	Escalation map[string]EscalationEntry `json:"escalation"`
}

var seed Seed

func loadSeed(path string) (Seed, error) {
	var s Seed
	b, err := os.ReadFile(path)
	if err != nil {
		return s, err
	}
	err = json.Unmarshal(b, &s)
	return s, err
}

func getOncall(w http.ResponseWriter, r *http.Request) {
	svc := strings.TrimPrefix(r.URL.Path, "/oncall/")
	e, ok := seed.Oncall[svc]
	w.Header().Set("content-type", "application/json")
	if !ok {
		json.NewEncoder(w).Encode(map[string]any{"service": svc, "schedule": nil, "person": nil, "team": nil})
		return
	}
	json.NewEncoder(w).Encode(map[string]any{"service": svc, "schedule": e.Schedule, "person": e.Person, "team": e.Team})
}

func getEscalation(w http.ResponseWriter, r *http.Request) {
	parts := strings.Split(strings.TrimPrefix(r.URL.Path, "/escalation/"), "/")
	w.Header().Set("content-type", "application/json")
	if len(parts) < 2 {
		http.Error(w, "need /escalation/{service}/{severity}", http.StatusBadRequest)
		return
	}
	key := parts[0] + "|" + parts[1]
	e, ok := seed.Escalation[key]
	if !ok {
		json.NewEncoder(w).Encode(map[string]any{"service": parts[0], "severity": parts[1], "policy": nil, "steps": []string{}})
		return
	}
	json.NewEncoder(w).Encode(map[string]any{"service": parts[0], "severity": parts[1], "policy": e.Policy, "steps": e.Steps})
}

func getSchedules(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set("content-type", "application/json")
	json.NewEncoder(w).Encode(seed.Oncall)
}

func main() {
	path := os.Getenv("SEED_PATH")
	if path == "" {
		path = "/seed/oncall-seed.json"
	}
	if s, err := loadSeed(path); err != nil {
		log.Printf("seed load failed (%v); serving empty", err)
	} else {
		seed = s
	}
	mux := http.NewServeMux()
	mux.HandleFunc("/oncall/", getOncall)
	mux.HandleFunc("/escalation/", getEscalation)
	mux.HandleFunc("/schedules", getSchedules)
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) { w.Write([]byte("ok")) })
	log.Printf("oncall-registry listening on :8080")
	log.Fatal(http.ListenAndServe(":8080", mux))
}
