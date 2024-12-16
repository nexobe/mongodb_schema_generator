#!/bin/bash

# Build and start the container
echo "Starting MongoDB Schema Generator..."
docker compose up --build -d
echo "Application started in background..."

# Create a temporary file for status
STATUSFILE=$(mktemp)
echo "running" > "$STATUSFILE"

# Function to follow logs and check for completion
follow_logs() {
    docker compose logs -f schema-generator | while read -r line; do
        echo "$line"
        
        # Check for completion message
        if echo "$line" | grep -q "ER diagram saved to"; then
            echo "ER diagram saved to" > "$STATUSFILE"
            # Wait a bit to ensure all logs are flushed
            sleep 2
            break
        fi
        
        # Check for critical errors but ignore:
        # - Authorization errors
        # - Warnings
        # - Conversion errors
        # - Collection access errors
        if echo "$line" | grep -q -i "error:" && \
           ! echo "$line" | grep -q "not authorized" && \
           ! echo "$line" | grep -q "Warning" && \
           ! echo "$line" | grep -q "ConversionFailure" && \
           ! echo "$line" | grep -q "Error getting collection fields"; then
            echo "error" > "$STATUSFILE"
            break
        fi
    done
}

# Start following logs in background
follow_logs &
LOGS_PID=$!

# Wait and check status
TIMEOUT=300  # 5 minutes
ELAPSED=0
INTERVAL=5   # Check every 5 seconds

while [ $ELAPSED -lt $TIMEOUT ]; do
    STATUS=$(cat "$STATUSFILE")
    
    if [ "$STATUS" = "ER diagram saved to" ]; then
        echo "Schema generation completed successfully!"
        # Wait to ensure all logs are flushed
        sleep 5
        echo "Stopping containers..."
        kill $LOGS_PID 2>/dev/null
        ./scripts/stop.sh
        rm "$STATUSFILE"
        exit 0
    fi
    
    if [ "$STATUS" = "error" ]; then
        echo "Critical error detected in logs. Stopping containers..."
        # Wait to ensure all logs are flushed
        sleep 5
        kill $LOGS_PID 2>/dev/null
        docker compose logs schema-generator | tail -n 20
        ./scripts/stop.sh
        rm "$STATUSFILE"
        exit 1
    fi
    
    sleep $INTERVAL
    ELAPSED=$((ELAPSED + INTERVAL))
done

# Timeout reached
echo "Timeout reached after ${TIMEOUT} seconds. Stopping containers..."
kill $LOGS_PID 2>/dev/null
docker compose logs schema-generator | tail -n 20
# Wait to ensure all logs are flushed
sleep 5
./scripts/stop.sh
rm "$STATUSFILE"
exit 1
