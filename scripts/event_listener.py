#!/usr/bin/env python3
"""
Entrypoint for the Redis event listeners used by docker-compose.

This delegates to the real consumer implementation in workers.event_listener
so the container starts the actual pub/sub loop.
"""

import logging

from workers.event_listener import start_consumers


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    """Start the real event consumer loop."""
    logger.info("Starting event listener consumers...")
    start_consumers()


if __name__ == "__main__":
    main()
