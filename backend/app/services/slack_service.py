from typing import Optional
import httpx
from app.core.config import settings

class SlackService:
    async def send_message(
        self,
        webhook_url: str,
        channel: str,
        message: str,
        user_id: Optional[str] = None
    ) -> dict:
        """
        Send a message to a Slack channel using webhook URL
        """
        try:
            payload = {
                "channel": channel,
                "text": message,
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(webhook_url, json=payload)
                response.raise_for_status()
                
            return {"status": "success", "message": "Slack message sent successfully"}
            
        except httpx.HTTPError as e:
            return {"status": "error", "message": f"Failed to send Slack message: {str(e)}"} 