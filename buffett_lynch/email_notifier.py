"""Email notification helper."""
from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Iterable

from .config import EmailConfig
from .models import EmailPayload


class EmailNotifier:
    def __init__(self, config: EmailConfig):
        self.config = config

    def send(self, payload: EmailPayload) -> None:
        msg = EmailMessage()
        msg["Subject"] = payload.subject
        msg["From"] = self.config.sender
        msg["To"] = ",".join(self.config.recipients)
        msg.set_content(payload.body)
        with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port) as client:
            if self.config.username and self.config.password:
                client.login(self.config.username, self.config.password)
            client.send_message(msg)


__all__ = ["EmailNotifier"]

