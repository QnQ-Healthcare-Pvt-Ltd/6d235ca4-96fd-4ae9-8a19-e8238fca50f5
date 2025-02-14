from pydantic import BaseModel, UUID4
from typing import List, Dict, Any, Optional
from datetime import datetime
from enum import Enum

class ExecutionStatus(str, Enum):
    PENDING = 'pending'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'

class WorkflowCreate(BaseModel):
    name: str
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]
    is_active: bool = True

class WorkflowResponse(BaseModel):
    id: str
    name: str
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]
    is_active: bool
    version: int
    created_at: datetime
    updated_at: datetime

class WorkflowExecution(BaseModel):
    id: str
    workflow_id: str
    workflow_version: int
    status: ExecutionStatus
    started_at: datetime
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    trigger_type: str
    trigger_data: Dict[str, Any]

class NodeExecution(BaseModel):
    id: str
    workflow_execution_id: str
    node_id: str
    status: ExecutionStatus
    started_at: datetime
    completed_at: Optional[datetime] = None
    input_data: Optional[Dict[str, Any]] = None
    output_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None

class ActionConfig(BaseModel):
    workflow_id: str
    node_id: str
    action_type: str
    config: Dict[str, Any] 