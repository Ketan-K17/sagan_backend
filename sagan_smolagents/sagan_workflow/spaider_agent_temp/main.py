from io import BytesIO
from bs4 import BeautifulSoup
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

# Dynamically resolve the path to config.py
CURRENT_FILE = Path(__file__).resolve()
SAGAN_MULTIMODAL = CURRENT_FILE.parent.parent.parent
CONFIG_PATH = SAGAN_MULTIMODAL / "config.py"

# Load config.py dynamically
spec = importlib.util.spec_from_file_location("config", CONFIG_PATH)
config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config)

# Load config.py dynamically
CONFIG_PATH = project_root / "config.py"
config_spec = importlib.util.spec_from_file_location("config", CONFIG_PATH)
configfile = importlib.util.module_from_spec(config_spec)
config_spec.loader.exec_module(configfile)
# Import config and read cookie file
from config import FIRST_WORKFLOW_ROOT, SSL_CERT_PATH

# getting project_id from cookie.json
with open(project_root / "cookie.json", "r") as f:
    cookie_data = json.load(f)
    project_id = cookie_data.get("project_id")

print(f"Incumbent Project's ID: {project_id}")

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
from fastapi import Body, FastAPI, Form, HTTPException, File, UploadFile,Request
from fastapi.responses import JSONResponse, StreamingResponse,FileResponse,HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import subprocess
from pathlib import Path
import base64
from typing import List
from pydantic import BaseModel
from pypdf import PdfReader
from docx import Document
# import mammoth
from io import BytesIO
from langchain_core.runnables.config import RunnableConfig
from graph import create_graph, compile_graph, print_stream
from html2docx import html2docx
import mammoth

import csv
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

DATA_RFP_FOLDER = Path("data_rfp")
FOLDERS = {
    "Proposal Files": DATA_RFP_FOLDER / "Proposal Files",
    "Additional Files": DATA_RFP_FOLDER / "Additional Files",
    "sota": DATA_RFP_FOLDER / "sota",
    "methodology": DATA_RFP_FOLDER / "methodology",
    "other": DATA_RFP_FOLDER / "other",
}

# Ensure all folders exist
for folder in FOLDERS.values():
    folder.mkdir(parents=True, exist_ok=True)


UPLOAD_DIRECTORY = "uploaded_resumes"
CSV_DIRECTORY = "csv_data"


# Ensure the upload directory exists
os.makedirs(UPLOAD_DIRECTORY, exist_ok=True)
os.makedirs(CSV_DIRECTORY, exist_ok=True)


class CompanyInfo(BaseModel):
    name: str
    address: str
    teamSize: str
    website: str

class PersonInfo(BaseModel):
    firstName: str
    lastName: str
    position: str

class ProjectInfo(BaseModel):
    projectName: str
    description: str
    issuingOrg: str
    callLink: str



DATA_RFP_FOLDER = Path("data_rfp")
FOLDERS = {
    "Proposal Files": DATA_RFP_FOLDER / "Proposal Files",
    "Additional Files": DATA_RFP_FOLDER / "Additional Files",
    "sota": DATA_RFP_FOLDER / "sota",
    "methodology": DATA_RFP_FOLDER / "methodology",
    "other": DATA_RFP_FOLDER / "other",
}

# Ensure all folders exist
for folder in FOLDERS.values():
    folder.mkdir(parents=True, exist_ok=True)


UPLOAD_DIRECTORY = "uploaded_resumes"
CSV_DIRECTORY = "csv_data"


# Ensure the upload directory exists
os.makedirs(UPLOAD_DIRECTORY, exist_ok=True)
os.makedirs(CSV_DIRECTORY, exist_ok=True)


class CompanyInfo(BaseModel):
    name: str
    address: str
    teamSize: str
    website: str

class PersonInfo(BaseModel):
    firstName: str
    lastName: str
    position: str

class ProjectInfo(BaseModel):
    projectName: str
    description: str
    issuingOrg: str
    callLink: str


