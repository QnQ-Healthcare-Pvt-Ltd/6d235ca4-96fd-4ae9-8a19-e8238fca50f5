from supabase import create_client
from app.core.config import settings

supabase_client = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_KEY
) 