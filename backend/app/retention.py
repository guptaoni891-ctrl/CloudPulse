"""Run retention hourly without exposing a scheduler endpoint to the network."""

import json
import logging
import time

from .db import SessionLocal
from .main import retention

log = logging.getLogger("cloudpulse-retention")


def main():
    while True:
        try:
            with SessionLocal() as db:
                log.info(json.dumps({"event": "retention", **retention(db)}))
        except Exception as exc:
            log.error(json.dumps({"event": "retention_failed", "error_type": type(exc).__name__}))
        time.sleep(3600)


if __name__ == "__main__":
    main()
