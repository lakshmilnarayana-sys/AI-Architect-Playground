package main

import "testing"

func TestChannelStorePostAndGet(t *testing.T) {
	s := NewStore()
	s.PostMessage("#inc-billing", Message{Author: "bot", Text: "hello"})
	s.PostMessage("#inc-billing", Message{Author: "bot", Text: "world"})
	msgs := s.Channel("#inc-billing")
	if len(msgs) != 2 {
		t.Fatalf("want 2, got %d", len(msgs))
	}
	if msgs[0].Text != "world" {
		t.Fatalf("want newest-first, got %q", msgs[0].Text)
	}
	if msgs[0].Ts == "" {
		t.Fatal("expected a ts assigned")
	}
}
