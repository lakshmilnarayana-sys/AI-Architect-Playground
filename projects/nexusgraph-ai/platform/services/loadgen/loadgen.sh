#!/usr/bin/env sh
set -eu
: "${TARGETS:?set TARGETS}"
: "${RPS:=5}"
sleep_s=$(awk "BEGIN{print 1/$RPS}")
echo "loadgen: RPS=$RPS targets=$TARGETS"
while true; do
  for t in $TARGETS; do
    wget -q -O /dev/null "$t" || true
    sleep "$sleep_s"
  done
done
