#!/usr/bin/env python3
"""
Simple event listener script for development.
This is a placeholder script that would normally handle real-time events.
"""

import time
import logging
from utils.redis_client import get_redis_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    """Main event listener loop."""
    logger.info("Starting event listener...")
    
    try:
        redis_client = get_redis_client('queue')
        logger.info("Connected to Redis for event listening")
        
        # Simple event loop - in production this would subscribe to Redis pub/sub
        while True:
            logger.info("Event listener running... (press Ctrl+C to stop)")
            time.sleep(60)  # Sleep for 60 seconds
            
    except KeyboardInterrupt:
        logger.info("Event listener stopped by user")
    except Exception as e:
        logger.error(f"Event listener error: {e}")

if __name__ == "__main__":
    main()