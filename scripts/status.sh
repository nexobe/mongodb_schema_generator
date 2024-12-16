#!/bin/bash

echo "Checking MongoDB Schema Generator status..."
CONTAINER_STATUS=$(docker compose ps --format json | grep schema-generator)

if [ -z "$CONTAINER_STATUS" ]; then
    echo "Status: Not running"
    exit 1
else
    echo "Status: Running"
    docker compose ps
    exit 0
fi
