#!/usr/bin/env bash
set -u
cd ~/x402/services
services=$(docker compose config --services)
total=$(echo "$services" | wc -l)
i=0
fail=0
> ~/build_sequential.log
for s in $services; do
  i=$((i+1))
  echo "[$i/$total] $s" | tee -a ~/build_sequential.log
  if docker compose build "$s" >> ~/build_sequential.log 2>&1; then
    echo "  OK" | tee -a ~/build_sequential.log
  else
    fail=$((fail+1))
    echo "  FAIL: $s" | tee -a ~/build_sequential.log
  fi
done
echo "Termine. Echecs: $fail / $total" | tee -a ~/build_sequential.log
