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
from colorama import Fore, Style, init
import json
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
        # project_id = sagan_utils.create_project_id()
        project_state = sagan_utils.create_new_project(project_details.project_name)
        
        # Update config paths with new project_id
        config.update_project_paths(project_state["project_id"])

        # Print project paths
        config.print_project_paths()

        # Write project_id to cookie.json
        cookie_path = Path("cookie.json")
        cookie_path.write_text(json.dumps({"project_id": project_state["project_id"]}))

        ui = sagan_utils.UIHandler()

        # WRITE CODE FOR USER TO UPLOAD DATA FILES HERE (AND CONVERT TO VECTORDB)
        print(f"\n{Fore.YELLOW}Select input files for vector database:{Style.RESET_ALL}")
        data_files = ui.select_files("Select input files", [
                    ('PDF files', '*.pdf'),
                    ('Text files', '*.txt'),
                    ('Word files', '*.docx'),
                    ('CSV files', '*.csv')
                ])
        
        if data_files:
            print(f"\n{Fore.YELLOW}Processing data files...{Style.RESET_ALL}")
            try:
                sagan_utils.create_data_vectordb(project_state["project_id"], data_files)
                print(f"{Fore.GREEN}Data vector database created successfully!{Style.RESET_ALL}")
            except Exception as e:
                print(f"{Fore.RED}CREATE PROJECT ENDPOINT: Failed to create data vector database - {str(e)}{Style.RESET_ALL}")
                raise HTTPException(status_code=500, detail=f"Failed to create data vector database: {str(e)}")

        

        # WRITE CODE FOR USER TO UPLOAD TEMPLATE FILE HERE (AND CONVERT TO VECTORDB)
        print(f"\n{Fore.YELLOW}Select template file:{Style.RESET_ALL}")
        template_file = ui.select_template()
                
        if template_file:
            print(f"\n{Fore.YELLOW}Processing template...{Style.RESET_ALL}")
            if sagan_utils.create_template_vectordb(project_state["project_id"], template_file):
                print(f"{Fore.GREEN}Template vector database created successfully!{Style.RESET_ALL}")
            else:
                print(f"{Fore.RED}CREATE PROJECT ENDPOINT: Failed to create template vector database.{Style.RESET_ALL}")

        
        return JSONResponse(content={
            "message": "Project created and loaded successfully",
            "project_id": project_state["project_id"],
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

        # Write project_id to cookie.json
        cookie_path = Path("cookie.json")
        cookie_path.write_text(json.dumps({"project_id": project_id}))

        # WRITE CODE FOR USER TO UPDATE DATA FILES HERE (AND ADD TO VECTORDB)
        print(f"\n{Fore.YELLOW}Select input files to add to vector database:{Style.RESET_ALL}")
        sagan_utils.handle_project_choice(project_id)


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