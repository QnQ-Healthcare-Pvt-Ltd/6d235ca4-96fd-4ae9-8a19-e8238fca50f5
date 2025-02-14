from fastapi import APIRouter, HTTPException, Body
from typing import Dict, Any, List
from pydantic import BaseModel
from datetime import datetime
from uuid import uuid4
from app.db.supabase import supabase_client
from app.services.workflow_executor import WorkflowExecutor
from app.schemas.workflow import WorkflowCreate, WorkflowResponse, WorkflowExecution, ActionConfig, ExecutionStatus
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    force=True
)
logger = logging.getLogger(__name__)

router = APIRouter()

class WorkflowCreate(BaseModel):
    name: str
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]
    is_active: bool = True  # Default to active

class WorkflowResponse(BaseModel):
    id: str
    name: str
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]
    is_active: bool
    created_at: datetime
    updated_at: datetime

@router.post("/", response_model=WorkflowResponse)
async def create_workflow(workflow: WorkflowCreate):
    try:
        # Extract form ID from the nodes
        form_node = next(
            (node for node in workflow.nodes if node.get('type') == 'form'),
            None
        )
        if not form_node:
            raise HTTPException(status_code=400, detail="Workflow must contain a form node")
        
        # Update this part to correctly access the form ID
        form_id = form_node.get('data', {}).get('form', {}).get('id') or form_node.get('data', {}).get('id')
        if not form_id:
            raise HTTPException(status_code=400, detail="Form ID not found in form node")

        # Get existing form data
        form_response = supabase_client.table('forms')\
            .select('*')\
            .eq('id', form_id)\
            .single()\
            .execute()
        
        if not form_response.data:
            raise HTTPException(status_code=404, detail="Form not found")

        form_data = form_response.data
        existing_fields = form_data.get('form_data', [])

        # Find all Math Function nodes and their output variables
        math_nodes = [
            node for node in workflow.nodes 
            if node.get('type') == 'action' and 
            node.get('data', {}).get('app', {}).get('id') == 'math'
        ]

        # Collect output variables from math nodes
        new_fields = []
        existing_field_labels = {field['label'] for field in existing_fields}

        for math_node in math_nodes:
            math_config = math_node.get('data', {}).get('config', {}).get('mathConfig', {})
            output_variable = math_config.get('outputVariable')
            
            if output_variable and output_variable not in existing_field_labels:
                new_fields.append({
                    "id": f"field-{len(existing_fields) + len(new_fields) + 1}",
                    "type": "hidden",
                    "label": output_variable,
                    "caption": "Math Function Output",
                    "options": [],
                    "required": False,
                    "placeholder": ""
                })

        # Only update if we have new fields to add
        if new_fields:
            updated_form_data = {
                **form_data,
                'form_data': [*existing_fields, *new_fields],
                'updated_at': datetime.utcnow().isoformat()
            }

            # Update the form with new fields
            update_response = supabase_client.table('forms')\
                .update(updated_form_data)\
                .eq('id', form_id)\
                .execute()

            if not update_response.data:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to update form with math output fields"
                )

        # Create the workflow with proper data structure
        workflow_data = {
            "id": str(uuid4()),
            "name": workflow.name,
            "nodes": workflow.nodes,
            "edges": workflow.edges,
            "is_active": workflow.is_active,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }

        response = supabase_client.table('workflows')\
            .insert(workflow_data)\
            .execute()

        if not response.data:
            raise HTTPException(status_code=500, detail="Failed to create workflow")

        return response.data[0]

    except Exception as e:
        print(f"Error creating workflow: {str(e)}")  # Add logging
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/", response_model=List[WorkflowResponse])
async def get_workflows():
    try:
        response = supabase_client.table('workflows').select("*").order('created_at.desc').execute()
        
        if not response.data:
            return []
            
        return response.data
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch workflows: {str(e)}"
        )

@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(workflow_id: str):
    try:
        response = supabase_client.table('workflows').select("*").eq('id', workflow_id).single().execute()
        
        if not response.data:
            raise HTTPException(status_code=404, detail="Workflow not found")
            
        return response.data
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch workflow: {str(e)}"
        )

@router.put("/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow(workflow_id: str, workflow: WorkflowCreate):
    try:
        workflow_data = {
            "name": workflow.name,
            "nodes": workflow.nodes,
            "edges": workflow.edges,
            "updated_at": datetime.utcnow().isoformat()
        }
        
        response = supabase_client.table('workflows').update(workflow_data).eq('id', workflow_id).execute()
        
        if not response.data:
            raise HTTPException(status_code=404, detail="Workflow not found")
            
        return response.data[0]
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update workflow: {str(e)}"
        )

