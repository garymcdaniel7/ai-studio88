from fastapi import FastAPI, HTTPException
from backend.database import get_projects, get_talent, create_talent

app = FastAPI(title="AI Studio API")

@app.get("/")
def health_check():
    return {"status": "ok"}

@app.get("/projects")
def projects():
    return get_projects().data

@app.get("/talent")
def talent():
    return get_talent().data

@app.post("/talent")
def add_talent(talent_data: dict):
    try:
        result = create_talent(talent_data)
        return result.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
