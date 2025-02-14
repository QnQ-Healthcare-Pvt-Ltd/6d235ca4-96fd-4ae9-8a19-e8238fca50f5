from fastapi import APIRouter, HTTPException, Body
from typing import List, Dict, Any, Optional
from app.schemas.rule import Rule, RuleCreate
from app.db.supabase import supabase_client
from pydantic import BaseModel
import openai
from datetime import datetime
import logging
from app.core.config import settings


router = APIRouter()
logger = logging.getLogger(__name__)
openai.api_key = settings.OPENAI_API_KEY


class PromptRequest(BaseModel):
    prompt: str
    fieldId: str
    formId: str

@router.post("/generate", response_model=Dict[str, Any])
async def generate_rule(request: PromptRequest):
    try:
        client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
        
        # Get specific form by ID
        form_response = supabase_client.table("forms")\
            .select("form_data")\
            .eq("id", request.formId)\
            .execute()

        if not form_response.data:
            raise HTTPException(status_code=404, detail="Form not found")
            
        form_data = form_response.data[0]["form_data"]
        field = next((f for f in form_data if f["id"] == request.fieldId), None)
        
        if not field:
            raise HTTPException(status_code=404, detail="Field not found")
            
        field_type = field["type"]
        print("field_type:", field_type)

        field_type = field["type"] if field else "text"
        
        # Customize system message based on field type
        if field_type in ['checkbox', 'multiple-choice']:
            system_message = (
                "You are a form validation expert. Generate a JavaScript validation function that validates "
                f"{'multiple selections' if field_type == 'checkbox' else 'single selection'} for a {field_type} field. "
                "The function should follow this format:\n"
                "```javascript\n"
                "function validateField(value) {\n"
                "    // For checkbox, value will be comma-separated string of selections\n"
                "    // For radio/multiple-choice, value will be a single selection\n"
                "    // Return true if valid, false if invalid\n"
                "}\n"
                "```\n"
                "Return only the code without explanations."
            )
        else:
            system_message = (
                "You are a form validation expert. Generate a JavaScript validation function "
                "that validates user input. The function should follow this format:\n"
                "```javascript\n"
                "function validateField(value) {\n"
                "    // Validation logic here\n"
                "    // Return true if valid, false if invalid\n"
                "}\n"
                "```\n"
                "Return only the code without explanations."
            )

        # Log OpenAI request
        js_response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": request.prompt}
            ]
        )

        py_response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": "You are a Python validation expert. Generate Python validation code based on the prompt."
                },
                {"role": "user", "content": request.prompt}
            ]
        )

        # Extract and clean generated code
        generated_code = js_response.choices[0].message.content.strip()
        python_code = py_response.choices[0].message.content.strip()
        
        rule_data = {
            "name": f"Rule {datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "description": f"Generated rule for prompt: {request.prompt}",
            "prompt": request.prompt,
            "generated_code": generated_code,
            "python_code": python_code,
            "field_id": request.fieldId,
            "form_id": request.formId,
            "created_at": datetime.now().isoformat(),
        }

        response = supabase_client.table("rules").insert(rule_data).execute()

        if response.data:
            saved_rule = response.data[0]
            return {"message": "Rule generated and saved successfully", "rule": saved_rule}
        else:
            raise HTTPException(status_code=500, detail="Failed to save the rule")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/")
async def get_rules():
    try:
        logger.info("Fetching rules from database")
        # Use supabase_client instead of supabase
        response = supabase_client.table("rules").select("*").order("created_at", desc=True).execute()

        # Ensure `rules` is always an array
        rules = response.data if response.data else []
        
        return {
            "message": "Rules fetched successfully" if rules else "No rules found",
            "rules": rules
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch rules: {str(e)}")



@router.get("/{rule_id}", response_model=Rule)
async def get_rule(rule_id: int):
    """
    Get a specific rule by ID
    """
    try:
        response = supabase_client.table('rules').select("*").eq('id', rule_id).single().execute()
        
        if not response.data:
            raise HTTPException(status_code=404, detail="Rule not found")
            
        return response.data
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch rule: {str(e)}"
        )

@router.delete("/{rule_id}")
async def delete_rule(rule_id: str):
    try:
        # Attempt to delete the rule from the Supabase table
        response = supabase_client.table("rules").delete().eq("id", rule_id).execute()

        if response.data:
            return {"message": "Rule deleted successfully", "deleted_rule": response.data}
        else:
            raise HTTPException(status_code=404, detail="Rule not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete rule: {str(e)}")