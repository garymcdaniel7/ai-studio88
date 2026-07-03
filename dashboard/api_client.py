"""Shared API client for the Streamlit dashboard.

All pages use this module to call the FastAPI backend.
Never duplicates backend logic — the API is the source of truth.
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")


def _url(path: str) -> str:
    return f"{API_BASE_URL}/api/v1{path}"


def _handle(resp: requests.Response):
    """Return JSON or raise with detail."""
    if resp.ok:
        return resp.json()
    detail = resp.json().get("detail", resp.text) if resp.headers.get("content-type", "").startswith("application/json") else resp.text
    raise Exception(f"API error {resp.status_code}: {detail}")


# ── Health ────────────────────────────────────────────────────────────────────

def health():
    return requests.get(f"{API_BASE_URL}/").json()


def v1_health():
    return requests.get(_url("/health")).json()


# ── Projects ──────────────────────────────────────────────────────────────────

def list_projects():
    return _handle(requests.get(f"{API_BASE_URL}/projects"))


# ── Talent ────────────────────────────────────────────────────────────────────

def list_talent():
    return _handle(requests.get(_url("/talent")))


def create_talent(data: dict):
    return _handle(requests.post(_url("/talent"), json=data))


# ── Assets ────────────────────────────────────────────────────────────────────

def list_assets():
    return _handle(requests.get(_url("/assets")))


def get_asset(asset_id: str):
    return _handle(requests.get(_url(f"/assets/{asset_id}")))


def upload_asset(file_bytes: bytes, filename: str, content_type: str, asset_type: str = "general", tags: str = ""):
    files = {"file": (filename, file_bytes, content_type)}
    data = {"asset_type": asset_type, "tags": tags}
    return _handle(requests.post(_url("/assets"), files=files, data=data))


def delete_asset(asset_id: str):
    return _handle(requests.delete(_url(f"/assets/{asset_id}")))


# ── Jobs ──────────────────────────────────────────────────────────────────────

def list_jobs(status: str = None, job_type: str = None):
    params = {}
    if status:
        params["status"] = status
    if job_type:
        params["type"] = job_type
    return _handle(requests.get(_url("/jobs"), params=params))


def get_job(job_id: str):
    return _handle(requests.get(_url(f"/jobs/{job_id}")))


def create_job(data: dict):
    return _handle(requests.post(_url("/jobs"), json=data))


def cancel_job(job_id: str):
    return _handle(requests.post(_url(f"/jobs/{job_id}/cancel")))


def retry_job(job_id: str):
    return _handle(requests.post(_url(f"/jobs/{job_id}/retry")))


def delete_job(job_id: str):
    return _handle(requests.delete(_url(f"/jobs/{job_id}")))


# ── Workflows ─────────────────────────────────────────────────────────────────

def list_workflows():
    return _handle(requests.get(_url("/workflows")))


def get_workflow(workflow_id: str):
    return _handle(requests.get(_url(f"/workflows/{workflow_id}")))


def create_workflow(data: dict):
    return _handle(requests.post(_url("/workflows"), json=data))


def run_workflow(workflow_id: str, input_data: dict = None):
    return _handle(requests.post(_url(f"/workflows/{workflow_id}/run"), json={"input": input_data or {}}))


def delete_workflow(workflow_id: str):
    return _handle(requests.delete(_url(f"/workflows/{workflow_id}")))
