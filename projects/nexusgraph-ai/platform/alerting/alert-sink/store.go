package main

import (
	"sync"
	"time"
)

type ReceivedAlert struct {
	Status      string            `json:"status"`
	Labels      map[string]string `json:"labels"`
	Annotations map[string]string `json:"annotations"`
	ReceivedAt  time.Time         `json:"receivedAt"`
}

type AlertStore struct {
	mu       sync.Mutex
	capacity int
	items    []ReceivedAlert // oldest..newest
}

func NewAlertStore(capacity int) *AlertStore {
	return &AlertStore{capacity: capacity}
}

func (s *AlertStore) Add(a ReceivedAlert) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if a.ReceivedAt.IsZero() {
		a.ReceivedAt = time.Now().UTC()
	}
	s.items = append(s.items, a)
	if len(s.items) > s.capacity {
		s.items = s.items[len(s.items)-s.capacity:]
	}
}

func (s *AlertStore) List() []ReceivedAlert {
	s.mu.Lock()
	defer s.mu.Unlock()
	out := make([]ReceivedAlert, len(s.items))
	for i, a := range s.items { // reverse → newest first
		out[len(s.items)-1-i] = a
	}
	return out
}
