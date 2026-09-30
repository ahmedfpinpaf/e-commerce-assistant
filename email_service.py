import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any, Optional

import tracker_db

logger = logging.getLogger("email_service")

class EmailAlertService:
    def __init__(self):
        self.smtp_host = os.getenv("SMTP_HOST", "")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER", "")
        self.smtp_pass = os.getenv("SMTP_PASSWORD", "")
        self.smtp_from = os.getenv("SMTP_FROM", "alerts@shopai-assistant.com")

    def send_price_drop_alert(
        self,
        product_id: str,
        product_name: str,
        product_url: str,
        current_price: float,
        previous_price: float,
        currency: str = "PKR",
        target_price: Optional[float] = None,
        recipient_email: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Sends price-drop email notification compliant with Section 8 specification.
        Subject: Price Drop Alert — [Product Name]
        Body:
        The price of [Product Name] has dropped.

        Previous Price: [Currency] [Previous Price]
        Current Price: [Currency] [Current Price]

        You can view the product here:

        [Product URL]
        """
        # Determine recipient email
        if not recipient_email:
            settings = tracker_db.get_user_settings()
            recipient_email = settings.get("alert_email", "user@example.com")

        subject = f"Price Drop Alert — {product_name}"
        
        curr_str = f"{currency} {current_price:,.0f}" if current_price.is_integer() else f"{currency} {current_price:,.2f}"
        prev_str = f"{currency} {previous_price:,.0f}" if previous_price.is_integer() else f"{currency} {previous_price:,.2f}"
        
        body_text = (
            f"The price of {product_name} has dropped.\n\n"
            f"Previous Price: {prev_str}\n"
            f"Current Price: {curr_str}\n\n"
            f"You can view the product here:\n\n"
            f"{product_url}\n"
        )
        
        if target_price:
            targ_str = f"{currency} {target_price:,.0f}" if target_price.is_integer() else f"{currency} {target_price:,.2f}"
            body_text += f"\nYour target price was {targ_str}.\n"

        sent_via = "logged"
        error_msg = None

        # Attempt real SMTP if configured
        if self.smtp_host and self.smtp_user and self.smtp_pass:
            try:
                msg = MIMEMultipart("alternative")
                msg["Subject"] = subject
                msg["From"] = self.smtp_from
                msg["To"] = recipient_email
                msg.attach(MIMEText(body_text, "plain"))
                
                with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10) as server:
                    server.starttls()
                    server.login(self.smtp_user, self.smtp_pass)
                    server.sendmail(self.smtp_from, [recipient_email], msg.as_string())
                sent_via = "smtp"
                logger.info(f"Price drop email successfully sent to {recipient_email} via SMTP")
            except Exception as e:
                logger.warning(f"SMTP send failed: {e}. Falling back to internal alert log.")
                error_msg = str(e)
                sent_via = "failed_smtp_logged"

        # Record alert in DB
        tracker_db.record_alert_sent(
            prod_id=product_id,
            price=current_price,
            alert_type="price_drop" if not target_price or current_price > target_price else "target_reached",
            recipient_email=recipient_email,
            subject=subject,
            body=body_text
        )

        return {
            "success": True,
            "mode": sent_via,
            "recipient": recipient_email,
            "subject": subject,
            "body": body_text,
            "error": error_msg
        }

email_service = EmailAlertService()