def extract_sections(latex_content):
    """
    Extract all top-level section titles (i.e., \section{}) from LaTeX content.
    Returns a list of section titles.
    """
    import re
    
    def clean_latex_command(text: str) -> str:
        """Remove LaTeX commands from text while preserving content."""
        # Remove comments
        text = re.sub(r'%.*$', '', text, flags=re.MULTILINE)
        # Remove specific LaTeX commands while keeping their content
        text = re.sub(r'\\textbf{(.*?)}', r'\1', text)
        text = re.sub(r'\\textit{(.*?)}', r'\1', text)
        text = re.sub(r'\\emph{(.*?)}', r'\1', text)
        return text.strip()

    try:
        # Extract content between \begin{document} and \end{document}
        doc_match = re.search(r'\\begin{document}(.*?)\\end{document}', latex_content, re.DOTALL)
        if not doc_match:
            # If no document environment found, process the entire content
            main_content = latex_content
        else:
            main_content = doc_match.group(1)

        # Regular expression for section commands
        section_pattern = r'\\section\{([^}]+)\}'
        
        # Find all section matches
        section_matches = list(re.finditer(section_pattern, main_content))
        
        if not section_matches:
            # Handle case with no sections
            return []

        # Extract section titles
        section_titles = []
        for match in section_matches:
            title = clean_latex_command(match.group(1))
            section_titles.append(title)
        # print(section_titles,"section titlkes 470")
        return section_titles

    except Exception as e:
        raise ValueError(f"Error processing LaTeX content: {str(e)}")


