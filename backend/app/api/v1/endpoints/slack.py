from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
from app.schemas.slack import SlackMessage
from app.services.slack_service import SlackService
from app.api import deps

router = APIRouter()

@router.post("/send")
async def send_slack_message(
    message: SlackMessage,
    current_user_id: Optional[str] = Depends(deps.get_current_user_id)
) -> dict:
    slack_service = SlackService()
    result = await slack_service.send_message(
        webhook_url=message.webhook_url,
        channel=message.channel,
        message=message.message,
        user_id=current_user_id
    )
    
    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["message"])
        
    return result 