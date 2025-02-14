from pydantic import BaseModel, HttpUrl

class SlackMessage(BaseModel):
    webhook_url: HttpUrl
    channel: str
    message: str 
