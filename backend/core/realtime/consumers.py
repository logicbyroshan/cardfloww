from __future__ import annotations

import time
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.core.exceptions import PermissionDenied

from core.services.permission_service import PermissionService
from core.services.realtime_service import normalize_topic, topic_group_name


class RealtimeHubConsumer(AsyncJsonWebsocketConsumer):
    """Global websocket hub for reusable topic-based realtime events."""

    MAX_TOPICS_PER_CLIENT = 20
    MAX_TOPICS_PER_PACKET = 50
    PACKET_RATE_LIMIT_COUNT = 80
    PACKET_RATE_LIMIT_WINDOW_SECONDS = 30
    CHAT_SEND_RATE_LIMIT_COUNT = 30
    CHAT_SEND_RATE_LIMIT_WINDOW_SECONDS = 30

    async def connect(self):
        user = self.scope.get('user')
        if not user or not user.is_authenticated:
            await self.close(code=4401)
            return

        self._subscribed_topics = set()
        self._packet_window_started_at = time.monotonic()
        self._packet_window_count = 0
        self._chat_send_window_started_at = time.monotonic()
        self._chat_send_window_count = 0
        await self.accept()

        query_topics = self._topics_from_query_string()
        bootstrap_topics = await self._bootstrap_topics_for_user()
        requested_topics = self._normalize_topics(list(query_topics) + list(bootstrap_topics))
        if requested_topics:
            subscribed = await self._subscribe_topics(requested_topics)
        else:
            subscribed = []

        await self.send_json({
            'type': 'realtime.ready',
            'subscribed_topics': subscribed,
        })

    async def _bootstrap_topics_for_user(self):
        user = self.scope.get('user')
        return await database_sync_to_async(self._bootstrap_topics_for_user_sync)(user)

    @staticmethod
    def _bootstrap_topics_for_user_sync(user):
        if not user or not user.is_authenticated:
            return []

        topics = []
        # Add any default bootstrap topics here
        return topics

    async def disconnect(self, close_code):
        for topic in list(getattr(self, '_subscribed_topics', set())):
            await self.channel_layer.group_discard(topic_group_name(topic), self.channel_name)

    async def receive_json(self, content, **kwargs):
        if not self._allow_in_window(
            started_at_attr='_packet_window_started_at',
            count_attr='_packet_window_count',
            limit=self.PACKET_RATE_LIMIT_COUNT,
            window_seconds=self.PACKET_RATE_LIMIT_WINDOW_SECONDS,
        ):
            await self.send_json({'type': 'realtime.error', 'message': 'Too many realtime packets. Slow down.'})
            return

        packet_type = str((content or {}).get('type') or '').strip().lower()

        if packet_type == 'ping':
            await self.send_json({'type': 'pong'})
            return

        if packet_type == 'realtime.subscribe':
            topics = self._topics_from_message(content)
            subscribed = await self._subscribe_topics(topics)
            await self.send_json({'type': 'realtime.subscribed', 'topics': subscribed})
            return

        if packet_type == 'realtime.unsubscribe':
            topics = self._topics_from_message(content)
            unsubscribed = await self._unsubscribe_topics(topics)
            await self.send_json({'type': 'realtime.unsubscribed', 'topics': unsubscribed})
            return

        await self.send_json({'type': 'realtime.error', 'message': 'Unsupported realtime packet type.'})

    async def realtime_event(self, event):
        await self.send_json({
            'type': 'realtime.event',
            'topic': event.get('topic') or 'global',
            'event': event.get('event_type') or 'realtime.message',
            'payload': event.get('payload') or {},
            'sent_at': event.get('sent_at'),
        })

    async def _subscribe_topics(self, topics):
        subscribed = []
        for topic in topics:
            if len(self._subscribed_topics) >= self.MAX_TOPICS_PER_CLIENT:
                break
            if topic in self._subscribed_topics:
                subscribed.append(topic)
                continue
            if not await self._can_access_topic(topic):
                continue
            await self.channel_layer.group_add(topic_group_name(topic), self.channel_name)
            self._subscribed_topics.add(topic)
            subscribed.append(topic)
        return subscribed

    async def _unsubscribe_topics(self, topics):
        removed = []
        for topic in topics:
            if topic not in self._subscribed_topics:
                continue
            await self.channel_layer.group_discard(topic_group_name(topic), self.channel_name)
            self._subscribed_topics.discard(topic)
            removed.append(topic)
        return removed

    async def _can_access_topic(self, topic: str) -> bool:
        return await database_sync_to_async(self._can_access_topic_sync)(self.scope.get('user'), topic)

    @staticmethod
    def _can_access_topic_sync(user, topic: str) -> bool:
        normalized = normalize_topic(topic)

        if normalized in {'dashboard.live', 'dashboard.working', 'dashboard.assignments'}:
            return PermissionService.is_any_admin(user)
        if normalized == 'client.messaging':
            return bool(user and user.is_authenticated)
        return bool(user and user.is_authenticated)

    def _topics_from_query_string(self):
        query_string = (self.scope.get('query_string') or b'').decode('utf-8', errors='ignore')
        params = parse_qs(query_string)
        raw_topics = params.get('topics', [''])
        return self._normalize_topics(raw_topics[0].split(','))

    def _topics_from_message(self, content):
        raw_topics = (content or {}).get('topics') or []
        if isinstance(raw_topics, str):
            raw_topics = raw_topics.split(',')
        if not isinstance(raw_topics, (list, tuple, set)):
            return []
        return self._normalize_topics(list(raw_topics)[: self.MAX_TOPICS_PER_PACKET])

    def _allow_in_window(self, *, started_at_attr: str, count_attr: str, limit: int, window_seconds: int) -> bool:
        now = time.monotonic()
        started_at = float(getattr(self, started_at_attr, now) or now)
        count = int(getattr(self, count_attr, 0) or 0)

        if (now - started_at) >= float(window_seconds):
            setattr(self, started_at_attr, now)
            setattr(self, count_attr, 1)
            return True

        count += 1
        setattr(self, count_attr, count)
        return count <= int(limit)

    @staticmethod
    def _normalize_topics(values):
        topics = []
        seen = set()
        for raw in values:
            topic = normalize_topic(str(raw or '').strip())
            if not topic or topic in seen:
                continue
            seen.add(topic)
            topics.append(topic)
        return topics
