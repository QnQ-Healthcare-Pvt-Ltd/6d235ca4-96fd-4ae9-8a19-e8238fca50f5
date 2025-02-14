from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime

class RuleBase(BaseModel):
    name: str
    description: Optional[str] = None
    prompt: str
    generated_code: Dict[str, Any]
    python_code: Dict[str, Any]
    field_id: str
    form_id: str

class RuleCreate(RuleBase):
    pass

class Rule(RuleBase):
    id: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True 