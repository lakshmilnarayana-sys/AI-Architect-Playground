package main

import (
	"os"
	"path/filepath"
	"testing"
)

func TestLoadSeedAndLookup(t *testing.T) {
	dir := t.TempDir()
	p := filepath.Join(dir, "seed.json")
	os.WriteFile(p, []byte(`{"oncall":{"billing-service":{"schedule":"Billing Primary","person":"Daniel Okafor","team":"Billing Platform"}},"escalation":{"billing-service|SEV2":{"policy":"Billing SEV2","steps":["oncall","manager"]}}}`), 0644)
	seed, err := loadSeed(p)
	if err != nil {
		t.Fatal(err)
	}
	if seed.Oncall["billing-service"].Person != "Daniel Okafor" {
		t.Fatalf("got %+v", seed.Oncall["billing-service"])
	}
	if seed.Escalation["billing-service|SEV2"].Policy != "Billing SEV2" {
		t.Fatalf("got %+v", seed.Escalation["billing-service|SEV2"])
	}
}
