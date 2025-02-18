from dotenv import load_dotenv
import os
import certifi
import ssl
import shutil
import sys
from pathlib import Path
import json
import importlib, importlib.util
# Add parent directory to Python path to enable relative imports
current_dir = Path(__file__).parent
project_root = current_dir.parent.parent
sys.path.append(str(project_root))

# Load config.py dynamically
CONFIG_PATH = project_root / "config.py"
config_spec = importlib.util.spec_from_file_location("config", CONFIG_PATH)
configfile = importlib.util.module_from_spec(config_spec)
config_spec.loader.exec_module(configfile)
# Import config and read cookie file
from config import FIRST_WORKFLOW_ROOT, SSL_CERT_PATH

with open(project_root / "cookie.json", "r") as f:
    cookie_data = json.load(f)
    project_id = cookie_data.get("project_id")

print(f"Project ID: {project_id}")

configfile.update_project_paths(project_id)

# Set up SSL certificate first, before any other imports
try:
    # Use certifi's default certificate
    default_cert = certifi.where()
    ssl_cert_path = FIRST_WORKFLOW_ROOT / "certs" / "cacert.pem"
    
    # Create directory if it doesn't exist
    os.makedirs(os.path.dirname(ssl_cert_path), exist_ok=True)
    
    # Copy the certificate to our location with proper permissions
    shutil.copy2(default_cert, ssl_cert_path)
    os.chmod(ssl_cert_path, 0o644)  # Set read permissions
    
    # Set environment variables
    os.environ['SSL_CERT_FILE'] = str(ssl_cert_path)
    os.environ['REQUESTS_CA_BUNDLE'] = str(ssl_cert_path)
    os.environ['CURL_CA_BUNDLE'] = str(ssl_cert_path)
    
except Exception as e:
    print(f"Warning: Could not set up SSL certificate: {e}")
    print("Falling back to certifi's default certificate")
    os.environ['SSL_CERT_FILE'] = certifi.where()
    os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
    os.environ['CURL_CA_BUNDLE'] = certifi.where()

# Now continue with all original imports and code
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

from langchain_core.runnables.config import RunnableConfig
from graph import create_graph, compile_graph, print_stream



app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create graph workflow instance and compile it
builder = create_graph()
graph = compile_graph(builder)

runnable_config = RunnableConfig(
    recursion_limit=50,
    configurable={"thread_id": "1"}
)

class UserInput(BaseModel):
    message: str

# Define paths
DATA_RFP_FOLDER = Path("data_rfp")
DATA_RFP_FOLDER.mkdir(exist_ok=True)

@app.post("/upload-files")
async def upload_files(files: list[UploadFile] = File(...)):
    if not all(file.content_type == "application/pdf" for file in files):
        return JSONResponse(status_code=400, content={"message": "Invalid file type. Please upload only PDF files."})

    successful_uploads = []
    failed_uploads = []

    for file in files:
        file_location = DATA_RFP_FOLDER / file.filename
        try:
            with open(file_location, "wb") as f:
                f.write(await file.read())

            # Validate the PDF and read all pages
            with open(file_location, "rb") as pdf_file:
                reader = PdfReader(pdf_file)
                # Iterate through all pages to ensure the PDF is fully readable
                for page_num, page in enumerate(reader.pages):
                    text = page.extract_text()
                    print(f"Text from file '{file.filename}' page {page_num + 1}: {text}")

            successful_uploads.append(file.filename)

        except Exception as e:
            # Delete the file if it's not a valid PDF or an error occurred
            if file_location.exists():
                os.remove(file_location)
            failed_uploads.append(file.filename)

    if failed_uploads:
        return JSONResponse(status_code=400, content={
            "message": "Some files were not valid PDFs.",
            "failed_uploads": failed_uploads
        })

    return JSONResponse(content={
        "message": "All files uploaded and verified successfully!",
        "successful_uploads": successful_uploads
    })

# ADD PROJECT ID AS INPUT FROM FRONTEND
@app.post("/process-input-first-workflow")
async def process_input(user_input: UserInput):
    try:   
        print(f"Processing input: {user_input.message}")
        
        outputs = list(graph.stream(
            {"user_prompt": user_input.message}, 
            stream_mode="values", 
            config=runnable_config
        ))

        state = outputs[-1]

        # Get the file paths
        project_root = Path(__file__).parent.parent
        output_dir = configfile.NODEWISE_OUTPUT_PATH / "output_pdf"
        docx_file = output_dir / "output.docx"
        
        # Ensure output directory exists
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            if not docx_file.exists():
                raise HTTPException(
                    status_code=404,
                    detail=f"docx file not found at {docx_file}"
                )

            print(f"Found docx file at: {docx_file}")
            print(f"Files in output directory: {list(output_dir.glob('*'))}")

            if not docx_file.exists():
                print(f"docx file missing at: {docx_file}")
                raise HTTPException(
                    status_code=404,
                    detail="docx file not found after compilation"
                )

            print("Docx file found.")

            # Convert PosixPath objects to strings before JSON serialization
            response_data = {
                "ai_message": state.get('ai_message'),
                "docx_file": str(docx_file),  # Convert to string
                "success": True,
                "file_paths": {
                    "docx": str(docx_file),  # Convert to string
                }
            }

            return JSONResponse(response_data)

        except subprocess.CalledProcessError as e:
            print(f"Docx generation error: {e.stderr}")
            raise HTTPException(
                status_code=500,
                detail=f"Docx generation failed: {e.stderr}"
            )
    
    except Exception as e:
        print(f"Error in process-input endpoint: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=str(e)
        )

@app.post("/interact")
async def interact(user_input: UserInput):
    """
    Endpoint to interact with the graph using user input.
    """
    message = user_input.message

    if not message:
        raise HTTPException(status_code=400, detail="No input provided")

    try:
        # Stream the responses from the graph
        async def event_generator():
            for response in graph.stream({"messages": [("user", message)]}, stream_mode="values", config=runnable_config):
                yield f"data: {response}\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)



# @app.post("/upload")
# async def upload_file(file: UploadFile = File(...)):
#     if file.content_type != "application/pdf":
#         return JSONResponse(status_code=400, content={"message": "Invalid file type. Please upload a PDF."})

#     file_location = DATA_FOLDER / file.filename
#     with open(file_location, "wb") as f:
#         f.write(await file.read())

#     # Validate the PDF and read all pages
#     try:
#         with open(file_location, "rb") as pdf_file:
#             reader = PdfReader(pdf_file)
#             # Iterate through all pages to ensure the PDF is fully readable
#             for page_num, page in enumerate(reader.pages):
#                 text = page.extract_text()
#                 print(f"Text from page {page_num + 1}: {text}")
#     except Exception as e:
#         # Delete the file if it's not a valid PDF
#         os.remove(file_location)
#         return JSONResponse(status_code=400, content={"message": "The file is not a valid PDF."})

#     return JSONResponse(content={"message": "File uploaded and verified successfully!"})



# upload rfp