# helper function to get section_title and section_text from formatting node state JSON.
def get_generated_sections() -> list:
# def get_generated_sections() -> dict:
    """
    Extract and return the generated_sections dictionary from the formatting node state JSON.
    
    Returns:
        dict: Dictionary containing section titles as keys and their content as values
        
    Raises:
        FileNotFoundError: If the state JSON file doesn't exist
        ValueError: If JSON data is malformed or missing required fields
    """
    CURRENT_FILE = Path(__file__).resolve()
    SAGAN_ROOT = CURRENT_FILE.parent.parent.parent
    CONFIG_PATH = SAGAN_ROOT / "config.py"
    
    # Load config.py dynamically
    spec = importlib.util.spec_from_file_location("config", CONFIG_PATH)
    config = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config)
    
    current_project_id = config.get_current_project_id()
    updated_paths = config.update_project_paths(current_project_id)

    nodewise_output_dir = updated_paths['nodewise_output']

    final_state_path = nodewise_output_dir / "formatting_node_state.json"
    
    try:
       with open(final_state_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
            generated_sections = json_data.get('state', {}).get('generated_sections', {})
        # with open(final_state_path, 'r',) as f:
        #     json_data = json.load(f)
        #     generated_sections = json_data.get('state', {}).get('generated_sections', {})
            
            if not generated_sections:
                raise ValueError("No generated sections found in state file")
                
            section_titles = list(generated_sections.keys())
            print(section_titles,"sections")
            return section_titles
       

            # return generated_sections
            
    except FileNotFoundError:
        raise FileNotFoundError(f"State file not found at {final_state_path}")
    except json.JSONDecodeError:
        raise ValueError("Invalid JSON in state file")

# @app.post("/upload-files")
# async def upload_files(files: list[UploadFile] = File(...)):
#     if not all(file.content_type == "application/pdf" for file in files):
#         return JSONResponse(status_code=400, content={"message": "Invalid file type. Please upload only PDF files."})

#     successful_uploads = []
#     failed_uploads = []

#     for file in files:
#         file_location = DATA_RFP_FOLDER / file.filename
#         try:
#             with open(file_location, "wb") as f:
#                 f.write(await file.read())

#             # Validate the PDF and read all pages
#             with open(file_location, "rb") as pdf_file:
#                 reader = PdfReader(pdf_file)
#                 # Iterate through all pages to ensure the PDF is fully readable
#                 for page_num, page in enumerate(reader.pages):
#                     text = page.extract_text()
#                     print(f"Text from file '{file.filename}' page {page_num + 1}: {text}")

#             successful_uploads.append(file.filename)

#         except Exception as e:
#             # Delete the file if it's not a valid PDF or an error occurred
#             if file_location.exists():
#                 os.remove(file_location)
#             failed_uploads.append(file.filename)

#     if failed_uploads:
#         return JSONResponse(status_code=400, content={
#             "message": "Some files were not valid PDFs.",
#             "failed_uploads": failed_uploads
#         })

#     return JSONResponse(content={
#         "message": "All files uploaded and verified successfully!",
#         "successful_uploads": successful_uploads
#     })




# @app.post("/upload-files")
# async def upload_files(files: list[UploadFile] = File(...)):
#     if not all(file.content_type == "application/pdf" for file in files):
#         return JSONResponse(status_code=400, content={"message": "Invalid file type. Please upload only PDF files."})

#     successful_uploads = []
#     failed_uploads = []

#     for file in files:
#         file_location = DATA_RFP_FOLDER / file.filename
#         try:
#             with open(file_location, "wb") as f:
#                 f.write(await file.read())

#             # Validate the PDF and read all pages
#             with open(file_location, "rb") as pdf_file:
#                 reader = PdfReader(pdf_file)
#                 # Iterate through all pages to ensure the PDF is fully readable
#                 for page_num, page in enumerate(reader.pages):
#                     text = page.extract_text()
#                     print(f"Text from file '{file.filename}' page {page_num + 1}: {text}")

#             successful_uploads.append(file.filename)

#         except Exception as e:
#             # Delete the file if it's not a valid PDF or an error occurred
#             if file_location.exists():
#                 os.remove(file_location)
#             failed_uploads.append(file.filename)

#     if failed_uploads:
#         return JSONResponse(status_code=400, content={
#             "message": "Some files were not valid PDFs.",
#             "failed_uploads": failed_uploads
#         })

#     return JSONResponse(content={
#         "message": "All files uploaded and verified successfully!",
#         "successful_uploads": successful_uploads
#     })




@app.post("/upload-files")
async def upload_files(files: list[UploadFile] = File(...), folder: str = Form(...)):
    if folder not in FOLDERS:
        return JSONResponse(status_code=400, content={"message": f"Invalid folder: {folder}"})

    target_folder = FOLDERS[folder]

    successful_uploads = []
    failed_uploads = []

    for file in files:
        if file.content_type != "application/pdf":
            failed_uploads.append(file.filename)
            continue

        file_location = target_folder / file.filename

        try:
            with open(file_location, "wb") as f:
                f.write(await file.read())

            # Validate the PDF and read all pages
            with open(file_location, "rb") as pdf_file:
                reader = PdfReader(pdf_file)
                for page_num, page in enumerate(reader.pages):
                    text = page.extract_text()
                    print(f"Text from file '{file.filename}' page {page_num + 1}: {text}")

            successful_uploads.append(file.filename)

        except Exception as e:
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

        # Get updated paths from config
        updated_paths = config.update_project_paths(project_id)
        
        # Use the correct output path from config
        output_dir = updated_paths['workflow1_output']
        docx_file = output_dir / "output.docx"
        
        # Ensure output directory exists
        output_dir.mkdir(parents=True, exist_ok=True)

        with open(docx_file, "rb") as file:
            encoded_string = base64.b64encode(file.read()).decode('utf-8')
        
        sections = get_generated_sections()

        response_data = {
            "ai_message": state.get('ai_message'),
            "docx_file": encoded_string,
            "section_headings": sections,
            "success": True,
        }
        return JSONResponse(response_data)

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

# @app.get("/read-docx")
# def read_docx():
#     project_root = Path(__file__).parent.parent
#     output_dir = project_root / "spaider_agent_temp" / "output_pdf"
#     docx_file = output_dir / "output.docx"
    
#     if not docx_file.exists():
#         raise HTTPException(status_code=404, detail="DOCX file not found")
    
#     try:
#         doc = Document(docx_file)
#         docx_content = "\n".join([para.text for para in doc.paragraphs])
#         print(docx_content,"content")
#         return {"message": "DOCX content retrieved successfully", "content": docx_content}
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error reading DOCX file: {str(e)}")



@app.get("/download")
def download_document():
    file_path = os.path.join(os.path.dirname(__file__), "./output_pdf/output.docx")
    return FileResponse(file_path, media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document', filename="document.docx")
  
# @app.get("/download-base64")
# def download_document_base64():
#     file_path = os.path.join(os.path.dirname(__file__), "./output_pdf/output.docx")
    
#     with open(file_path, "rb") as file:
#         encoded_string = base64.b64encode(file.read()).decode('utf-8')
    
#     return {"file": encoded_string}



@app.get("/download-base64")
def download_document_base64():
    try:
        # Get current project ID
        project_id = config.get_current_project_id()
        if not project_id:
            raise HTTPException(
                status_code=404,
                detail="No active project found"
            )
        
        # Update project paths based on current project
        config.update_project_paths(project_id)
        
        # Get state.json path for current project
        # project_state_path = config.PROJECTS_BASE / project_id / "state.json"
        
        
        # Read state.json
        with open(config.OUTPUT_DOCX_PATH, "rb") as file:
            encoded_string = base64.b64encode(file.read()).decode('utf-8')
    
        return {"file": encoded_string}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting base64 document: {str(e)}"
        )




# class DocxContent(BaseModel):
#     content: str

# @app.post("/save-docx")
# async def save_docx(docx_data: DocxContent):
#     try:
#         # Decode base64 content
#         docx_content = base64.b64decode(docx_data.content)
        
#         # Get the file path
#         file_path = os.path.join(os.path.dirname(__file__), "./output_pdf/output.docx")
        
#         # Ensure directory exists
#         os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
#         # Write the content to file
#         with open(file_path, "wb") as docx_file:
#             docx_file.write(docx_content)
            
#         return {"message": "Document saved successfully"}
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Failed to save document: {str(e)}")



class DocxContent(BaseModel):
    content: str



class DocumentContent(BaseModel):
    content: str  # Quill's HTML content

# @app.post("/upload-docx")
# async def upload_docx(data: DocumentContent = Body(...)):
#     # file_path = os.path.join('./', "document.docx")

#     try:
#         docx_content = html2docx(data.content, title="Document")
#         with open("./output_pdf/output.docx", "wb") as f:
#             f.write(docx_content.getvalue())
#         print("Document created successfully")
#     except Exception as e:
#         print("Error creating document:", e)
#         return {"error": str(e)}

#     return {"message": "Document saved successfully!", "filename": "output.docx"}


@app.post("/upload-docx")
async def upload_docx(data: DocumentContent = Body(...)):
    # Get current project ID
    project_id = config.get_current_project_id()
    if not project_id:
        raise HTTPException(
            status_code=404,
            detail="No active project found"
        )
    
    # Update project paths based on current project
    config.update_project_paths(project_id)
    
    try:
        docx_content = html2docx(data.content, title="Document")
        with open(config.OUTPUT_DOCX_PATH, "wb") as f:
            f.write(docx_content.getvalue())
        print("Document created successfully")
    except Exception as e:
        print("Error creating document:", e)
        return {"error": str(e)}
    

    # take docx_content and convert it to base64 string 
    with open(config.OUTPUT_DOCX_PATH, "rb") as file:
        encoded_string = base64.b64encode(file.read()).decode('utf-8')

        # save this encoded_string in the state.json of the current project 
        state_path = config.PROJECTS_BASE / project_id / "state.json"
        with open(state_path, "r") as f:
            state_data = json.load(f)
            state_data["output_docx_base64"] = encoded_string
        with open(state_path, "w") as f:
            json.dump(state_data, f, indent=4)

    return {"message": "Document saved successfully!", "filename": str(config.OUTPUT_DOCX_PATH)}


# @app.get("/convert-to-html/")
# async def convert_to_html():
#     file_path = os.path.join(os.path.dirname(__file__), "./output_pdf/output.docx")
#     if not os.path.exists(file_path):
#         raise HTTPException(status_code=404, detail="File not found.")
#     with open(file_path, "rb") as docx_file:
#         contents = docx_file.read()
#     result = mammoth.convert_to_html(BytesIO(contents))
#     html_content = result.value
#     return HTMLResponse(content=html_content)


@app.get("/convert-to-html/")
async def convert_to_html():
    project_id = config.get_current_project_id()
    if not project_id:
        raise HTTPException(
            status_code=404,
            detail="No active project found"
        )
    
    # Update project paths based on current project
    config.update_project_paths(project_id)
    
    # Get output docx path for current project
    file_path = config.OUTPUT_DOCX_PATH
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found in workflow1_output folder")
        
        
    with open(file_path, "rb") as docx_file:
        contents = docx_file.read()
    result = mammoth.convert_to_html(BytesIO(contents))
    html_content = result.value
    return HTMLResponse(content=html_content)


@app.post("/upload-image/")
async def upload_image(file: UploadFile = File(...)):
    upload_dir = "uploaded_images"
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, file.filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return {"url": f"http://localhost:8000/{file_path}"}

@app.post("/convert-to-docx/")
async def convert_to_docx(html: str = Form(...)):
    # Create a new .docx Document
    doc = Document()

    # Parse the HTML content
    soup = BeautifulSoup(html, 'html.parser')

    # Iterate through the parsed HTML and add content to the .docx document
    for element in soup.descendants:
        if element.name == 'p':
            doc.add_paragraph(element.get_text())
        elif element.name == 'h1':
            doc.add_heading(element.get_text(), level=1)
        elif element.name == 'h2':
            doc.add_heading(element.get_text(), level=2)
        # Add more handling as needed for other HTML elements

    # Define the path to save the edited document
    output_dir = os.path.join(os.path.dirname(__file__), "output_pdf")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "output.docx")

    # Save the document to the specified path
    doc.save(output_path)

    # Return the .docx file as a FileResponse
    return FileResponse(
        output_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename="output.docx"
    )





