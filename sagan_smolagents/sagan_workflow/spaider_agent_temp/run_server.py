# import os
# from pyngrok import ngrok
# import uvicorn
# from fastapi import FastAPI, File, UploadFile, HTTPException, Request
# from pydantic import BaseModel
# from fastapi.responses import StreamingResponse, JSONResponse
# from fastapi.middleware.cors import CORSMiddleware
# import nest_asyncio
# from pathlib import Path
# import base64
# import subprocess
# from langchain_core.runnables.config import RunnableConfig
# from graph import create_graph, compile_graph, print_stream
# from dotenv import load_dotenv

# load_dotenv()

# # Initialize FastAPI
# app = FastAPI()

# # Add CORS middleware
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# # Setup data folders
# DATA_FOLDER = Path("testfolder")
# DATA_FOLDER.mkdir(exist_ok=True)

# DATA_RFP_FOLDER = Path("testfolder")
# DATA_RFP_FOLDER.mkdir(exist_ok=True)

# # Initialize graph (assuming these are imported from your existing code)
# verbose = True
# builder = create_graph()
# graph = compile_graph(builder)

# config = RunnableConfig(
#     recursion_limit=50,
#     configurable={"thread_id": "1"}
# )

# class UserInput(BaseModel):
#     message: str

# @app.post("/process-input")
# async def process_input(user_input: UserInput):
#     try:   
#         print(f"Processing input: {user_input.message}")
        
#         # Run the graph
#         _ = list(graph.stream(
#             {"messages": [("user", user_input.message)]}, 
#             stream_mode="values", 
#             config=config
#         ))

#         # Setup paths
#         project_root = Path(__file__).parent.parent
#         output_dir = project_root / "spaider_agent_temp" / "output_pdf"
#         tex_file = output_dir / "output.tex"
#         pdf_file = output_dir / "output.pdf"
#         md_file = output_dir / "output.md"
        
#         output_dir.mkdir(parents=True, exist_ok=True)

#         if not tex_file.exists():
#             raise HTTPException(status_code=404, detail=f"LaTeX file not found")

#         # Run pdflatex
#         for i in range(3):
#             process = subprocess.run([
#                 'pdflatex',
#                 '-interaction=nonstopmode',
#                 f'-output-directory={str(output_dir)}',
#                 str(tex_file)
#             ], check=True, capture_output=True, text=True)

#         if not pdf_file.exists():
#             raise HTTPException(status_code=404, detail="PDF generation failed")

#         # Convert to Markdown
#         from utils.latex_to_markdown import create_markdown_pipeline
#         md_pipeline = create_markdown_pipeline()
#         md_result = md_pipeline.convert_latex_to_markdown(str(tex_file), str(output_dir))

#         # Read files
#         with open(tex_file, 'r', encoding='utf-8') as f:
#             latex_content = f.read()

#         with open(pdf_file, 'rb') as f:
#             pdf_content = base64.b64encode(f.read()).decode('utf-8')

#         markdown_content = None
#         if md_result["success"] and md_result["markdown_content"]:
#             with open(md_file, 'w', encoding='utf-8') as f:
#                 f.write(md_result["markdown_content"])
#             with open(md_file, 'r', encoding='utf-8') as f:
#                 markdown_content = f.read()

#         response_data = {
#             "tex_file": latex_content,
#             "pdf_file": pdf_content,
#             "md_file": markdown_content,
#             "success": True,
#             "file_paths": {
#                 "tex": str(tex_file),
#                 "pdf": str(pdf_file),
#                 "md": str(md_file) if markdown_content else None
#             }
#         }

#         if not markdown_content:
#             response_data["markdown_error"] = md_result.get("error", "Unknown conversion error")

#         # Cleanup auxiliary files
#         aux_extensions = ['.aux', '.log', '.out', '.fls', '.fdb_latexmk', '.synctex.gz']
#         for ext in aux_extensions:
#             aux_file = output_dir / f"output{ext}"
#             if aux_file.exists():
#                 aux_file.unlink()

#         return JSONResponse(response_data)

#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))

# @app.post("/interact")
# async def interact(user_input: UserInput):
#     message = user_input.message
    
#     if not message:
#         raise HTTPException(status_code=400, detail="No input provided")

#     try:
#         async def event_generator():
#             for response in graph.stream(
#                 {"messages": [("user", message)]}, 
#                 stream_mode="values", 
#                 config=config
#             ):
#                 yield f"data: {response}\n\n"

#         return StreamingResponse(event_generator(), media_type="text/event-stream")

#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))

# # if __name__ == "__main__":
# #     # Set your auth token from https://dashboard.ngrok.com/get-started/your-authtoken
# #     ngrok.set_auth_token("YOUR_NGROK_AUTH_TOKEN")
    
# #     # Initialize
# #     nest_asyncio.apply()
# #     http_tunnel = ngrok.connect(8000)
# #     print(f"Public URL: {http_tunnel.public_url}")
    
# #     # Run the server
# #     uvicorn.run(app, host="127.0.0.1", port=8000)
    
# if __name__ == "__main__":
#     # Get token from environment
#     auth_token = os.getenv('NGROK_AUTH_TOKEN')
#     if not auth_token:
#         raise ValueError("NGROK_AUTH_TOKEN not found in .env file")
    
