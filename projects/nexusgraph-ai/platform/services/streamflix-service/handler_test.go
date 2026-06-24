package main

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

// resetFaults clears the package-global fault store and leak slice between sub-tests.
func resetFaults() {
	faults.Clear()
	leakMu.Lock()
	leak = nil
	leakMu.Unlock()
}

func TestHandleFault_ValidMode(t *testing.T) {
	resetFaults()
	body := `{"mode":"cpu_throttle","value":1,"ttl":5}`
	req := httptest.NewRequest(http.MethodPost, "/admin/fault", bytes.NewBufferString(body))
	rec := httptest.NewRecorder()

	handleFault(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	_, _, ok := faults.Active()
	if !ok {
		t.Fatal("expected an active fault after setting cpu_throttle")
	}
}

func TestHandleFault_UnknownMode(t *testing.T) {
	resetFaults()
	body := `{"mode":"bogus"}`
	req := httptest.NewRequest(http.MethodPost, "/admin/fault", bytes.NewBufferString(body))
	rec := httptest.NewRecorder()

	handleFault(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for unknown mode, got %d: %s", rec.Code, rec.Body.String())
	}
	_, _, ok := faults.Active()
	if ok {
		t.Fatal("expected no active fault after rejected unknown mode")
	}
	// Verify response body is parseable JSON
	var resp map[string]interface{}
	if err := json.NewDecoder(rec.Body).Decode(&resp); err != nil {
		t.Fatalf("expected JSON error body, got parse error: %v", err)
	}
}

func TestHandleFault_Clear(t *testing.T) {
	resetFaults()
	// Seed a fault first
	faults.Set("memory_leak", 1, 0)

	body := `{"mode":"clear"}`
	req := httptest.NewRequest(http.MethodPost, "/admin/fault", bytes.NewBufferString(body))
	rec := httptest.NewRecorder()

	handleFault(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	_, _, ok := faults.Active()
	if ok {
		t.Fatal("expected no active fault after clear")
	}
}
