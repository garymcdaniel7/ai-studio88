"""Notification service package.

Provides:
    - NotificationService: create, read, list, count notifications
    - NotificationChannel Protocol: adapter interface for delivery channels
    - InAppChannel: canonical in-app delivery (writes to notifications table)
    - Router: API endpoints for notification CRUD

Validates: Requirements R101.1, R101.2, R101.3
"""

from backend.notifications.notification_schemas import (
    NotificationCategory,
    NotificationCountResponse,
    NotificationListResponse,
    NotificationResponse,
)
from backend.notifications.notification_service import (
    InAppChannel,
    NotificationChannel,
    NotificationService,
)

__all__ = [
    "InAppChannel",
    "NotificationCategory",
    "NotificationChannel",
    "NotificationCountResponse",
    "NotificationListResponse",
    "NotificationResponse",
    "NotificationService",
]
