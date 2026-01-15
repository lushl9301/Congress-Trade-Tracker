"""
Email notification module for Congress Trade Tracker.
Sends alerts and summaries via SMTP.
"""
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from app.config import config
from app.logging import get_logger

logger = get_logger(__name__)


class EmailNotifier:
    """Send email notifications via SMTP."""

    def __init__(self):
        """Initialize email notifier."""
        self.enabled = config.EMAIL_ENABLED
        self.smtp_host = config.SMTP_HOST
        self.smtp_port = config.SMTP_PORT
        self.smtp_user = config.SMTP_USER
        self.smtp_password = config.SMTP_PASSWORD
        self.email_from = config.EMAIL_FROM
        self.email_to = config.EMAIL_TO

    def send_email(self, subject: str, body: str, html: bool = False) -> bool:
        """
        Send an email.

        Args:
            subject: Email subject
            body: Email body (plain text or HTML)
            html: If True, send as HTML email

        Returns:
            True if successful
        """
        if not self.enabled:
            logger.debug(f"Email disabled. Would send: {subject}")
            return False

        if not all(
            [self.smtp_host, self.smtp_user, self.smtp_password, self.email_from, self.email_to]
        ):
            logger.error("Email configuration incomplete")
            return False

        try:
            # Create message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.email_from
            msg["To"] = self.email_to

            # Attach body
            if html:
                msg.attach(MIMEText(body, "html"))
            else:
                msg.attach(MIMEText(body, "plain"))

            # Send via SMTP
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)

            logger.info(f"Email sent: {subject}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False

    def send_daily_summary(self, summary: dict[str, Any]) -> bool:
        """
        Send daily summary email.

        Args:
            summary: Daily summary dictionary

        Returns:
            True if successful
        """
        subject = f"Congress Trade Tracker - Daily Summary {summary.get('date', '')}"

        body = f"""
Congress Trade Tracker Daily Summary
=====================================

Date: {summary.get('date', 'N/A')}

Ingestion:
- New events: {summary.get('ingestion', {}).get('new_events', 0)}
- Duplicates: {summary.get('ingestion', {}).get('duplicates', 0)}

Signals:
- STRONG: {summary.get('signals', {}).get('STRONG', 0)}
- NORMAL: {summary.get('signals', {}).get('NORMAL', 0)}
- WATCH: {summary.get('signals', {}).get('WATCH', 0)}

Trading:
- Orders placed: {summary.get('trading', {}).get('orders_placed', 0)}
- Orders filled: {summary.get('trading', {}).get('orders_filled', 0)}

Portfolio:
- Positions: {summary.get('portfolio', {}).get('num_positions', 0)}
- Total value: ${summary.get('portfolio', {}).get('total_notional', 0):,.2f}
- Exposure: {summary.get('portfolio', {}).get('exposure_pct', 0):.2%}

Errors: {summary.get('errors', [])}

---
Mode: {config.TRADING_MODE.upper()}
Trading enabled: {config.TRADING_ENABLED}
"""

        return self.send_email(subject, body)

    def send_alert(self, alert_type: str, message: str) -> bool:
        """
        Send an alert email.

        Args:
            alert_type: Type of alert (ERROR, WARNING, INFO)
            message: Alert message

        Returns:
            True if successful
        """
        subject = f"Congress Trade Tracker Alert - {alert_type}"
        body = f"{alert_type}: {message}"

        return self.send_email(subject, body)


# Global notifier instance
notifier = EmailNotifier()
