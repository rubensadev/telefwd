#!/bin/sh
set -e

# If APP_UID and APP_GID are provided, modify appuser
if [ -n "$APP_UID" ] && [ -n "$APP_GID" ]; then
    # Change group ID
    if [ "$(getent group appgroup | cut -d: -f3)" != "$APP_GID" ]; then
        delgroup appgroup
        addgroup -g "$APP_GID" appgroup
    fi

    # Change user ID
    if [ "$(id -u appuser)" != "$APP_UID" ]; then
        deluser appuser
        adduser -u "$APP_UID" -G appgroup -S appuser
    fi
fi

exec "$@"
