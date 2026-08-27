#!/bin/sh
# Apply pending schema migrations before the real process starts (D-083). Idempotent and
# concurrency-safe (advisory lock + checksum guard in acde.migrations), so this is safe to run on
# every container start, including every replica in a multi-instance deployment.
set -e
acde migrate
exec "$@"
