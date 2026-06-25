package main

import (
	"os"
	"path/filepath"
	"testing"
)

func TestLoadCatalogMultiDoc(t *testing.T) {
	dir := t.TempDir()
	p := filepath.Join(dir, "c.yaml")
	os.WriteFile(p, []byte("kind: System\nmetadata:\n  name: streamflix\n---\nkind: Component\nmetadata:\n  name: billing-service\n"), 0644)
	ents, err := loadCatalog(p)
	if err != nil {
		t.Fatal(err)
	}
	if len(ents) != 2 {
		t.Fatalf("want 2 entities, got %d", len(ents))
	}
	if ents[1]["kind"] != "Component" {
		t.Fatalf("got %v", ents[1]["kind"])
	}
}
