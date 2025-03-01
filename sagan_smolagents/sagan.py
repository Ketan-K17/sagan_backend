from fastapi import FastAPI, Form, HTTPException, File, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import subprocess
from pathlib import Path
import base64
from typing import List, Optional
from pydantic import BaseModel
from pypdf import PdfReader
from typing import Dict
from colorama import Fore, Style, init
import json
import shutil
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
            "projects": project_names
            # "projects": projects
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# @app.post("/create_project")
# async def create_project(project_details: ProjectDetails):
#     try:
#         print(f"\n{Fore.YELLOW}Starting project creation for: {project_details.project_name}{Style.RESET_ALL}")
        
#         # Create new project using existing utility
#         project_state = sagan_utils.create_new_project(project_details.project_name)
#         print(f"Project state created: {project_state}")
        
#         # Update config paths with new project_id
#         config.update_project_paths(project_state["project_id"])
#         print(f"Updated project paths for ID: {project_state['project_id']}")

#         # Print project paths
#         config.print_project_paths()

#         # Write project_id to cookie.json
#         try:
#             cookie_path = Path("cookie.json")
#             cookie_path.write_text(json.dumps({"project_id": project_state["project_id"]}))
#             print("Cookie file written successfully")
#         except Exception as cookie_error:
#             print(f"{Fore.RED}Error writing cookie file: {str(cookie_error)}{Style.RESET_ALL}")
#             raise

#         try:
#             ui = sagan_utils.UIHandler()
#         except Exception as ui_error:
#             print(f"{Fore.RED}Error creating UI Handler: {str(ui_error)}{Style.RESET_ALL}")
#             raise

#         # WRITE CODE FOR USER TO UPLOAD DATA FILES HERE (AND CONVERT TO VECTORDB)
#         print(f"\n{Fore.YELLOW}Select input files for vector database:{Style.RESET_ALL}")
#         data_files = ui.select_files("Select input files", [
#                     ('PDF files', '*.pdf'),
#                     ('Text files', '*.txt'),
#                     ('Word files', '*.docx'),
#                     ('CSV files', '*.csv')
#                 ])
        
#         if data_files:
#             print(f"\n{Fore.YELLOW}Processing data files...{Style.RESET_ALL}")
#             try:
#                 sagan_utils.create_data_vectordb(project_state["project_id"], data_files)
#                 print(f"{Fore.GREEN}Data vector database created successfully!{Style.RESET_ALL}")
#             except Exception as e:
#                 print(f"{Fore.RED}CREATE PROJECT ENDPOINT: Failed to create data vector database - {str(e)}{Style.RESET_ALL}")
#                 raise HTTPException(status_code=500, detail=f"Failed to create data vector database: {str(e)}")

        

#         # WRITE CODE FOR USER TO UPLOAD TEMPLATE FILE HERE (AND CONVERT TO VECTORDB)
#         print(f"\n{Fore.YELLOW}Select template file:{Style.RESET_ALL}")
#         template_file = ui.select_template()
                
#         if template_file:
#             print(f"\n{Fore.YELLOW}Processing template...{Style.RESET_ALL}")
#             if sagan_utils.create_template_vectordb(project_state["project_id"], template_file):
#                 print(f"{Fore.GREEN}Template vector database created successfully!{Style.RESET_ALL}")
#             else:
#                 print(f"{Fore.RED}CREATE PROJECT ENDPOINT: Failed to create template vector database.{Style.RESET_ALL}")

        
#         return JSONResponse(content={
#             "message": "Project created and loaded successfully",
#             "project_id": project_state["project_id"],
#             "project_state": project_state
#         })
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))

# @app.post("/load_project")
# async def load_project(request: LoadProjectRequest):
#     """Load an existing project by its name"""
#     try:
#         project_name = request.project_name
        
#         # Get all projects
#         projects = sagan_utils.get_all_projects()
        
#         # Find project with matching name
#         project_id = None
#         project_state = None
#         for pid, state in projects.items():
#             if state["name"].lower() == project_name.lower():
#                 project_id = pid
#                 project_state = state
#                 break
        
#         if project_id is None:
#             raise HTTPException(status_code=404, detail="Project not found")
        
#         # Update config paths with loaded project_id
#         config.update_project_paths(project_id)


#         config.print_project_paths()

#         # Write project_id to cookie.json
#         cookie_path = Path("cookie.json")
#         cookie_path.write_text(json.dumps({"project_id": project_id}))

#         # WRITE CODE FOR USER TO UPDATE DATA FILES HERE (AND ADD TO VECTORDB)
#         print(f"\n{Fore.YELLOW}Select input files to add to vector database:{Style.RESET_ALL}")
#         sagan_utils.handle_project_choice(project_id)


#         return JSONResponse(content={
#             "status": "success",
#             "message": "Project loaded successfully",
#             "project_id": project_id,
#             "project_state": project_state
#         })
#     except HTTPException as he:
#         raise he
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


class ProjectDetails(BaseModel):
    project_name: str

class LoadProjectRequest(BaseModel):
    project_name: str

