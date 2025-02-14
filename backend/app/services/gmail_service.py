from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
from typing import Dict, Any
import logging
from app.core.config import settings
from pydantic import EmailStr

logger = logging.getLogger(__name__)

class GmailService:
    def __init__(self):
        self.fastmail = None

    async def send_email(self, config: Dict[str, Any], form_data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            # Create a new connection config for each email using the provided config
            mail_conf = ConnectionConfig(
                MAIL_USERNAME=config.get('username'),
                MAIL_PASSWORD=config.get('password'),
                MAIL_FROM=config.get('username'),  # Use username as from address
                MAIL_PORT=int(config.get('port', 587)),
                MAIL_SERVER=config.get('host'),
                MAIL_STARTTLS=True,
                MAIL_SSL_TLS=False,
                USE_CREDENTIALS=True
            )

            # Create a new FastMail instance with the provided config
            fastmail = FastMail(mail_conf)

            # Process template variables in email content
            to_email = self._process_template(config.get("to", ""), form_data)
            subject = self._process_template(config.get("subject", "Workflow Notification"), form_data)
            body = self._process_template(config.get("content", ""), form_data)

            logger.info(f"Sending email to: {to_email}")
            logger.info(f"Subject: {subject}")
            logger.info(f"Body: {body}")

            if not to_email or "@" not in to_email:
                raise ValueError(f"Invalid recipient email address: {to_email}")

            # Create message
            message = MessageSchema(
                subject=subject,
                recipients=[to_email],
                body=body,
                subtype="plain"
            )

            # Send email
            await fastmail.send_message(message)

            return {
                "status": "success",
                "message": "Email sent successfully",
                "details": {
                    "to": to_email,
                    "subject": subject,
                    "body": body
                }
            }

        except Exception as e:
            logger.error(f"Failed to send email: {str(e)}")
            return {
                "status": "error",
                "message": f"Failed to send email: {str(e)}"
            }

    def _process_template(self, template: str, data: Dict[str, Any]) -> str:
        """Replace {{field}} placeholders with actual values from form data"""
        if not template:
            return ""
            
        result = template
        for key, value in data.items():
            placeholder = f"{{{{{key}}}}}"
            if placeholder in result:
                result = result.replace(placeholder, str(value))
        return result