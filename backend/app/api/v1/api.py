from fastapi import APIRouter
from app.api.v1.endpoints import forms, workflows
from app.api.v1.endpoints.rules import router as rules_router

api_router = APIRouter()
api_router.include_router(forms.router, prefix="/forms", tags=["forms"])
api_router.include_router(workflows.router, prefix="/workflows", tags=["workflows"])
api_router.include_router(rules_router, prefix="/rules", tags=["rules"])