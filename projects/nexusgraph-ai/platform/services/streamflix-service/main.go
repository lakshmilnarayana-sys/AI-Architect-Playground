package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"math/rand"
	"net/http"
	"os"
	"runtime"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

var (
	svcName     = env("SERVICE_NAME", "unknown-service")
	svcTier     = env("SERVICE_TIER", "internal")
	baseMS, _   = strconv.Atoi(env("BASE_LATENCY_MS", "20"))
	errRate, _  = strconv.ParseFloat(env("ERROR_RATE", "0"), 64)
	faults      = NewFaultStore()
	leak        [][]byte
	leakMu      sync.Mutex

	reqs = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "http_requests_total", Help: "Requests by code",
		ConstLabels: prometheus.Labels{"service": svcName},
	}, []string{"code"})
	dur = promauto.NewHistogramVec(prometheus.HistogramOpts{
		Name: "http_request_duration_seconds", Help: "Latency",
		Buckets: prometheus.DefBuckets, ConstLabels: prometheus.Labels{"service": svcName},
	}, []string{"code"})
	down = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "downstream_requests_total", Help: "Downstream calls",
		ConstLabels: prometheus.Labels{"service": svcName},
	}, []string{"target", "code"})
)

func env(k, d string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return d
}

func downstreams() map[string]string {
	out := map[string]string{}
	for _, p := range strings.Split(os.Getenv("DOWNSTREAMS"), ",") {
		p = strings.TrimSpace(p)
		if p == "" {
			continue
		}
		if kv := strings.SplitN(p, "=", 2); len(kv) == 2 {
			out[kv[0]] = kv[1]
		}
	}
	return out
}

func applyFault() (extraLatency time.Duration, forceErr bool) {
	mode, val, ok := faults.Active()
	if !ok {
		return 0, false
	}
	switch mode {
	case "cpu_throttle":
		// busy-loop to burn CPU against a low cgroup limit
		deadline := time.Now().Add(time.Duration(50+val*100) * time.Millisecond)
		for time.Now().Before(deadline) {
		}
		return 0, false
	case "memory_leak", "oom_kill":
		leakMu.Lock()
		leak = append(leak, make([]byte, 8*1024*1024)) // 8MiB per hit
		leakMu.Unlock()
		runtime.GC()
		return 0, false
	case "pod_restart":
		log.Printf("fault pod_restart: exiting")
		os.Exit(137)
	case "disk_iops":
		return time.Duration(val*100) * time.Millisecond, false
	default: // node_pressure, hpa_maxed, image_pull_backoff handled at manifest layer
		return 0, false
	}
	return 0, false
}

func handleRoot(w http.ResponseWriter, r *http.Request) {
	start := time.Now()
	time.Sleep(time.Duration(baseMS) * time.Millisecond)
	extra, forceErr := applyFault()
	time.Sleep(extra)

	code := http.StatusOK
	if forceErr || rand.Float64() < errRate {
		code = http.StatusInternalServerError
	}
	// fan out to downstreams
	client := &http.Client{Timeout: 2 * time.Second}
	for name, url := range downstreams() {
		resp, err := client.Get(url)
		dc := "error"
		if err == nil {
			dc = strconv.Itoa(resp.StatusCode)
			io.Copy(io.Discard, resp.Body)
			resp.Body.Close()
		}
		down.WithLabelValues(name, dc).Inc()
	}
	w.WriteHeader(code)
	fmt.Fprintf(w, `{"service":%q,"tier":%q,"code":%d}`, svcName, svcTier, code)
	reqs.WithLabelValues(strconv.Itoa(code)).Inc()
	dur.WithLabelValues(strconv.Itoa(code)).Observe(time.Since(start).Seconds())
}

func handleFault(w http.ResponseWriter, r *http.Request) {
	var body struct {
		Mode  string  `json:"mode"`
		Value float64 `json:"value"`
		TTL   int     `json:"ttl"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	if body.Mode == "" || body.Mode == "clear" {
		faults.Clear()
		leakMu.Lock()
		leak = nil
		leakMu.Unlock()
		w.Write([]byte(`{"status":"cleared"}`))
		return
	}
	ttl := time.Duration(body.TTL) * time.Second
	if body.TTL == 0 {
		ttl = 10 * time.Minute
	}
	faults.Set(body.Mode, body.Value, ttl)
	fmt.Fprintf(w, `{"status":"set","mode":%q}`, body.Mode)
}

func main() {
	_ = context.Background
	mux := http.NewServeMux()
	mux.HandleFunc("/", handleRoot)
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) { w.Write([]byte("ok")) })
	mux.HandleFunc("/readyz", func(w http.ResponseWriter, _ *http.Request) { w.Write([]byte("ready")) })
	mux.HandleFunc("/admin/fault", handleFault)
	mux.Handle("/metrics", promhttp.Handler())
	addr := ":" + env("PORT", "8080")
	log.Printf("%s (%s) listening on %s", svcName, svcTier, addr)
	log.Fatal(http.ListenAndServe(addr, mux))
}
