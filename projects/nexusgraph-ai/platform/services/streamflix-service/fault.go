package main

import (
	"sync"
	"time"
)

type FaultStore struct {
	mu     sync.RWMutex
	mode   string
	value  float64
	expiry time.Time
}

func NewFaultStore() *FaultStore { return &FaultStore{} }

func (f *FaultStore) Set(mode string, value float64, ttl time.Duration) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.mode, f.value = mode, value
	if ttl > 0 {
		f.expiry = time.Now().Add(ttl)
	} else {
		f.expiry = time.Time{}
	}
}

func (f *FaultStore) Clear() {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.mode, f.value, f.expiry = "", 0, time.Time{}
}

func (f *FaultStore) Active() (string, float64, bool) {
	f.mu.RLock()
	defer f.mu.RUnlock()
	if f.mode == "" {
		return "", 0, false
	}
	if !f.expiry.IsZero() && time.Now().After(f.expiry) {
		return "", 0, false
	}
	return f.mode, f.value, true
}
