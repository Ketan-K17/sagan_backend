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

# Import LaTeX and Markdown conversion utilities
from utils.latex_to_markdown import create_markdown_pipeline
from utils.latextopdf import LaTeXPipeline
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

MODEL = "gpt-4o"
# llm = BuildChatGroq(model=MODEL, temperature=0)
llm = BuildChatOpenAI(model=MODEL, temperature=0)
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
builder = create_graph()
graph = compile_graph(builder)

# Configure runnable
runnable_config = RunnableConfig(
    recursion_limit=50,
    configurable={"thread_id": "1"}
)

def extract_section(draft_path: str, section_number: int) -> tuple[str, str]:
    """
    Extract section title and text from a LaTeX file based on section number.
    Returns a tuple of (section_title, section_text).
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
        with open(draft_path, 'r', encoding='utf-8') as file:
            content = file.read()

        # Extract content between \begin{document} and \end{document}
        doc_match = re.search(r'\\begin{document}(.*?)\\end{document}', content, re.DOTALL)
        if not doc_match:
            raise ValueError("Could not find document environment in LaTeX file")
        
        main_content = doc_match.group(1)

        # Find all sections
        sections = []
        section_titles = []
        
        # Regular expression for section commands
        section_pattern = r'\\section\{([^}]+)\}'
        
        # Find all section positions
        section_matches = list(re.finditer(section_pattern, main_content))
        
        if not section_matches:
            # Handle case with no sections
            return "", clean_latex_command(main_content)
        
        # Process each section
        for i, match in enumerate(section_matches):
            section_start = match.start()
            section_end = section_matches[i + 1].start() if i < len(section_matches) - 1 else len(main_content)
            
            # Extract title and content
            section_content = main_content[section_start:section_end]
            title_match = re.search(section_pattern, section_content)
            
            if title_match:
                title = clean_latex_command(title_match.group(1))
                # Get content after the section command
                content_start = title_match.end()
                content = section_content[content_start:].strip()
                
                section_titles.append(title)
                sections.append(clean_latex_command(content))

        # Validate section number
        if section_number < 1 or section_number > len(sections):
            raise ValueError(f"Section number {section_number} is out of range. File has {len(sections)} sections.")

        # Get the requested section
        section_index = section_number - 1
        return section_titles[section_index], sections[section_index]

    except FileNotFoundError:
        raise FileNotFoundError(f"LaTeX file not found: {draft_path}")
    except Exception as e:
        raise ValueError(f"Error processing LaTeX file: {str(e)}")
    


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
        tex_file = output_dir / "output.tex"
        pdf_file = output_dir / "output.pdf"
        md_file = output_dir / "output.md"
        # Ensure output directory exists
        output_dir.mkdir(parents=True, exist_ok=True)

        # Step 3: Extract section if section number and draft path are provided
        if user_input.section_number:
            draft_path = tex_file  # Using tex_file as draft path
            s_title, s_text = extract_section(str(draft_path), user_input.section_number)
            research_query_generator_prompt = RESEARCH_QUERY_GENERATOR_PROMPT.format(
                section_title=s_title,
                section_text=s_text
            )

            initial_input = {
                "messages": [
                    SystemMessage(content=research_query_generator_prompt),
                    HumanMessage(content=user_input.message)
                ],
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
                print("Save was successful, processing PDF and Markdown conversions...")

                # Verify files exist
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

                print("Both files exist, proceeding with markdown conversion")

                # Convert to Markdown
                md_pipeline = create_markdown_pipeline()
                md_result = md_pipeline.convert_latex_to_markdown(str(tex_file), str(output_dir))

                try:
                    # Read LaTeX content
                    with open(tex_file, 'r', encoding='utf-8') as f:
                        latex_content = f.read()
                    print("Successfully read LaTeX content")

                    # Read PDF content
                    with open(pdf_file, 'rb') as f:
                        pdf_content = base64.b64encode(f.read()).decode('utf-8')
                    print("Successfully read PDF content")

                    # Handle Markdown content
                    markdown_content = None
                    if md_result["success"]:
                        markdown_content = md_result["markdown_content"]
                        # Save to file
                        with open(md_file, 'w', encoding='utf-8') as f:
                            f.write(markdown_content)
                        print("Successfully created Markdown file")

                    # Update response data with file information
                    response_data.update({
                        "tex_file": latex_content,
                        "pdf_file": pdf_content,
                        "md_file": markdown_content,
                        "file_paths": {
                            "tex": str(tex_file),
                            "pdf": str(pdf_file),
                            "md": str(md_file) if markdown_content else None
                        }
                    })

                    if not markdown_content:
                        response_data["markdown_error"] = md_result.get("error", "Unknown conversion error")
                        print(f"Markdown conversion failed: {response_data['markdown_error']}")

                    # Clean up auxiliary files
                    aux_extensions = ['.aux', '.log', '.out', '.fls', '.fdb_latexmk', '.synctex.gz']
                    for ext in aux_extensions:
                        aux_file = output_dir / f"output{ext}"
                        if aux_file.exists():
                            aux_file.unlink()
                    print("Cleaned up auxiliary files")

                except Exception as e:
                    print(f"Error processing output files: {str(e)}")
                    raise HTTPException(
                        status_code=500,
                        detail=f"Error processing output files: {str(e)}"
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
async def publish(update_request:  PublishInput):
    """
    API to update a specific section in the tex_file and regenerate pdf and markdown files.
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
        tex_file = output_dir / "output.tex"
        pdf_file = output_dir / "output.pdf"
        md_file = output_dir / "output.md"

        if not tex_file.exists():
            raise HTTPException(
                status_code=404,
                detail="LaTeX file not found at the specified path"
            )

        # Read the current content of the TeX file
        with open(tex_file, 'r', encoding='utf-8') as f:
            tex_content = f.read()

        # Update the specific section
        doc_start = tex_content.find('\\begin{document}')
        doc_end = tex_content.find('\\end{document}')
        if doc_start == -1 or doc_end == -1:
            raise ValueError("Could not find document environment in LaTeX file")

        preamble = tex_content[:doc_start + len('\\begin{document}')]
        postamble = tex_content[doc_end:]
        main_content = tex_content[doc_start + len('\\begin{document}'):doc_end]

        # Use regex to split the document into sections
        import re
        section_pattern = r'(\\section\{[^}]*\}[\s\S]*?)(?=\\section\{|$)'
        sections = re.findall(section_pattern, main_content)

        # print(sections,"sections 1298")

        # Validate section number
        if section_number < 1 or section_number > len(sections):
            raise ValueError(f"Section number {section_number} is out of range. File has {len(sections)} sections.")

        # Replace the section content while preserving the section command
        section_header_match = re.match(r'(\\section\{[^}]*\})', sections[section_number - 1])
        if section_header_match:
            section_header = section_header_match.group(1)
            sections[section_number - 1] = f"{section_header}\n{modified_text}\n"
        else:
            sections[section_number - 1] = modified_text

        # Reconstruct the document
        new_main_content = ''.join(sections)
        new_tex_content = preamble + new_main_content + postamble

        # Write the updated TeX content back to the file
        with open(tex_file, 'w', encoding='utf-8') as f:
            f.write(new_tex_content)

        print("Updated the TeX file with modified section text.")

        # Ensure the PDF file exists
        if not pdf_file.exists():
            raise HTTPException(
                status_code=404,
                detail="PDF file not found. Ensure LaTeX to PDF conversion is enabled."
            )

        # Markdown conversion

        md_pipeline = create_markdown_pipeline()
        md_result = md_pipeline.convert_latex_to_markdown(str(tex_file), str(output_dir))
        pipeline = LaTeXPipeline()
        pdf_result = pipeline.latex_to_pdf(tex_file, output_dir)
        print(pdf_result,"pdf result 436")

        try:
            # Read LaTeX content
            with open(tex_file, 'r', encoding='utf-8') as f:
                latex_content = f.read()

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
                "message": "Section updated and files regenerated successfully",
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
                detail=f"Error processing output files: {str(e)}"
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






@app.post("/interact")
async def interact(user_input: UserInput):
    """
    Endpoint to interact with the graph using user input with streaming response.
    """
    if not user_input.message:
        raise HTTPException(status_code=400, detail="No input provided")

    try:
        # Stream the responses from the graph
        async def event_generator():
            initial_input = {"messages": [("user", user_input.message)]}
            for response in graph.stream(initial_input, stream_mode="values", config=runnable_config):
                yield f"data: {response}\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8002)






