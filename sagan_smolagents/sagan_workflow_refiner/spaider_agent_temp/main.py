from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.runnables.config import RunnableConfig
from fastapi import FastAPI, HTTPException, WebSocket,WebSocketDisconnect,File ,Form,UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from pathlib import Path
import uvicorn
import subprocess
import base64
from typing import Optional,Dict
import os
import asyncio
import json
import uuid
import importlib.util
from docx import Document
from docx.oxml import OxmlElement
from docx.text.paragraph import Paragraph

from nodes_and_conditional_edges.nodes import ws_manager,research_query_generator
from models.chatgroq import BuildChatGroq, BuildChatOpenAI
# LOCAL IMPORTS
from graph import create_graph, compile_graph, print_stream
from schemas import State
from prompts.prompts import RESEARCH_QUERY_GENERATOR_PROMPT

# Dynamically resolve the path to config.py
CURRENT_FILE = Path(__file__).resolve()
SAGAN_MULTIMODAL = CURRENT_FILE.parent.parent.parent
CONFIG_PATH = SAGAN_MULTIMODAL / "config.py"

# Load config.py dynamically
spec = importlib.util.spec_from_file_location("config", CONFIG_PATH)
config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config)

# Update UserInput model to include human input fields
class UserInput(BaseModel):
    message: str
    section_number: Optional[int] = None


class PublishInput(BaseModel):
    modified_text: str
    section_number: Optional[int] = None


class UpdateLatexInput(BaseModel):
    """Input model for updating complete LaTeX document"""
    latex_content: str

# Initialize FastAPI app
app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize paths and configurations
DATA_FOLDER = Path("testfolder")
DATA_FOLDER.mkdir(exist_ok=True)

DATA_RFP_FOLDER = Path("testfolder")
DATA_RFP_FOLDER.mkdir(exist_ok=True)

# Initialize graph
verbose = True
builder = create_graph("1234")
graph = compile_graph(builder)

# Configure runnable
runnable_config = RunnableConfig(
    recursion_limit=50,
    configurable={"thread_id": "1"}
)

# helper function to get section_title and section_text from formatting node state JSON.
def get_section_info(section_number: int) -> tuple[str, str]:
    """
    Extract section title and text for a given section number from the formatting node state JSON.
    
    Args:
        section_number (int): The section number to extract (1-based indexing)
        
    Returns:
        tuple[str, str]: A tuple containing (section_title, section_text)
        
    Raises:
        ValueError: If section number is invalid or if JSON data is malformed
        FileNotFoundError: If the state JSON file doesn't exist
    """
    final_state_path = config.NODEWISE_OUTPUT_PATH / "formatting_node_state.json"

    print("1")
    
    with open(final_state_path, 'r', encoding='utf-8') as f:
        json_data = json.load(f)
        generated_sections = json_data.get('state', {}).get('generated_sections', {})

        
    # with open(final_state_path, 'r') as f:
    #     json_data = json.load(f)
    #     generated_sections = json_data.get('state', {}).get('generated_sections', {})

        print("2")
        
    # Convert section number to corresponding section title and text
    section_titles = list(generated_sections.keys())
    if 1 <= section_number <= len(section_titles):
        s_title = section_titles[section_number - 1]
        s_text = generated_sections[s_title]
        return s_title, s_text
    else:
        raise ValueError(f"Section number {section_number} is out of range. Available sections: {len(section_titles)}")
    
# helper function to read the contents of a docx file.
def read_docx_file(file_path: str) -> str:
    """
    Read the contents of a DOCX file and return its text as a string.
    
    Args:
        file_path (str): Path to the DOCX file
        
    Returns:
        str: Text content of the DOCX file
    """
    try:
        # Load the document
        doc = Document(file_path)
        
        # Extract text from paragraphs
        full_text = []
        for para in doc.paragraphs:
            full_text.append(para.text)
        
        # Join all paragraphs with newlines
        return '\n'.join(full_text)
    
    except Exception as e:
        return f"Error reading file: {str(e)}"

