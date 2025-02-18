from fastapi import FastAPI, HTTPException, File, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import subprocess
from pathlib import Path
import base64
from typing import List
from pydantic import BaseModel
from pypdf import PdfReader
from typing import Dict

# getting config file here: 


# LOCAL IMPORTS
import sagan_utils as sagan_utils
import config as config


app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ProjectDetails(BaseModel):
    project_name: str

class LoadProjectRequest(BaseModel):
    project_name: str


@app.get("/list_projects")
async def list_projects():
    """Get list of all existing projects with their details"""
    try:
        projects = sagan_utils.get_all_projects()
        # Extract just the names from each project's state
        project_names = [project_data["name"] for project_data in projects.values()]
        
        # Print to console
        print("\n=== Existing Projects ===")
        for i, name in enumerate(project_names, 1):
            print(f"{i}. {name}")
        print("=====================\n")
        
        return JSONResponse(content={
            "status": "success",
            "projects": projects
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/create_project")
async def create_project(project_details: ProjectDetails):
    try:
        # Create new project using existing utility
        project_id = sagan_utils.create_project_id()
        project_state = sagan_utils.create_new_project(project_details.project_name)
        
        # Update config paths with new project_id
        config.update_project_paths(project_id)
        
        return JSONResponse(content={
            "message": "Project created successfully",
            "project_id": project_id,
            "project_state": project_state
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/load_project")
async def load_project(request: LoadProjectRequest):
    """Load an existing project by its name"""
    try:
        project_name = request.project_name
        
        # Get all projects
        projects = sagan_utils.get_all_projects()
        
        # Find project with matching name
        project_id = None
        project_state = None
        for pid, state in projects.items():
            if state["name"].lower() == project_name.lower():
                project_id = pid
                project_state = state
                break
        
        if project_id is None:
            raise HTTPException(status_code=404, detail="Project not found")
        
        # Update config paths with loaded project_id
        config.update_project_paths(project_id)


        config.print_project_paths()
        
        return JSONResponse(content={
            "status": "success",
            "message": "Project loaded successfully",
            "project_id": project_id,
            "project_state": project_state
        })
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8002)