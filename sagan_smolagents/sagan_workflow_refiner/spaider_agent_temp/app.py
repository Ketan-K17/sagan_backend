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


# def extract_section(draft_path: str, section_number: int) -> tuple[str, str]:
#     """
#     Extract section title and text from a markdown file based on section number.
#     Returns a tuple of (section_title, section_text).
#     """
#     with open(draft_path, 'r', encoding='utf-8') as file:
#         content = file.read()
    
#     # Remove any content before the first section
#     if '# ' in content:
#         content = content[content.find('# '):]
    
#     # Split the content into sections based on level 1 headers
#     sections = content.split('\n# ')
#     if sections[0].startswith('# '):  # Handle first section if it starts with #
#         sections[0] = sections[0][2:]
    
#     # Ensure section number is valid
#     if section_number < 1 or section_number > len(sections):
#         raise ValueError(f"Section number {section_number} is out of range. File has {len(sections)} sections.")
    
#     # Get the requested section
#     section = sections[section_number - 1]
    
#     # Split into title and content, handling subsections
#     section_parts = section.split('\n', 1)
#     section_title = section_parts[0].split(':', 1)[1].strip() if ':' in section_parts[0] else section_parts[0].strip()
#     section_text = section_parts[1].strip() if len(section_parts) > 1 else ""
    
#     return section_title, section_text


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



# if __name__ == "__main__":
#     # creating graph workflow instance and then compiling it.
#     verbose = True
#     builder = create_graph()
#     graph = compile_graph(builder)


#     draft_path = config.TEX_OUTPUT_PATH
#     section_number = 1
        
#     s_title, s_text = extract_section(draft_path, section_number)

#     # printing the graph.
#     print(graph.get_graph().draw_mermaid())

#     # research_query_generator_prompt = RESEARCH_QUERY_GENERATOR_PROMPT.format(
#     #     section_title=s_title,
#     #     section_text=s_text
#     # )

#     user_prompt = f"""
#     Section Title: {s_title}
#     Section Text: {s_text}
#     """
#     combined_prompt = RESEARCH_QUERY_GENERATOR_PROMPT + "\n" + user_prompt

#     user_input = input("############# User: ")
#     initial_input = {
#         "messages": [SystemMessage(content=combined_prompt), HumanMessage(content=user_input)],
#         "section_text": s_text,
#         "section_title": s_title,
#         "section_number": section_number,
#         "rough_draft_path": draft_path
#     }

#     print_stream(graph.stream(initial_input, stream_mode="values", config=runnable_config))

#     user_approval = input("Save changes to the section text? (yes/no): ")
#     if user_approval.lower() == "yes":
#         # If approved, continue the graph execution
#         for event in graph.stream(None, config=runnable_config, stream_mode="values"):
#             event['messages'][-1].pretty_print()
            
#     else:
#         print("Changes not saved.")

# # Use the function to get section title and text
# try:
#     s_title, s_text = extract_section(draft_path, section_number)
# except Exception as e:
#     print(f"Error extracting section: {e}")
#     s_title, s_text = "", ""

# Add at the end of file, replacing the existing main block
if __name__ == "__main__":
    async def main():
        verbose = True
        builder = create_graph()
        graph = compile_graph(builder)

        draft_path = config.TEX_OUTPUT_PATH
        section_number = 1
        
        s_title, s_text = extract_section(draft_path, section_number)
        print(graph.get_graph().draw_mermaid())

        user_prompt = f"""
        Section Title: {s_title}
        Section Text: {s_text}
        """
        combined_prompt = RESEARCH_QUERY_GENERATOR_PROMPT + "\n" + user_prompt

        user_input = input("############# User: ")
        initial_input = {
            "messages": [SystemMessage(content=combined_prompt), HumanMessage(content=user_input)],
            "section_text": s_text,
            "section_title": s_title,
            "section_number": section_number,
            "rough_draft_path": draft_path
        }

        async for s in graph.astream(initial_input, stream_mode="values", config=runnable_config):
            print_stream([s])

    import asyncio
    asyncio.run(main())