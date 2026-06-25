package main

import (
	"crypto/sha1"
	"encoding/hex"
	"fmt"
	"strconv"
)

func issueKey(incidentID string) string {
	sum := sha1.Sum([]byte(incidentID))
	hexstr := hex.EncodeToString(sum[:])[:8]
	n, _ := strconv.ParseInt(hexstr, 16, 64)
	return fmt.Sprintf("INC-%d", n%900000+100000)
}
