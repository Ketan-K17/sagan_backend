from dotenv import load_dotenv
import os
import certifi
import ssl
import openai
from openai import OpenAI
from langchain_openai import ChatOpenAI
import shutil
from pathlib import Path
import importlib.util

# Dynamically resolve the path to config.py
CURRENT_FILE = Path(__file__).resolve()
SAGAN_MULTIMODAL = CURRENT_FILE.parent.parent.parent
CONFIG_PATH = SAGAN_MULTIMODAL / "config.py"

# Load config.py dynamically
spec = importlib.util.spec_from_file_location("config", CONFIG_PATH)
config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config)

# Verify paths at startup
if not config.verify_paths():
    print("Warning: Some required paths are missing. Please check config.py")

# Load environment variables from .env
load_dotenv(dotenv_path=config.ENV_PATH)

# Set up SSL certificate
try:
    # Use certifi's default certificate
    default_cert = certifi.where()
    ssl_cert_path = str(config.SSL_CERT_PATH)
    
    # Create directory if it doesn't exist
    os.makedirs(os.path.dirname(ssl_cert_path), exist_ok=True)
    
    # Copy the certificate to our location with proper permissions
    shutil.copy2(default_cert, ssl_cert_path)
    os.chmod(ssl_cert_path, 0o644)  # Set read permissions
    
    # Set environment variables
    os.environ['SSL_CERT_FILE'] = ssl_cert_path
    os.environ['REQUESTS_CA_BUNDLE'] = ssl_cert_path
    os.environ['CURL_CA_BUNDLE'] = ssl_cert_path
    
except Exception as e:
    print(f"Warning: Could not set up SSL certificate: {e}")
    print("Falling back to certifi's default certificate")
    os.environ['SSL_CERT_FILE'] = certifi.where()
    os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
    os.environ['CURL_CA_BUNDLE'] = certifi.where()

# Configure OpenAI
api_key = os.getenv('OPENAI_API_KEY')
if not api_key:
    raise ValueError("OPENAI_API_KEY not found in environment variables")

# Create and configure the ChatOpenAI instance
llm = ChatOpenAI(
    openai_api_key=api_key,
    model_name="gpt-4",
    temperature=0.7,
    request_timeout=30,
    max_retries=3
)

# Add this to verify the configuration
print(f"Using SSL cert path: {os.environ['SSL_CERT_FILE']}")
print(f"API Key configured: {'Yes' if api_key else 'No'}")

# Rest of your imports
from langchain_core.runnables.config import RunnableConfig
from graph import create_graph, compile_graph, print_stream

# Your existing configuration
config = RunnableConfig(
    recursion_limit=50,
    configurable={
        "thread_id": "1",
        "llm": llm
    }
)

if __name__ == "__main__":
    builder = create_graph()
    graph = compile_graph(builder)
    print(graph.get_graph().draw_mermaid())
    
    user_input = input("############# User: ")
    print_stream(graph.stream({"user_prompt": user_input}, stream_mode="values", config=config))
