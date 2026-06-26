package main

import "testing"

func TestIssueKeyDeterministic(t *testing.T) {
	a := issueKey("incident:billing-oom")
	b := issueKey("incident:billing-oom")
	if a != b {
		t.Fatalf("not deterministic: %s vs %s", a, b)
	}
	if len(a) < 5 || a[:4] != "INC-" {
		t.Fatalf("bad key format: %s", a)
	}
}
