#!/bin/bash

# Parse command line arguments
TAIL_LINES="100"
FOLLOW=false
TAIL_FILE=false

function show_help() {
    echo "Usage: $0 [options]"
    echo "Options:"
    echo "  -n, --lines NUMBER    Show last NUMBER lines (default: 100)"
    echo "  -f, --follow         Follow the logs in real-time"
    echo "  -t, --tail           Tail the logs using system tail command"
    echo "  -h, --help           Show this help message"
}

while [[ $# -gt 0 ]]; do
    case $1 in
        -n|--lines)
            TAIL_LINES="$2"
            shift 2
            ;;
        -f|--follow)
            FOLLOW=true
            shift
            ;;
        -t|--tail)
            TAIL_FILE=true
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

echo "Showing last $TAIL_LINES lines of logs..."

if [ "$TAIL_FILE" = true ]; then
    # Get the container ID
    CONTAINER_ID=$(docker compose ps -q schema-generator)
    if [ -z "$CONTAINER_ID" ]; then
        echo "Container not found"
        exit 1
    fi

    # Get the log file path
    LOG_FILE=$(docker inspect --format='{{.LogPath}}' "$CONTAINER_ID")
    if [ -z "$LOG_FILE" ]; then
        echo "Log file not found"
        exit 1
    fi

    echo "Tailing log file: $LOG_FILE"
    if [ "$FOLLOW" = true ]; then
        sudo tail -n "$TAIL_LINES" -f "$LOG_FILE"
    else
        sudo tail -n "$TAIL_LINES" "$LOG_FILE"
    fi
else
    if [ "$FOLLOW" = true ]; then
        echo "Following logs (Ctrl+C to stop)..."
        docker compose logs --tail="$TAIL_LINES" -f
    else
        docker compose logs --tail="$TAIL_LINES"
    fi
fi
