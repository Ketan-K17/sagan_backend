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


# getting config file here: 


# LOCAL IMPORTS
import sagan_smolagents.sagan_utils as sagan_utils


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


@app.post("/create_project")
async def create_project(project_details: ProjectDetails):
    project_id = sagan_utils.create_project_id()
    print(f"Generated project_id: {project_id}")
    print(f"Project name: {project_details.project_name}")
    
    print(f"Processing input: {project_id}")


@app.post("/load_project")
async def load_project(project_id: str):
    pass

if __name__ == "__main__":
    print(project_id)