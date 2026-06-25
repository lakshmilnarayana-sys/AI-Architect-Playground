package main

import (
	"encoding/json"
	"log"
	"net/http"
	"os"

	"gopkg.in/yaml.v3"
)

func loadCatalog(path string) ([]map[string]any, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	dec := yaml.NewDecoder(f)
	var out []map[string]any
	for {
		var doc map[string]any
		if err := dec.Decode(&doc); err != nil {
			break
		}
		if doc != nil {
			out = append(out, doc)
		}
	}
	return out, nil
}

func main() {
	path := os.Getenv("CATALOG_PATH")
	if path == "" {
		path = "/catalog/catalog.yaml"
	}
	entities, err := loadCatalog(path)
	if err != nil {
		log.Printf("catalog load failed: %v", err)
	}
	mux := http.NewServeMux()
	mux.HandleFunc("/api/catalog/entities", func(w http.ResponseWriter, r *http.Request) {
		kind := r.URL.Query().Get("filter")
		w.Header().Set("content-type", "application/json")
		if kind == "" {
			json.NewEncoder(w).Encode(entities)
			return
		}
		// filter=kind=component
		want := ""
		if len(kind) > 5 && kind[:5] == "kind=" {
			want = kind[5:]
		}
		var filtered []map[string]any
		for _, e := range entities {
			k, _ := e["kind"].(string)
			if want == "" || equalFold(k, want) {
				filtered = append(filtered, e)
			}
		}
		json.NewEncoder(w).Encode(filtered)
	})
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) { w.Write([]byte("ok")) })
	log.Printf("catalog-server serving %d entities on :7007", len(entities))
	log.Fatal(http.ListenAndServe(":7007", mux))
}

func equalFold(a, b string) bool {
	if len(a) != len(b) {
		return false
	}
	for i := 0; i < len(a); i++ {
		ca, cb := a[i], b[i]
		if 'A' <= ca && ca <= 'Z' {
			ca += 32
		}
		if 'A' <= cb && cb <= 'Z' {
			cb += 32
		}
		if ca != cb {
			return false
		}
	}
	return true
}
