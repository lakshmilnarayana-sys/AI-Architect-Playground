package main

import (
	"encoding/json"
	"log"
	"net/http"
	"strings"
)

var store = NewStore()

func postMessage(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "POST only", http.StatusMethodNotAllowed)
		return
	}
	var body struct {
		Channel  string `json:"channel"`
		Text     string `json:"text"`
		Username string `json:"username"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	if body.Channel == "" {
		body.Channel = "#incidents"
	}
	author := body.Username
	if author == "" {
		author = "incident-bot"
	}
	m := store.PostMessage(body.Channel, Message{Author: author, Text: body.Text})
	w.Header().Set("content-type", "application/json")
	json.NewEncoder(w).Encode(map[string]any{"ok": true, "ts": m.Ts, "channel": body.Channel})
}

func getChannel(w http.ResponseWriter, r *http.Request) {
	name := strings.TrimPrefix(r.URL.Path, "/channels/")
	if !strings.HasPrefix(name, "#") {
		name = "#" + name
	}
	w.Header().Set("content-type", "application/json")
	json.NewEncoder(w).Encode(store.Channel(name))
}

func webhook(w http.ResponseWriter, r *http.Request) {
	var p struct {
		Alerts []map[string]any `json:"alerts"`
	}
	if err := json.NewDecoder(r.Body).Decode(&p); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	for _, a := range p.Alerts {
		store.AddAlert(a)
		labels, _ := a["labels"].(map[string]any)
		log.Printf("alert received: %v", labels["alertname"])
	}
	w.WriteHeader(http.StatusOK)
	w.Write([]byte(`{"ok":true}`))
}

func getAlerts(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set("content-type", "application/json")
	json.NewEncoder(w).Encode(store.Alerts())
}

func main() {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/chat.postMessage", postMessage)
	mux.HandleFunc("/channels/", getChannel)
	mux.HandleFunc("/webhook", webhook)
	mux.HandleFunc("/alerts", getAlerts)
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) { w.Write([]byte("ok")) })
	log.Printf("slack-mock listening on :8080")
	log.Fatal(http.ListenAndServe(":8080", mux))
}
