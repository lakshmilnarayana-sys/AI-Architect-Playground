package main

import (
	"context"
	"testing"
)

func TestInitTracerReturnsShutdown(t *testing.T) {
	// endpoint need not be reachable; exporter creation is lazy/batched.
	shutdown, err := initTracer(context.Background(), "test-service", "localhost:4318")
	if err != nil {
		t.Fatalf("initTracer error: %v", err)
	}
	if shutdown == nil {
		t.Fatal("expected non-nil shutdown func")
	}
	_ = shutdown(context.Background())
}
