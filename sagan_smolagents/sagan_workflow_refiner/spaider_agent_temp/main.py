from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.runnables.config import RunnableConfig
from langchain_groq import ChatGroq
from fastapi import FastAPI, HTTPException, WebSocket,WebSocketDisconnect,File ,Form,UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from pathlib import Path
import uvicorn
import subprocess
import base64
from typing import Optional,Dict,List
import os
import asyncio
import json
import uuid
import importlib.util
from docx import Document
from docx.oxml import OxmlElement
from docx.text.paragraph import Paragraph

from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import PictureItem, TableItem
from docling_core.types.doc import ImageRefMode


from nodes_and_conditional_edges.nodes import ws_manager,research_query_generator
from models.chatgroq import BuildChatGroq, BuildChatOpenAI
# LOCAL IMPORTS
from graph import create_graph, compile_graph, print_stream
from schemas import State
from prompts.prompts import RESEARCH_QUERY_GENERATOR_PROMPT

from dotenv import load_dotenv

load_dotenv()

# Dynamically resolve the path to config.py
CURRENT_FILE = Path(__file__).resolve()
project_root = CURRENT_FILE.parent.parent.parent
CONFIG_PATH = project_root / "config.py"

# Load config.py dynamically
spec = importlib.util.spec_from_file_location("config", CONFIG_PATH)
config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config)

# getting project_id from cookie.json
with open(project_root / "cookie.json", "r") as f:
    cookie_data = json.load(f)
    project_id = cookie_data.get("project_id")

print(f"incumbent project: {project_id}")

# Update UserInput model to include human input fields
class UserInput(BaseModel):
    message: str
    section_number: Optional[int] = None


class PublishInput(BaseModel):
    modified_text: str
    section_number: Optional[int] = None

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

groq_llm = BuildChatGroq(model="llama-3.2-90b-vision-preview", temperature=0.0)

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
    # Dynamically resolve the path to config.py
    CURRENT_FILE = Path(__file__).resolve()
    project_root = CURRENT_FILE.parent.parent.parent
    CONFIG_PATH = project_root / "config.py"

    # Load config.py dynamically
    spec = importlib.util.spec_from_file_location("config", CONFIG_PATH)
    configfile = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(configfile)

    updated_paths = configfile.update_project_paths(project_id)
    
    final_state_path = updated_paths['nodewise_output'] / "formatting_node_state.json"

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
    
def get_text_info_from_inputfile(inputfile: UploadFile, grand_prompt: str):
    """
    Get textual information from an uploaded file and append it to the grand_prompt.
    
    Args:
        inputfile (UploadFile): The uploaded file to process
        grand_prompt (str): The prompt to append the extracted text to
        
    Returns:
        str: The updated prompt with the file's content appended
    """
    try:
        # Check if a file with this name already exists in the temp directory
        temp_dir = Path("temp_uploads")
        file_path = temp_dir / inputfile.filename
        
        # If file doesn't exist, save it
        if not file_path.exists():
            temp_dir.mkdir(exist_ok=True)
            content = inputfile.file.read()
            with open(file_path, "wb") as f:
                f.write(content)
            # Reset the file pointer
            inputfile.file.seek(0)
        
        # Use the extract_info function to process the document
        extracted_text = extract_info(str(file_path))
        
        # Append the extracted text to the grand_prompt
        # Format: original prompt + clear separator + document content
        updated_prompt = f"{grand_prompt}\n\n--- Document Content ---\n{extracted_text}"
        
        print(f"Enhanced prompt created with document content from {inputfile.filename}")
        return updated_prompt
    
    except Exception as e:
        print(f"Error processing uploaded file: {str(e)}")
        # Return the original prompt if there was an error
        return grand_prompt

