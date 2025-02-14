from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID

class FormField(BaseModel):
    id: str
    type: str
    label: str
    options: List[Any] = []
    placeholder: Optional[str] = None

class Form(BaseModel):
    id: UUID
    form_name: str
    form_data: List[Dict[str, Any]]  # Using Dict since it's a JSONB field
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    user_id: Optional[int] = None
    form_id: Optional[int] = None

    class Config:
        from_attributes = True

class FormCreate(BaseModel):
    form_name: str
    form_data: List[Dict[str, Any]]
    user_id: Optional[int] = None
    form_id: Optional[int] = None

class FormSubmission(BaseModel):
    id: str
    form_id: str
    submission_data: Dict[str, Any]
    created_at: str

    class Config:
        from_attributes = True