# helper functions for docx editing.
def insert_paragraph_after(paragraph, text=""):
    """
    Insert a new paragraph immediately after the given paragraph and set its text.
    """
    # Create a new XML element for a paragraph
    new_p_element = OxmlElement("w:p")
    # Insert the new element right after the current paragraph's element
    paragraph._p.addnext(new_p_element)
    # Wrap the new element in a Paragraph object
    new_paragraph = Paragraph(new_p_element, paragraph._parent)
    # Add a run with the provided text
    new_paragraph.add_run(text)
    return new_paragraph

def fill_section_with_text(doc_path: str, section_title: str, section_text: str):
    """
    Open the document at 'doc_path', find the paragraph containing section_title,
    and replace all content after it until the next section with section_text.
    
    Args:
        doc_path (str): Path to the Word document
        section_title (str): Title of the section to modify
        section_text (str): New text to replace the section content with
    """
    # Load the document
    doc = Document(doc_path)
    
    # Find the section and its content
    section_start = None
    for i, paragraph in enumerate(doc.paragraphs):
        if section_title.lower() in paragraph.text.lower():
            section_start = i
            break
    
    if section_start is None:
        print(f"Section '{section_title}' not found in document")
        return
    
    # Find the end of this section (next heading or document end)
    section_end = len(doc.paragraphs)
    for i in range(section_start + 1, len(doc.paragraphs)):
        if doc.paragraphs[i].style.name.startswith('Heading'):
            section_end = i
            break
    
    # Remove all paragraphs between section start and end (except the heading)
    for i in range(section_end - 1, section_start, -1):
        p = doc.paragraphs[i]._element
        p.getparent().remove(p)
    
    # Insert the new text after the section heading
    insert_paragraph_after(doc.paragraphs[section_start], section_text)
    
    # Save the modified document back to the same file
    doc.save(doc_path)


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket API that allows clients to connect with a session_id."""
    await ws_manager.connect(websocket, session_id)
    try:
        print('try block')
        while True:
            message = await ws_manager.receive_message(session_id)
            
            # if message:
            #     await ws_manager.send_message(session_id, f"Echo: {message}")
    except WebSocketDisconnect:
        ws_manager.disconnect(session_id)


@app.post("/process-input")
async def process_input(user_input: UserInput):
    try:
        # Step 1: Generate a session ID and connect WebSocket
        session_id = "1234"
        # await ws_manager.connect(session_id,{
        #    "message":"hey  from 943"
        # })
        # Step 2: Default paths and configurations
        output_dir = Path(config.OUTPUT_PDF_PATH)
        docx_file = output_dir / "output.docx"
        # Ensure output directory exists
        output_dir.mkdir(parents=True, exist_ok=True)

        # Step 3: Extract section if section number and draft path are provided
        if user_input.section_number:
            draft_path = docx_file  # Using tex_file as draft 
            s_title, s_text = get_section_info(user_input.section_number)
            initial_input = {
                "user_prompt": user_input.message,
                "section_text": s_text,
                "section_title": s_title,
                "section_number": user_input.section_number,
                "rough_draft_path": str(draft_path)
            }
        else:
            initial_input = {"messages": [("user", user_input.message)]}

        # Step 4: Process through graph and capture the final state
        state = None
        try:
            async for output in graph.astream(
                initial_input,
                stream_mode="values",
                config=runnable_config
            ):
                state = output  # Capture the last state

                # WebSocket: Send progress updates
                # await websocket.send_json({"type": "progress", "content": state})

            if not state:
                raise HTTPException(
                    status_code=500,
                    detail="No state returned from graph processing"
                )

            # Debug logging
            print("\nState after graph processing:")
            print(f"State: {state}")
            print(f"AI Message in state: {state.get('ai_message')}")
            print(f"Modified text in state: {bool(state.get('modified_section_text'))}")

            # Step 5: Build initial response data
            response_data = {
                "success": True,
                "message": "Processing completed",
                "ai_message": state.get("ai_message"),
                "modified_section_text": state.get("modified_section_text")
            }

            # WebSocket: Send final state
            # await websocket.send_json({"type": "final_state", "content": response_data})

            print("\nConstructing response with state data:")
            print(f"AI Message: {response_data['ai_message']}")
            print(f"Modified text present: {bool(response_data['modified_section_text'])}")

            # Step 6: Handle file processing for successful state
            if response_data.get("success"):
                print("Save was successful. Writing to docx file...")

                # Verify whether docx file exists
                if not docx_file.exists():
                    print(f"Docx file missing at: {docx_file}")
                    raise HTTPException(
                        status_code=404,
                        detail="Docx file not found after formatting"
                    )

                print("Docx file exists, proceeding with writing to docx file...")

                try:
                    docx_content = read_docx_file(docx_file)
                    print("Successfully read docx content")

                    # Update response data with file information
                    response_data.update({
                        "docx_file": docx_content,
                        "file_paths": {
                            "docx": str(docx_file),
                        }
                    })

                except Exception as e:
                    print(f"Error processing output file: {str(e)}")
                    raise HTTPException(
                        status_code=500,
                        detail=f"Error processing output file: {str(e)}"
                    )
            else:
                print("No file processing needed or save was not successful")

            # Final debug logging
            print("\nFinal response data:")
            print(f"AI Message: {response_data['ai_message']}")
            print(f"Modified text present: {bool(response_data.get('modified_section_text'))}")

            return JSONResponse(response_data)

        except Exception as e:
            print(f"Error in process-input: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Error in process-input: {str(e)}"
            )

    except Exception as e:
        print(f"Error in outer process-input: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error in process-input endpoint: {str(e)}"
        )

    # finally:
    #     # Ensure WebSocket disconnects
    #     ws_manager.disconnect(session_id)


@app.post("/publish")
async def publish(update_request: PublishInput):
    """
    API to update a specific section in the docx_file.
    """
    try:
        # Extract input parameters
        modified_text = update_request.modified_text
        section_number = update_request.section_number
        # modified_text = update_request.get("modified_section_text")
        # section_number = update_request.get("section_number")

        if not modified_text or not section_number:
            raise HTTPException(
                status_code=400,
                detail="Both 'modified_section_text' and 'section_number' are required"
            )

        # File paths
        output_dir = Path(config.OUTPUT_PDF_PATH)
        docx_file = output_dir / "output.docx"

        if not docx_file.exists():
            raise HTTPException(
                status_code=404,
                detail="Docx file not found at the specified path"
            )

        try:
            # Get the section title for the given section number
            s_title, _ = get_section_info(section_number)
            
            # Update the specific section using the helper function
            fill_section_with_text(
                doc_path=str(docx_file),
                section_title=s_title,
                section_text=modified_text
            )

            # Read the updated docx content
            docx_content = read_docx_file(str(docx_file))

            print("Updated the docx file with modified section text.")

            response_data = {
                "success": True,
                "message": "Section updated successfully",
                "docx_file": docx_content,
                "file_paths": {
                    "docx": str(docx_file),
                }
            }

            return JSONResponse(response_data)

        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Error processing output file: {str(e)}"
            )

    except Exception as e:
        print(f"Error in publish API: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error in publish endpoint: {str(e)}"
        )



@app.post("/update-latex")
async def update_latex(update_request: UpdateLatexInput):
    """
    API to update the complete LaTeX document and regenerate PDF and markdown files.
    Accepts full LaTeX content from frontend and updates all related files.
    """
    try:
        # Extract input parameters
        
        latex_content = update_request.latex_content

        if not latex_content:
            raise HTTPException(
                status_code=400,
                detail="LaTeX content is required"
            )

        # File paths
        output_dir = Path(config.OUTPUT_PDF_PATH)
        
        tex_file = output_dir / "output.tex"
        pdf_file = output_dir / "output.pdf"
        md_file = output_dir / "output.md"

        # Write the new LaTeX content to file
        try:
            with open(tex_file, 'w', encoding='utf-8') as f:
                f.write(latex_content)
            print("Successfully updated LaTeX file with new content.")
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Error writing to LaTeX file: {str(e)}"
            )

        # Convert to PDF and Markdown
        try:
            # Create Markdown
            md_pipeline = create_markdown_pipeline()
            md_result = md_pipeline.convert_latex_to_markdown(str(tex_file), str(output_dir))

            # Create PDF
            pipeline = LaTeXPipeline()
            pdf_result = pipeline.latex_to_pdf(tex_file, output_dir)

            print(pdf_result,"pdf_result")

            if not pdf_file.exists():
                raise HTTPException(
                    status_code=500,
                    detail="PDF generation failed"
                )
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Error in file conversion: {str(e)}"
            )

        # Prepare response with all file contents
        try:
            # Read PDF content
            with open(pdf_file, 'rb') as f:
                pdf_content = base64.b64encode(f.read()).decode('utf-8')

            # Handle Markdown content
            markdown_content = None
            if md_result["success"]:
                markdown_content = md_result["markdown_content"]
                # Save the markdown content to file
                with open(md_file, 'w', encoding='utf-8') as f:
                    f.write(markdown_content)
                print("Successfully created Markdown file.")

            # Prepare the response
            response_data = {
                "success": True,
                "message": "Documents updated successfully",
                "tex_file": latex_content,
                "pdf_file": pdf_content,
                "md_file": markdown_content,
                "file_paths": {
                    "tex": str(tex_file),
                    "pdf": str(pdf_file),
                    "md": str(md_file) if markdown_content else None
                }
            }

            # Clean up auxiliary files
            aux_extensions = ['.aux', '.log', '.out', '.fls', '.fdb_latexmk', '.synctex.gz']
            for ext in aux_extensions:
                aux_file = output_dir / f"output{ext}"
                if aux_file.exists():
                    aux_file.unlink()
            print("Cleaned up auxiliary files.")

            return JSONResponse(response_data)

        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Error preparing response: {str(e)}"
            )

    except Exception as e:
        print(f"Error in update-latex API: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error in update-latex endpoint: {str(e)}"
        )



@app.post('/upload-image-to-latex')
async def uploadImageToLatex(image: UploadFile = File(...), latex: str = Form(...), cursor_position: int = Form(...)):
  try:
    print('code started',image)
   
    file_path = os.path.join(config.OUTPUT_PDF_PATH, image.filename)
    # file_path = os.path.join('C://Users//Asus//Desktop//sagan-demo-be//sagan_workflow//spaider_agent_temp//output_pdf', image.filename)
    with open(file_path, "wb") as buffer: 
      buffer.write(await image.read())
    
    image_path = f"./{image.filename}"

    print(image_path,"image path")
      
    # image_latex = f'\\includegraphics[width=0.25\\linewidth]{{{image_path}}}'
    
    # text_before_cursor = latex[:cursor_position]
    # text_after_cursor = latex[cursor_position:]
    # latex_content = text_before_cursor + image_latex + text_after_cursor
    
    # output_file_path = os.path.join('./', 'output.tex')
    # with open(output_file_path, "w") as output_file:
    #   output_file.write(latex_content)
      
    # print('new latex ready')
    
    return JSONResponse(content={"latex": "heyy"})
  
  except Exception as e:
    raise HTTPException(status_code=500, detail=f"uploadImageToLatex Error: {str(e)}")        




@app.post("/test-websocket")
async def test_websocket():
    try:
     await ws_manager.send_message("1234",{
        "type":"question1",
        "data":"Would you like to modify or add queries? (yes/no)"
    })
    except Exception as e:
        print(f"Error in test-websocket: {str(e)}")


# @app.post("/interact")
# async def interact(user_input: UserInput):
#     """
#     Endpoint to interact with the graph using user input with streaming response.
#     """
#     if not user_input.message:
#         raise HTTPException(status_code=400, detail="No input provided")

#     try:
#         # Stream the responses from the graph
#         async def event_generator():
#             initial_input = {"messages": [("user", user_input.message)]}
#             for response in graph.stream(initial_input, stream_mode="values", config=runnable_config):
#                 yield f"data: {response}\n\n"

#         return StreamingResponse(event_generator(), media_type="text/event-stream")

#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8002)