def get_image_info_from_inputfile(inputfile: UploadFile, grand_prompt: str):
    """
    Get textual information from an uploaded image file and append it to the grand_prompt.
    
    Args:
        inputfile (UploadFile): The uploaded image file to process
        grand_prompt (str): The prompt to append the extracted text to
        
    Returns:
        str: The updated prompt with image information appended
    """
    try:
        # Step 1: Dynamically load config and get paths
        CURRENT_FILE = Path(__file__).resolve()
        project_root = CURRENT_FILE.parent.parent.parent
        CONFIG_PATH = project_root / "config.py"
        
        spec = importlib.util.spec_from_file_location("config", CONFIG_PATH)
        config = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(config)

        updated_paths = config.update_project_paths(project_id)
        
        # Step 2: Create output directory for extracted images
        # Make it a subfolder of workflow2_output as requested
        workflow2_output = updated_paths.get('workflow2_output', project_root / "workflow2_output")
        output_dir = workflow2_output / "extracted_images"
        output_dir.mkdir(exist_ok=True, parents=True)
        
        # Step 3: Save the uploaded file temporarily
        temp_dir = Path("temp_uploads")
        temp_dir.mkdir(exist_ok=True)
        file_path = temp_dir / inputfile.filename
        
        content = inputfile.file.read()
        with open(file_path, "wb") as f:
            f.write(content)
        
        # Reset the file pointer
        inputfile.file.seek(0)
        
        # Step 4: Set up docling pipeline options for extraction
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        pipeline_options = PdfPipelineOptions()
        pipeline_options.images_scale = 2.0  # Adjust resolution if needed
        pipeline_options.generate_page_images = True
        pipeline_options.generate_picture_images = True
        
        # Step 5: Convert the document using docling's DocumentConverter
        doc_converter = DocumentConverter(
            format_options={
                'pdf': PdfFormatOption(pipeline_options=pipeline_options)
            }
        )
        conv_res = doc_converter.convert(file_path)
        
        # Step 6: Extract and save images of figures and tables
        picture_paths = []
        table_paths = []
        
        picture_counter = 0
        table_counter = 0
        
        for element, _level in conv_res.document.iterate_items():
            if isinstance(element, PictureItem):
                picture_counter += 1
                img_path = output_dir / f"picture_{picture_counter}.png"
                with open(img_path, "wb") as fp:
                    element.get_image(conv_res.document).save(fp, "PNG")
                picture_paths.append(str(img_path))
                
            elif isinstance(element, TableItem):
                table_counter += 1
                img_path = output_dir / f"table_{table_counter}.png"
                with open(img_path, "wb") as fp:
                    element.get_image(conv_res.document).save(fp, "PNG")
                table_paths.append(str(img_path))
        
        # Step 7: Create a summary of extracted images to append to the prompt
        image_summary = f"\n\n--- Document Visual Elements ---\n"
        image_summary += f"Extracted {picture_counter} images and {table_counter} tables from document.\n"
        
        if picture_counter > 0:
            image_summary += f"Pictures found: {picture_counter}\n"
            
        if table_counter > 0:
            image_summary += f"Tables found: {table_counter}\n"
            
        # Step 8: Placeholder for future ChatGroq integration
        # TODO: Future implementation of ChatGroq image description
        # This will use BuildChatGroq to analyze each image and generate descriptions
        # The code for implementing this feature will go here
        # For each image in picture_paths and table_paths:
        #   1. Load the image
        #   2. Use ChatGroq to describe the image
        #   3. Add description to image_summary

        # Call describe_image() for each image in picture_paths
        if picture_counter > 0:
            for i, img_path in enumerate(picture_paths):
                try:
                    img_description = describe_image(img_path)
                    image_summary += f"\n\nDescription of image {i+1}:\n{img_description}"
                    print(f"Generated description for image {i+1}")
                except Exception as e:
                    print(f"Error describing image {i+1}: {str(e)}")
                    image_summary += f"\n\nDescription of image {i+1}: Error generating description"
        
        # Step 9: Append the image summary to the grand_prompt
        updated_prompt = f"{grand_prompt}{image_summary}"
        
        print(f"Enhanced prompt created with image information from {inputfile.filename}")
        print(f"Images and tables saved to {output_dir}")
        
        return updated_prompt
    
    except Exception as e:
        print(f"Error processing image file: {str(e)}")
        # Return the original prompt if there was an error
        return grand_prompt

def extract_info(input_doc: str) -> str:
    """
    Processes the input document using Docling.
    For image files, it leverages OCR and visual understanding to extract any embedded text or contextual info.
    For textual documents (PDF, DOCX, etc.), it extracts and converts all text.
    Returns a unified markdown string representing the content.
    """
    converter = DocumentConverter()
    
    # Optional: Check file extension to allow for future customizations.
    ext = os.path.splitext(input_doc)[1].lower()
    if ext in [".jpg", ".jpeg", ".png", ".bmp"]:
        # For images, you might want to set additional pipeline options if needed.
        # Here, we simply let Docling auto-detect the image and process it.
        result = converter.convert(input_doc)
    else:
        result = converter.convert(input_doc)
    
    # Export all extracted information as Markdown.
    extracted_content = result.document.export_to_markdown()
    return extracted_content

