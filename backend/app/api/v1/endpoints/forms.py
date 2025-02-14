from fastapi import APIRouter, HTTPException, Body
from typing import List, Dict, Any
from app.schemas.form import Form, FormSubmission
from app.db.supabase import supabase_client
from uuid import UUID, uuid4
from datetime import datetime
import logging

router = APIRouter()

@router.get("/", response_model=List[Form])
async def get_all_forms():
    try:
        response = supabase_client.table('forms').select("*").execute()
        return response.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{form_id}")
async def get_form(form_id: str):
    try:
        # Validate if form_id is a valid UUID
        try:
            UUID(form_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid form ID format")

        response = supabase_client.table('forms')\
            .select('*')\
            .eq('id', form_id)\
            .single()\
            .execute()
            
        if not response.data:
            raise HTTPException(status_code=404, detail="Form not found")
            
        return response.data
        
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch form: {str(e)}"
        )

@router.post("/{form_id}/submit", response_model=FormSubmission)
async def submit_form(form_id: UUID, form_data: Dict[str, Any] = Body(...)):
    try:
        # Log incoming request data
        print(f"Received form submission - form_id: {form_id}, data: {form_data}")
        
        # First, verify that the form exists
        form_response = supabase_client.table('forms').select("*").eq('id', str(form_id)).single().execute()
        if not form_response.data:
            raise HTTPException(status_code=404, detail="Form not found")
        
        # Create submission data with all required fields
        submission_data = {
            "id": str(uuid4()),
            "form_id": str(form_id),
            "submission_data": form_data,
            "created_at": datetime.utcnow().isoformat()
        }
        
        # Log the response data before returning
        print(f"Returning submission data: {submission_data}")
        return submission_data
        
    except Exception as e:
        print(f"Error in submit_form: {str(e)}")
        print(f"Error type: {type(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to process form submission: {str(e)}"
        ) 

@router.get("/{form_id}/workflows")
async def get_form_workflows(form_id: str):
    try:
        # Get all workflows that have this form as a trigger
        response = supabase_client.table('workflows')\
            .select('*')\
            .execute()
            
        if not response.data:
            return []
            
        # Filter workflows to find ones that use this form
        form_workflows = []
        for workflow in response.data:
            nodes = workflow.get('nodes', [])
            for node in nodes:
                if (node.get('type') == 'form' and 
                    node.get('data', {}).get('id') == form_id and 
                    workflow.get('is_active', False)):  # Only include active workflows
                    form_workflows.append(workflow['id'])
                    break
                
        return form_workflows
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch form workflows: {str(e)}"
        ) 