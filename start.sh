#!/bin/sh
set -e

# Default to daily at midnight if SCHEDULE is not set
SCHEDULE="${SCHEDULE:-0 0 * * *}"

echo "Setting up cron job with schedule: $SCHEDULE"
echo "$SCHEDULE docker-image-cleanup $TARGET_REPOS" > Cronfile

# Run tasker with the generated Cronfile
exec tasker -file Cronfile
