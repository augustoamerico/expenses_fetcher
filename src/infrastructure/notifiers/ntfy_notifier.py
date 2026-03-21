import logging
from typing import List, Optional

import requests

log = logging.getLogger(__name__)


class NtfyNotifier:
    """
    Simple ntfy.sh notification client.

    ntfy.sh is a simple pub-sub notification service. This client sends
    push notifications that can be received on mobile devices.

    Usage:
        notifier = NtfyNotifier(topic="my-expenses")
        notifier.send(
            title="Sync complete",
            message="3 accounts processed",
            priority="default",
            tags=["white_check_mark"]
        )
    """

    def __init__(
        self,
        topic: str,
        server: str = "https://ntfy.sh",
        timeout: int = 10,
    ):
        """
        Initialize the ntfy notifier.

        Args:
            topic: The ntfy topic to publish to (e.g., "my-expenses-fetcher")
            server: The ntfy server URL (defaults to public ntfy.sh)
            timeout: Request timeout in seconds (default 10)
        """
        self.topic = topic
        self.server = server.rstrip("/")
        self.timeout = timeout

    def send(
        self,
        title: str,
        message: str,
        priority: str = "default",
        tags: Optional[List[str]] = None,
    ) -> bool:
        """
        Send a notification via ntfy.

        Args:
            title: Notification title
            message: Notification body
            priority: One of "min", "low", "default", "high", "urgent"
            tags: List of emoji tags (e.g., ["warning", "rotating_light"])

        Returns:
            True if notification was sent successfully, False otherwise
        """
        url = f"{self.server}/{self.topic}"
        headers = {
            "Title": title,
            "Priority": priority,
        }
        if tags:
            headers["Tags"] = ",".join(tags)

        try:
            response = requests.post(
                url,
                data=message.encode("utf-8"),
                headers=headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
            log.info(f"Sent ntfy notification: {title}")
            return True
        except requests.RequestException as e:
            log.warning(f"Failed to send ntfy notification: {e}")
            # Don't raise - notification failure shouldn't stop the job
            return False