@router.patch("/{workflow_id}/toggle", response_model=WorkflowResponse)
async def toggle_workflow_status(workflow_id: str):
    try:
        # First get the current status
        current = supabase_client.table('workflows').select("is_active").eq('id', workflow_id).single().execute()
        if not current.data:
            raise HTTPException(status_code=404, detail="Workflow not found")
            
        # Toggle the status
        new_status = not current.data['is_active']
        response = supabase_client.table('workflows').update({
            "is_active": new_status,
            "updated_at": datetime.utcnow().isoformat()
        }).eq('id', workflow_id).execute()
        
        if not response.data:
            raise HTTPException(status_code=404, detail="Workflow not found")
            
        return response.data[0]
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to toggle workflow status: {str(e)}"
        )

@router.post("/{workflow_id}/execute")
async def execute_workflow(workflow_id: str, trigger_data: Dict[str, Any]):
    try:
        logger.info(f"\n=== Starting Workflow Execution API ===")
        logger.info(f"Workflow ID: {workflow_id}")
        logger.info(f"Trigger Data: {trigger_data}")

        # Get workflow - remove await since supabase_client is synchronous
        workflow_response = supabase_client.table("workflows")\
            .select("*")\
            .eq("id", workflow_id)\
            .single()\
            .execute()
            
        if not workflow_response.data:
            raise HTTPException(status_code=404, detail="Workflow not found")
            
        workflow = workflow_response.data
        
        # Check if workflow is active
        if not workflow.get('is_active', False):
            logger.warning(f"Workflow {workflow_id} is inactive")
            raise HTTPException(
                status_code=400,
                detail="Cannot execute inactive workflow. Please activate the workflow first."
            )

        # Create workflow execution record - remove await
        execution_data = {
            "id": str(uuid4()),
            "workflow_id": workflow_id,
            "workflow_version": workflow.get("version", 1),
            "status": ExecutionStatus.PENDING,
            "trigger_type": "form_submission",
            "trigger_data": trigger_data,
            "started_at": datetime.utcnow().isoformat()
        }

        logger.info("Creating workflow execution record")
        execution_response = supabase_client.table("workflow_executions")\
            .insert(execution_data)\
            .execute()

        if not execution_response.data:
            raise HTTPException(status_code=500, detail="Failed to create workflow execution")

        # Execute workflow
        executor = WorkflowExecutor(execution_response.data[0])
        logger.info("Starting workflow execution")
        
        result = await executor.execute_workflow(
            nodes=workflow["nodes"],
            edges=workflow["edges"],
            trigger_data=trigger_data
        )
        
        logger.info(f"Workflow execution completed: {result}")
        return result

    except Exception as e:
        logger.error(f"Workflow execution failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{workflow_id}/executions", response_model=List[WorkflowExecution])
async def get_workflow_executions(workflow_id: str):
    try:
        response = supabase_client.table('workflow_executions')\
            .select('*')\
            .eq('workflow_id', workflow_id)\
            .order('started_at', desc=True)\
            .execute()
            
        return response.data
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch workflow executions: {str(e)}"
        )

async def start_workflow_execution(execution_data: Dict[str, Any]):
    executor = WorkflowExecutor(execution_data)
    await executor.start()

@router.post("/{workflow_id}/action-config", response_model=ActionConfig)
async def create_action_config(
    workflow_id: str,
    node_id: str,
    action_type: str,
    config: Dict[str, Any]
):
    try:
        action_config_data = {
            "workflow_id": workflow_id,
            "node_id": node_id,
            "action_type": action_type,
            "config": config
        }
        
        # First try to update existing config
        response = supabase_client.table('action_configurations')\
            .upsert(action_config_data)\
            .execute()
            
        if not response.data:
            raise HTTPException(status_code=500, detail="Failed to create/update action configuration")
            
        return response.data[0]
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create/update action configuration: {str(e)}"
        )

@router.delete("/{workflow_id}")
async def delete_workflow(workflow_id: str):
    try:
        # First check if workflow exists
        workflow = supabase_client.table('workflows')\
            .select('*')\
            .eq('id', workflow_id)\
            .single()\
            .execute()
            
        if not workflow.data:
            raise HTTPException(status_code=404, detail="Workflow not found")
            
        # Delete workflow
        response = supabase_client.table('workflows')\
            .delete()\
            .eq('id', workflow_id)\
            .execute()
            
        return {"message": "Workflow deleted successfully"}
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete workflow: {str(e)}"
        )