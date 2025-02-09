from dotenv import load_dotenv
import os
import certifi
import ssl
import shutil
import sys
from pathlib import Path

# Add parent directory to Python path to enable relative imports
current_dir = Path(__file__).parent
project_root = current_dir.parent.parent
sys.path.append(str(project_root))

# Import config after setting up path
from config import FIRST_WORKFLOW_ROOT, SSL_CERT_PATH

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

config = RunnableConfig(
    recursion_limit=50,
    configurable={"thread_id": "1"}
)

class UserInput(BaseModel):
    message: str

# Define paths
DATA_RFP_FOLDER = Path("data_rfp")
DATA_RFP_FOLDER.mkdir(exist_ok=True)

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

@app.post("/process-input-first-wrokflow")
async def process_input(user_input: UserInput):
    try:   
        print(f"Processing input: {user_input.message}")
        
        # Run the graph with the input
        outputs = list(graph.stream(
            {"messages": [("user", user_input.message)]}, 
            stream_mode="values", 
            config=config
        ))

        state = outputs[-1]

        # Get the file paths
        project_root = Path(__file__).parent.parent
        output_dir = project_root / "spaider_agent_temp" / "output_pdf"
        tex_file = output_dir / "output.tex"
        pdf_file = output_dir / "output.pdf"
        md_file = output_dir / "output.md"  # Define markdown file path
        
        # Ensure output directory exists
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            # First check if the tex file exists
            if not tex_file.exists():
                raise HTTPException(
                    status_code=404,
                    detail=f"LaTeX file not found at {tex_file}"
                )

            print(f"Found LaTeX file at: {tex_file}")
            print(f"Looking for PDF file at: {pdf_file}")

            # Additional debug information
            print(f"Files in output directory: {list(output_dir.glob('*'))}")

            # Check files with detailed logging
            if not tex_file.exists():
                print(f"TeX file missing at: {tex_file}")
                raise HTTPException(
                    status_code=404,
                    detail="LaTeX file not found after compilation"
                )

            if not pdf_file.exists():
                print(f"PDF file missing at: {pdf_file}")
                raise HTTPException(
                    status_code=404,
                    detail="PDF file not generated successfully"
                )

            print("Both files exist, proceeding with conversion")

            # Convert to Markdown
            from utils.latex_to_markdown import create_markdown_pipeline
            md_pipeline = create_markdown_pipeline()
            md_result = md_pipeline.convert_latex_to_markdown(str(tex_file), str(output_dir))

            # Read all files
            try:
                # Read LaTeX content
                with open(tex_file, 'r', encoding='utf-8') as f:
                    latex_content = f.read()
                print("Successfully read LaTeX content")

                right_section_headings =  extract_sections(latex_content)

                # Read PDF content
                with open(pdf_file, 'rb') as f:
                    pdf_content = base64.b64encode(f.read()).decode('utf-8')
                print("Successfully read PDF content")

                # Read or create Markdown content
                markdown_content = None
                if md_result["success"]:
                    # Save markdown to file if not already saved
                    if md_result["markdown_content"]:
                        with open(md_file, 'w', encoding='utf-8') as f:
                            f.write(md_result["markdown_content"])
                        
                        # Read the saved markdown file
                        with open(md_file, 'r', encoding='utf-8') as f:
                            markdown_content = f.read()
                        print("Successfully created and read Markdown file")

                response_data = {
                    "ai_message": state.get('ai_message'),
                    "tex_file": latex_content,
                    "pdf_file": pdf_content,
                    "md_file": markdown_content,
                    "section_headings": right_section_headings,
                    "success": True,
                    "file_paths": {
                        "tex": str(tex_file),
                        "pdf": str(pdf_file),
                        "md": str(md_file) if markdown_content else None
                    }
                }

                if not markdown_content:
                    response_data["markdown_error"] = md_result.get("error", "Unknown conversion error")
                    print(f"Markdown conversion failed: {response_data['markdown_error']}")

                # Clean up auxiliary files but keep the main outputs
                aux_extensions = ['.aux', '.log', '.out', '.fls', '.fdb_latexmk', '.synctex.gz']
                for ext in aux_extensions:
                    aux_file = output_dir / f"output{ext}"
                    if aux_file.exists():
                        aux_file.unlink()
                print("Cleaned up auxiliary files")

                return JSONResponse(response_data)

            except Exception as e:
                print(f"Error reading files: {str(e)}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Error reading generated files: {str(e)}"
                )

        except subprocess.CalledProcessError as e:
            print(f"LaTeX compilation error: {e.stderr}")
            raise HTTPException(
                status_code=500,
                detail=f"LaTeX compilation failed: {e.stderr}"
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
            for response in graph.stream({"messages": [("user", message)]}, stream_mode="values", config=config):
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


