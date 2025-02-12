from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.runnables.config import RunnableConfig
from pathlib import Path
import importlib.util
from dotenv import load_dotenv
import os
import certifi
import ssl
from langchain_openai import ChatOpenAI
import shutil
import json

# LOCAL IMPORTS.
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

# Verify paths at startup
if not config.verify_paths():
    print("Warning: Some required paths are missing. Please check config.py")

# Load environment variables from .env
load_dotenv(dotenv_path=config.ENV_PATH)

os.environ['SSL_CERT_FILE'] = certifi.where()


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


def extract_section(draft_path: str, section_number: int) -> tuple[str, str]:
    """
    Extract section title and text from a LaTeX file based on section number.
    Returns a tuple of (section_title, section_text).
    
    Args:
        draft_path (str): Path to the LaTeX file
        section_number (int): The section number to extract (1-based)
        
    Returns:
        tuple[str, str]: A tuple containing (section_title, section_text)
        
    Raises:
        ValueError: If the section number is invalid or if the file is not properly formatted
        FileNotFoundError: If the file doesn't exist
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

runnable_config = RunnableConfig(
    recursion_limit=50,
    configurable={"thread_id": "1"}
)
print(runnable_config)


# Add at the end of file, replacing the existing main block
if __name__ == "__main__":
    async def main():
        builder = create_graph("1234")
        graph = compile_graph(builder)

        draft_path = config.OUTPUT_DOCX_PATH
        section_number = 2

        final_state_path = config.NODEWISE_OUTPUT_PATH / "formatting_node_state.json"
        
        with open(final_state_path, 'r') as f:
            json_data = json.load(f)
            generated_sections = json_data.get('state', {}).get('generated_sections', {})
            
        # Convert section number to corresponding section title and text
        section_titles = list(generated_sections.keys())
        if 1 <= section_number <= len(section_titles):
            s_title = section_titles[section_number - 1]
            s_text = generated_sections[s_title]
        else:
            raise ValueError(f"Section number {section_number} is out of range")
            

        print(graph.get_graph().draw_mermaid())

        print("Chosen section: ", s_title)

        user_input = input("############# User: ")
        initial_input = {
            "user_prompt": user_input,
            "section_text": s_text,
            "section_title": s_title,
            "section_number": section_number,
            "rough_draft_path": draft_path
        }

        async for s in graph.astream(initial_input, stream_mode="values", config=runnable_config):
            print_stream([s])

    import asyncio
    asyncio.run(main())