@app.post("/create_project")
async def create_project(
    project_name: str = Form(...),  
    data_files: List[UploadFile] = File(default=[]),  # Changed to default=[] instead of just []
    template_file: Optional[UploadFile] = File(default=None)  # Make sure to use default=None
):
    try:
        print(f"\nStarting project creation for: {project_name}")
        
        # Create new project
        project_state = sagan_utils.create_new_project(project_name)
        
        # Update config paths
        config.update_project_paths(project_state["project_id"])
        config.print_project_paths()

        # Write project_id to cookie
        cookie_path = Path("cookie.json")
        cookie_path.write_text(json.dumps({"project_id": project_state["project_id"]}))

        # Process data files if provided
        if data_files:
            print("\nProcessing data files...")
            file_data = []
            for file in data_files:
                content = await file.read()
                file_data.append((file.filename, content))
            
            if not sagan_utils.create_data_vectordb(project_state["project_id"], file_data):
                raise HTTPException(
                    status_code=500,
                    detail="Failed to create data vector database"
                )
            print("Data vector database created successfully!")

        # Process template file if provided
        if template_file:
            print("\nProcessing template file...")
            template_content = await template_file.read()
            if not sagan_utils.create_template_vectordb(
                project_state["project_id"],
                template_file.filename,
                template_content
            ):
                raise HTTPException(
                    status_code=500,
                    detail="Failed to create template vector database"
                )
            print("Template vector database created successfully!")
        
        # If not, this means user has selected one of default templates.
        else:
            # Default template selection (will be determined by frontend later)
            selected_template = 'afr'  # Can be 'afr' or 'core'
            
            print(f"\nUsing default template: {selected_template}")
            
            # Paths for the template source
            templates_base_path = Path("/Users/ketankunkalikar/Desktop/SS/sagan_smolagents/sagan_smolagents/ingest_data/ready_made_templates")
            template_source_path = templates_base_path / selected_template
            template_db_source = template_source_path / "template_db"
            template_file_source = template_source_path / f"{selected_template}_stripped.docx"
            unedited_template_file_source = template_source_path / f"{selected_template}.docx"
            
            
            # Paths for the destination in the project
            project_id = project_state["project_id"]
            project_base = config.PROJECTS_BASE / project_id
            template_db_dest = project_base / "vectordb" / "template_db"
            workflow_output_dest = project_base / "workflow1_output"
            template_file_dest = workflow_output_dest / f"output.docx"
            unedited_template_file_dest = project_base / "template" / f"{selected_template}.docx"
            
            # Ensure destination directories exist
            template_db_dest.parent.mkdir(parents=True, exist_ok=True)
            workflow_output_dest.mkdir(parents=True, exist_ok=True)
            
            # Copy template_db folder
            if template_db_source.exists():
                if template_db_dest.exists():
                    shutil.rmtree(template_db_dest)
                shutil.copytree(template_db_source, template_db_dest)
                print(f"Copied template database from {template_db_source} to {template_db_dest}")
            else:
                print(f"Warning: Template database not found at {template_db_source}")
            
            # Copy template docx file
            if template_file_source.exists():
                shutil.copy2(template_file_source, template_file_dest)
                print(f"Copied template file from {template_file_source} to {template_file_dest}")
            else:
                print(f"Warning: Template file not found at {template_file_source}")

            # Copy unedited template docx file
            if unedited_template_file_source.exists():
                shutil.copy2(unedited_template_file_source, unedited_template_file_dest)
                print(f"Copied unedited template file from {unedited_template_file_source} to {unedited_template_file_dest}")
            else:
                print(f"Warning: Unedited template file not found at {unedited_template_file_source}")
            
            # Update state with template information
            update_state_path = project_base / "state.json"
            if update_state_path.exists():
                with open(update_state_path, 'r') as f:
                    state_data = json.load(f)
                
                state_data["vectordb"] = state_data.get("vectordb", {})
                state_data["vectordb"]["template"] = str(template_db_dest)
                state_data["vectordb"]["template_file"] = str(template_file_dest)
                
                with open(update_state_path, 'w') as f:
                    json.dump(state_data, f, indent=4)
                
                print(f"Updated state with template information")

        return JSONResponse(content={
            "message": "Project created and loaded successfully",
            "project_id": project_state["project_id"],
            "project_state": project_state
        })

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/load_project")
async def load_project(
    project_name: str = Form(...),  # Ensure project_name is received correctly
):
    try:
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
        
        # Update config paths
        config.update_project_paths(project_id)
        config.print_project_paths()

        # Write project_id to cookie
        cookie_path = Path("cookie.json")
        cookie_path.write_text(json.dumps({"project_id": project_id}))

        # Process new data files if provided
        # if data_files:
        #     print("\nProcessing new data files...")
        #     file_data = []
        #     for file in data_files:
        #         content = await file.read()
        #         file_data.append((file.filename, content))
            
        #     if not sagan_utils.update_vectordb(project_id, file_data):
        #         print("Failed to update vector database")

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