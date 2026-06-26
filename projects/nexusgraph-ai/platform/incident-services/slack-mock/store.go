package main

import (
	"fmt"
	"sync"
	"sync/atomic"
	"time"
)

type Message struct {
	Ts     string `json:"ts"`
	Author string `json:"author"`
	Text   string `json:"text"`
}

type Store struct {
	mu       sync.Mutex
	channels map[string][]Message
	alerts   []map[string]any
	seq      int64
}

func NewStore() *Store { return &Store{channels: map[string][]Message{}} }

func (s *Store) nextTs() string {
	n := atomic.AddInt64(&s.seq, 1)
	return fmt.Sprintf("%d.%06d", time.Now().Unix(), n)
}

func (s *Store) PostMessage(channel string, m Message) Message {
	s.mu.Lock()
	defer s.mu.Unlock()
	m.Ts = s.nextTs()
	s.channels[channel] = append(s.channels[channel], m)
	return m
}

func (s *Store) Channel(channel string) []Message {
	s.mu.Lock()
	defer s.mu.Unlock()
	src := s.channels[channel]
	out := make([]Message, len(src))
	for i, m := range src {
		out[len(src)-1-i] = m
	}
	return out
}

func (s *Store) AddAlert(a map[string]any) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.alerts = append(s.alerts, a)
}

func (s *Store) Alerts() []map[string]any {
	s.mu.Lock()
	defer s.mu.Unlock()
	out := make([]map[string]any, len(s.alerts))
	copy(out, s.alerts)
	return out
}