def describe_image(image_path: str) -> str:
    # Read and encode the image in base64
    with open(image_path, "rb") as image_file:
        base64_image = base64.b64encode(image_file.read()).decode('utf-8')
    
    # Prepare a message that includes a text prompt and the image (as a data URI)
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        "Please describe the content of the workflow present in this image. Do it in this format:\n"
                        "<what the entire workflow represents>\n\n"
                        "<Detailed description of the flow diagram, what node leads to what node, and what the node does.>\n\n"
                        "Keep your description concise, and do not include any other descriptive/reflective text. Your response must be in one paragraph."
                    )
                },
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
            ]
        }
    ]
    
    # Send the message to the LLM and return its response
    response = groq_llm.invoke(messages)
    return response.content

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
async def process_input(
    message: str = Form(...),
    section_number: int = Form(...),  # Section number is now mandatory
    document: Optional[UploadFile] = File(None)
):
    """
    Process user input with AI assistance, targeting a specific section of the document.
    
    Args:
        message: User's text prompt or question
        section_number: Required section number to target (1-based indexing)
        document: Optional file upload to provide additional context
        
    Returns:
        JSONResponse with AI's response and section information
    """
    try:
        # Step 1: Generate a session ID and connect WebSocket
        session_id = "1234"

        # Step 2: Dynamically load config and get paths
        CURRENT_FILE = Path(__file__).resolve()
        SAGAN_ROOT = CURRENT_FILE.parent.parent.parent
        CONFIG_PATH = SAGAN_ROOT / "config.py"
        
        spec = importlib.util.spec_from_file_location("config", CONFIG_PATH)
        config = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(config)

        updated_paths = config.update_project_paths(project_id)
        
        # Step 3: Default paths and configurations
        docx_file = updated_paths['output_docx']
        
        # Step 4: Process uploaded document if provided
        document_content = None
        document_text = None
        if document:
            print(f"\nProcessing uploaded document: {document.filename}")
            
            # First save the uploaded file for use in multiple processes
            # Create a temp directory for uploads if it doesn't exist
            temp_upload_dir = Path("temp_uploads")
            temp_upload_dir.mkdir(exist_ok=True)
            
            # Save the uploaded file
            file_path = temp_upload_dir / document.filename
            document_content = await document.read()
            
            with open(file_path, "wb") as f:
                f.write(document_content)
            
            # Reset the file pointer for the UploadFile object
            await document.seek(0)
            
            # Process the document using the get_text_info_from_inputfile function
            # Create a grand prompt with the user's message
            grand_prompt = message
            
            # Extract text and append to the grand prompt
            # This is the key step that enhances the user message with document content
            enhanced_prompt = get_text_info_from_inputfile(document, grand_prompt)

            # Process images and append to the grand prompt
            final_prompt = get_image_info_from_inputfile(document, enhanced_prompt)
            
            # Save the original message and set the enhanced one
            # 'message' now contains both the original user prompt and the document content
            message = final_prompt

        # Step 5: Extract section since section number is now mandatory
        draft_path = docx_file
        s_title, s_text = get_section_info(section_number)
        
        # Create initial input with section information
        # Note: 'message' already contains the document content if a document was provided,
        # because it was enhanced by get_text_info_from_inputfile
        initial_input = {
            "user_prompt": message,  # This now includes document content if a document was provided
            "section_text": s_text,
            "section_title": s_title,
            "section_number": section_number,
            "rough_draft_path": str(draft_path)
        }
    
        # Step 6: Process through graph and capture the final state
        state = None
        try:
            print(graph.get_graph().draw_mermaid())

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

            # Step 7: Build initial response data
            # Note: The AI's response and the modified section text may reflect 
            # information from both the user's prompt and any document content
            response_data = {
                "success": True,
                "message": "Processing completed",
                "ai_message": state.get("ai_message"),
                "modified_section_text": state.get("modified_section_text"),
                "section_number": section_number,  # Include section number in response
                "section_title": s_title  # Include section title in response
            }

            # WebSocket: Send final state
            # await websocket.send_json({"type": "final_state", "content": response_data})

            print("\nConstructing response with state data:")
            print(f"AI Message: {response_data['ai_message']}")
            print(f"Modified text present: {bool(response_data['modified_section_text'])}")

            # Step 8: Handle file processing for successful state
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


@app.post("/publish")
async def publish(update_request: PublishInput):
    """
    API to update a specific section in the docx_file.
    """
    try:
        # Step 1: Extract input parameters
        modified_text = update_request.modified_text
        section_number = update_request.section_number
        # modified_text = update_request.get("modified_section_text")
        # section_number = update_request.get("section_number")

        if not modified_text or not section_number:
            raise HTTPException(
                status_code=400,
                detail="Both 'modified_section_text' and 'section_number' are required"
            )

        # Step 2: Dynamically load config and get paths
        CURRENT_FILE = Path(__file__).resolve()
        SAGAN_ROOT = CURRENT_FILE.parent.parent.parent
        CONFIG_PATH = SAGAN_ROOT / "config.py"
        
        spec = importlib.util.spec_from_file_location("config", CONFIG_PATH)
        config = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(config)

        updated_paths = config.update_project_paths(project_id)
        
        # Step 3: File paths
        docx_file = updated_paths['output_docx']

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
# async def interact(message: str = Form(...)):
#     """
#     Endpoint to interact with the graph using user input with streaming response.
#     """
#     if not message:
#         raise HTTPException(status_code=400, detail="No input provided")
# 
#     try:
#         # Stream the responses from the graph
#         async def event_generator():
#             initial_input = {"messages": [("user", message)]}
#             for response in graph.stream(initial_input, stream_mode="values", config=runnable_config):
#                 yield f"data: {response}\n\n"
# 
#         return StreamingResponse(event_generator(), media_type="text/event-stream")
# 
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8001)






