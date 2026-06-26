package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"strings"
	"sync"
	"sync/atomic"
)

type issue struct {
	Key    string         `json:"key"`
	ID     string         `json:"id"`
	Self   string         `json:"self"`
	Fields map[string]any `json:"fields"`
}

var (
	mu     sync.Mutex
	issues = map[string]issue{}
	keySeq int64
	idSeq  int64
)

func createIssue(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "POST only", http.StatusMethodNotAllowed)
		return
	}
	var body struct {
		IncidentID string         `json:"incident_id"`
		Fields     map[string]any `json:"fields"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	var key string
	if body.IncidentID != "" {
		key = issueKey(body.IncidentID)
	} else {
		key = fmt.Sprintf("INC-%d", atomic.AddInt64(&keySeq, 1)+100000)
	}
	id := fmt.Sprintf("%d", atomic.AddInt64(&idSeq, 1))
	it := issue{Key: key, ID: id, Self: "/rest/api/2/issue/" + key, Fields: body.Fields}
	mu.Lock()
	issues[key] = it
	mu.Unlock()
	w.Header().Set("content-type", "application/json")
	json.NewEncoder(w).Encode(it)
}

func getIssue(w http.ResponseWriter, r *http.Request) {
	key := strings.TrimPrefix(r.URL.Path, "/rest/api/2/issue/")
	mu.Lock()
	it, ok := issues[key]
	mu.Unlock()
	if !ok {
		http.Error(w, "not found", http.StatusNotFound)
		return
	}
	w.Header().Set("content-type", "application/json")
	json.NewEncoder(w).Encode(it)
}

func listIssues(w http.ResponseWriter, _ *http.Request) {
	mu.Lock()
	out := make([]issue, 0, len(issues))
	for _, it := range issues {
		out = append(out, it)
	}
	mu.Unlock()
	w.Header().Set("content-type", "application/json")
	json.NewEncoder(w).Encode(out)
}

func main() {
	mux := http.NewServeMux()
	mux.HandleFunc("/rest/api/2/issue", createIssue)
	mux.HandleFunc("/rest/api/2/issue/", getIssue)
	mux.HandleFunc("/issues", listIssues)
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) { w.Write([]byte("ok")) })
	log.Printf("jira-mock listening on :8080")
	log.Fatal(http.ListenAndServe(":8080", mux))
}
