import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in .env")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def get_projects():
    return supabase.table("projects").select("*").execute()

def get_talent():
    return supabase.table("talent").select("*").execute()

def create_talent(data):
    return supabase.table("talent").insert(data).execute()


# =============================================================================
# Assets
# =============================================================================

def get_assets():
    """Get all assets, ordered by most recent first."""
    return supabase.table("assets").select("*").order("created_at", desc=True).execute()


def get_asset_by_id(asset_id: str):
    """Get a single asset by ID."""
    return supabase.table("assets").select("*").eq("id", asset_id).single().execute()


def create_asset(data: dict):
    """Insert a new asset record."""
    return supabase.table("assets").insert(data).execute()


def delete_asset(asset_id: str):
    """Delete an asset record by ID. Returns the deleted row."""
    return supabase.table("assets").delete().eq("id", asset_id).execute()