@app.post("/upload_resume")
async def upload_resume(section: str = Form(...), file: UploadFile = File(...)):
    file_location = os.path.join(UPLOAD_DIRECTORY, f"{section}_resume_{file.filename}")
    
    with open(file_location, "wb") as buffer:
        buffer.write(await file.read())
    
    return {"message": "File uploaded successfully", "file_name": f"{section}_resume_{file.filename}"}



def overwrite_csv(filename, data, fieldnames):
    file_path = os.path.join(CSV_DIRECTORY, filename)
    
    with open(file_path, mode='w', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(data)

# Endpoints to store data into individual CSV files (overwriting old data)
@app.post("/store_project_info/")
def store_project_info(project: ProjectInfo):
    overwrite_csv("project_info.csv", project.dict(), ["projectName", "description", "issuingOrg", "callLink"])
    return {"message": "Project information stored successfully"}


@app.post("/store_company_info/")
def store_company_info(company: CompanyInfo):
    overwrite_csv("company_info.csv", company.dict(), ["name", "address", "teamSize", "website"])
    return {"message": "Company information stored successfully"}

@app.post("/store_author_info/")
def store_author_info(author: PersonInfo):
    overwrite_csv("author_info.csv", author.dict(), ["firstName", "lastName", "position"])
    return {"message": "Author information stored successfully"}

@app.post("/store_pi_info/")
def store_pi_info(pi: PersonInfo):
    overwrite_csv("pi_info.csv", pi.dict(), ["firstName", "lastName", "position"])
    return {"message": "PI information stored successfully"}

@app.post("/store_copi_info/")
def store_copi_info(copi: PersonInfo):
    overwrite_csv("copi_info.csv", copi.dict(), ["firstName", "lastName", "position"])
    return {"message": "Co-PI information stored successfully"}









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


