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
