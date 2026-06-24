package main

import (
	"testing"
	"time"
)

func TestFaultStoreSetAndActive(t *testing.T) {
	fs := NewFaultStore()
	if _, _, ok := fs.Active(); ok {
		t.Fatal("expected no active fault initially")
	}
	fs.Set("cpu_throttle", 0.5, time.Minute)
	mode, val, ok := fs.Active()
	if !ok || mode != "cpu_throttle" || val != 0.5 {
		t.Fatalf("got %q %v %v", mode, val, ok)
	}
}

func TestFaultStoreExpiry(t *testing.T) {
	fs := NewFaultStore()
	fs.Set("oom_kill", 1, 10*time.Millisecond)
	time.Sleep(20 * time.Millisecond)
	if _, _, ok := fs.Active(); ok {
		t.Fatal("expected fault to expire")
	}
}

func TestFaultStoreClear(t *testing.T) {
	fs := NewFaultStore()
	fs.Set("memory_leak", 1, time.Hour)
	fs.Clear()
	if _, _, ok := fs.Active(); ok {
		t.Fatal("expected cleared fault")
	}
}
