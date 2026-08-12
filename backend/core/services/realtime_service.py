"""Global realtime publish helpers backed by Django Channels.

This service is intentionally app-agnostic so other modules (dashboard,
client messaging, office work, etc.) can share the same event bus.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.utils import timezone

logger = logging.getLogger(__name__)

_TOPIC_SANITIZER = re.compile(r"[^a-zA-Z0-9_.-]+")


def normalize_topic(topic: str) -> str:
    """Normalize topic names into safe, predictable identifiers."""
    raw_topic = str(topic or "").strip().lower()
    if not raw_topic:
        return "global"
    safe = _TOPIC_SANITIZER.sub("_", raw_topic).strip("._-")
    return safe[:80] or "global"


def topic_group_name(topic: str) -> str:
    """Return a channel-layer group name for a topic."""
    return f"rt.topic.{normalize_topic(topic)}"


def _build_group_event(*, topic: str, event_type: str, payload: Any | None) -> dict[str, Any]:
    return {
        "type": "realtime.event",
        "topic": normalize_topic(topic),
        "event_type": str(event_type or "realtime.message").strip() or "realtime.message",
        "payload": payload if payload is not None else {},
        "sent_at": timezone.now().isoformat(),
    }


async def apublish_topic_event(*, topic: str, event_type: str, payload: Any | None = None) -> bool:
    """Async publisher used from async consumers/tasks."""
    channel_layer = get_channel_layer()
    if channel_layer is None:
        logger.warning("Realtime channel layer unavailable; dropped async event '%s'.", event_type)
        return False

    await channel_layer.group_send(
        topic_group_name(topic),
        _build_group_event(topic=topic, event_type=event_type, payload=payload),
    )
    return True


def publish_topic_event(*, topic: str, event_type: str, payload: Any | None = None) -> bool:
    """Sync publisher used from normal Django views/services."""
    channel_layer = get_channel_layer()
    if channel_layer is None:
        logger.warning("Realtime channel layer unavailable; dropped event '%s'.", event_type)
        return False

    async_to_sync(channel_layer.group_send)(
        topic_group_name(topic),
        _build_group_event(topic=topic, event_type=event_type, payload=payload),
    )
    return True