#     ngrok.set_auth_token(auth_token)
#     nest_asyncio.apply()
#     http_tunnel = ngrok.connect(8000)
#     print(f"Public URL: {http_tunnel.public_url}")
    
#     # uvicorn.run(app, host="127.0.0.1", port=8000)

import os
from pyngrok import ngrok
import uvicorn
from fastapi import FastAPI, File, UploadFile, HTTPException, Request
from pydantic import BaseModel
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import nest_asyncio
from pathlib import Path
import base64
import subprocess
from langchain_core.runnables.config import RunnableConfig
from graph import create_graph, compile_graph, print_stream
from dotenv import load_dotenv

load_dotenv()

# Initialize FastAPI
app = FastAPI()

# Detailed CORS configuration
origins = [
    "http://localhost:5174",
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5174",
    "http://127.0.0.1:5173",
    "*"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,  # Set to False when using wildcard "*"
    allow_methods=["GET", "POST", "OPTIONS", "DELETE", "PATCH", "PUT"],
    allow_headers=["Content-Type", "Authorization", "Accept", "Origin", "X-Requested-With"],
    expose_headers=["Content-Length", "Content-Range"],
    max_age=3600,
)

# Setup data folders
DATA_FOLDER = Path("testfolder")
DATA_FOLDER.mkdir(exist_ok=True)

DATA_RFP_FOLDER = Path("testfolder")
DATA_RFP_FOLDER.mkdir(exist_ok=True)

# Initialize graph
verbose = True
builder = create_graph()
graph = compile_graph(builder)

config = RunnableConfig(
    recursion_limit=50,
    configurable={"thread_id": "1"}
)

class UserInput(BaseModel):
    message: str

@app.options("/{full_path:path}")
async def options_handler():
    return JSONResponse(
        content="OK",
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization, Accept, Origin, X-Requested-With",
        },
    )

@app.get("/")
async def root():
    return {"message": "API is running. Use /process-input or /interact endpoints"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.post("/process-input")
async def process_input(user_input: UserInput):
    try:   
        print(f"Processing input: {user_input.message}")
        
        # Run the graph
        _ = list(graph.stream(
            {"messages": [("user", user_input.message)]}, 
            stream_mode="values", 
            config=config
        ))

        # Setup paths
        project_root = Path(__file__).parent.parent
        output_dir = project_root / "spaider_agent_temp" / "output_pdf"
        tex_file = output_dir / "output.tex"
        pdf_file = output_dir / "output.pdf"
        md_file = output_dir / "output.md"
        
        output_dir.mkdir(parents=True, exist_ok=True)

        if not tex_file.exists():
            raise HTTPException(status_code=404, detail=f"LaTeX file not found")

        # Run pdflatex
        for i in range(3):
            process = subprocess.run([
                'pdflatex',
                '-interaction=nonstopmode',
                f'-output-directory={str(output_dir)}',
                str(tex_file)
            ], check=True, capture_output=True, text=True)

        if not pdf_file.exists():
            raise HTTPException(status_code=404, detail="PDF generation failed")

        # Convert to Markdown
        from utils.latex_to_markdown import create_markdown_pipeline
        md_pipeline = create_markdown_pipeline()
        md_result = md_pipeline.convert_latex_to_markdown(str(tex_file), str(output_dir))

        # Read files
        with open(tex_file, 'r', encoding='utf-8') as f:
            latex_content = f.read()

        with open(pdf_file, 'rb') as f:
            pdf_content = base64.b64encode(f.read()).decode('utf-8')

        markdown_content = None
        if md_result["success"] and md_result["markdown_content"]:
            with open(md_file, 'w', encoding='utf-8') as f:
                f.write(md_result["markdown_content"])
            with open(md_file, 'r', encoding='utf-8') as f:
                markdown_content = f.read()

        response_data = {
            "tex_file": latex_content,
            "pdf_file": pdf_content,
            "md_file": markdown_content,
            "success": True,
            "file_paths": {
                "tex": str(tex_file),
                "pdf": str(pdf_file),
                "md": str(md_file) if markdown_content else None
            }
        }

        if not markdown_content:
            response_data["markdown_error"] = md_result.get("error", "Unknown conversion error")

        # Cleanup auxiliary files
        aux_extensions = ['.aux', '.log', '.out', '.fls', '.fdb_latexmk', '.synctex.gz']
        for ext in aux_extensions:
            aux_file = output_dir / f"output{ext}"
            if aux_file.exists():
                aux_file.unlink()

        return JSONResponse(response_data)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/interact")
async def interact(user_input: UserInput):
    message = user_input.message
    
    if not message:
        raise HTTPException(status_code=400, detail="No input provided")

    try:
        async def event_generator():
            for response in graph.stream(
                {"messages": [("user", message)]}, 
                stream_mode="values", 
                config=config
            ):
                yield f"data: {response}\n\n"

        return StreamingResponse(
            event_generator(), 
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*"
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    # Start uvicorn first
    uvicorn_server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=8000))
    
    # Start ngrok after server is running
    auth_token = os.getenv('NGROK_AUTH_TOKEN')
    if not auth_token:
        raise ValueError("NGROK_AUTH_TOKEN not found in .env file")
    
    ngrok.set_auth_token(auth_token)
    http_tunnel = ngrok.connect(8000)
    print(f"Public URL: {http_tunnel.public_url}")
    
    # Run server
    uvicorn_server.run()