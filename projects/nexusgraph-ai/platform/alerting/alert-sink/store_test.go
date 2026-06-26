package main

import "testing"

func TestAlertStoreNewestFirst(t *testing.T) {
	s := NewAlertStore(10)
	s.Add(ReceivedAlert{Status: "firing", Labels: map[string]string{"alertname": "A"}})
	s.Add(ReceivedAlert{Status: "firing", Labels: map[string]string{"alertname": "B"}})
	got := s.List()
	if len(got) != 2 {
		t.Fatalf("want 2, got %d", len(got))
	}
	if got[0].Labels["alertname"] != "B" {
		t.Fatalf("want newest-first (B), got %s", got[0].Labels["alertname"])
	}
}

func TestAlertStoreCapacityEvictsOldest(t *testing.T) {
	s := NewAlertStore(2)
	s.Add(ReceivedAlert{Labels: map[string]string{"alertname": "A"}})
	s.Add(ReceivedAlert{Labels: map[string]string{"alertname": "B"}})
	s.Add(ReceivedAlert{Labels: map[string]string{"alertname": "C"}})
	got := s.List()
	if len(got) != 2 {
		t.Fatalf("want capacity 2, got %d", len(got))
	}
	if got[0].Labels["alertname"] != "C" || got[1].Labels["alertname"] != "B" {
		t.Fatalf("want [C,B], got [%s,%s]", got[0].Labels["alertname"], got[1].Labels["alertname"])
	}
}
