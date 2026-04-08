"""Dramatiq broker factory and middleware.

Call setup_broker() BEFORE importing queue.tasks so that the @dramatiq.actor
decorator registers actors with the correct broker instance.
"""

from __future__ import annotations

import logging
from typing import Any

import dramatiq
import orjson
import redis as sync_redis
from dramatiq.brokers.redis import RedisBroker
from dramatiq.middleware import AsyncIO, Retries, TimeLimit

logger = logging.getLogger(__name__)

DEAD_LETTER_STREAM = "langrove:tasks:dead"


class DeadLetterMiddleware(dramatiq.Middleware):
    """Writes messages to the dead-letter stream after all retries are exhausted.

    Runs *after* Dramatiq's built-in Retries middleware (middleware are called
    in registration order for both before_* and after_* hooks). When Retries
    decides to discard a message (current_retries >= actor.max_retries), this
    middleware records the payload in the Redis Stream that the /dead-letter
    API endpoint reads from.
    """

    def __init__(self, redis_url: str) -> None:
        self._redis = sync_redis.from_url(redis_url, decode_responses=True)

    def after_process_message(
        self,
        broker: Any,
        message: Any,
        *,
        result: Any = None,
        exception: Any = None,
    ) -> None:
        if exception is None:
            return  # Success — nothing to do.

        try:
            actor = broker.get_actor(message.actor_name)
            max_retries: int = actor.options.get("max_retries", 20)
            current_retries: int = message.options.get("retries", 0)
            if current_retries >= max_retries:
                run_id = message.kwargs.get("run_id", "<unknown>")
                self._redis.xadd(
                    DEAD_LETTER_STREAM,
                    {"payload": orjson.dumps(message.kwargs).decode()},
                )
                logger.error(
                    "Run dead-lettered run_id=%s (exceeded %d retries)", run_id, max_retries
                )
        except Exception:
            logger.exception("DeadLetterMiddleware: error recording dead-letter message")


def setup_broker(
    redis_url: str,
    *,
    max_delivery_attempts: int = 3,
    task_timeout_ms: int = 900_000,
) -> RedisBroker:
    """Create and register the global Dramatiq broker.

    Must be called before importing ``langrove.queue.tasks`` so that the
    ``@dramatiq.actor`` decorator attaches to the correct broker.

    Returns the configured broker instance.
    """
    broker = RedisBroker(url=redis_url)

    # Middleware order matters: Retries runs first, then DeadLetterMiddleware,
    # so dead-lettering only happens after Retries has given up.
    broker.add_middleware(AsyncIO())
    broker.add_middleware(TimeLimit(time_limit=task_timeout_ms))
    broker.add_middleware(Retries(max_retries=max_delivery_attempts))
    broker.add_middleware(DeadLetterMiddleware(redis_url))

    dramatiq.set_broker(broker)
    logger.info("Dramatiq broker configured (redis=%s)", redis_url)
    return broker
