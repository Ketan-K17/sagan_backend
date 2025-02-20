import json
from pathlib import Path
import os
import certifi 

current_project_id = None

# ----------- importing project id ---------------
# import sagan
# project_id = sagan.project_id
# -------------------------------------------------

# Base paths
# PROJECT_ROOT = Path(__file__).parent # i.e. spaider_agent_temp
# SAGAN_ROOT = PROJECT_ROOT.parent.parent # i.e. sagan_smolagents
SAGAN_ROOT = Path(__file__).parent # i.e. sagan_smolagents
FIRST_WORKFLOW_ROOT = SAGAN_ROOT / "sagan_workflow" / "spaider_agent_temp"
SECOND_WORKFLOW_ROOT = SAGAN_ROOT / "sagan_workflow_refiner" / "spaider_agent_temp"

# template file path
# TEMPLATE_FILE_PATH = SAGAN_ROOT / "fnr_template" / "template.docx"

# Database paths
# VECTOR_DB_PATHS = {
#     'astro_db': SAGAN_ROOT / "ingest_data" / "astroaidb",
#     'fnr_template_db': SAGAN_ROOT / "ingest_data" / "fnr_template_db",
#     'astro_ai2': SAGAN_ROOT / "ingest_data" / "astroai2",
#     'astro_ai3': SAGAN_ROOT / "ingest_data" / "astroai3"
# }

# Input paths
# INPUT_PDF_FOLDER = SAGAN_ROOT / "data"

# ----- output paths for OLD, FIXED workflow
# OUTPUT_BASE = FIRST_WORKFLOW_ROOT # i.e. sagan_workflow/spaider_agent_temp
# OUTPUT_PDF_PATH = OUTPUT_BASE / "output_pdf"
# RETRIEVED_IMAGES_PATH = OUTPUT_BASE / "retrieved_images"
# OUTPUT_DOCX_PATH = OUTPUT_PDF_PATH / "output.docx"
# NODEWISE_OUTPUT_PATH = OUTPUT_PDF_PATH / "nodewise_output"
# ------------------------------------

# Environment file
ENV_PATH = SAGAN_ROOT / ".env"

MODEL_SETTINGS = {
    'NOMIC_EMBED': "nomic-ai/nomic-embed-text-v1",
    'SENTENCE_TRANSFORMER': "sentence-transformers/all-MiniLM-L6-v2",
    'DEFAULT_K': 3,
    'MIN_RELEVANCE_SCORE': 0.5
}

# SSL Certificate path
#SSL_CERT_PATH = Path(os.getenv('SSL_CERT_FILE', '')) or Path(os.path.expanduser('~')) / "AppData/Local/.certifi/cacert.pem"
SSL_CERT_PATH = Path(certifi.where())



##### ------------PROJECTS ---------------
PROJECTS_BASE = SAGAN_ROOT / "projects"

# project_root = PROJECTS_BASE / project_id


def update_project_paths(project_id: str) -> dict:
    """
    Updates all project-specific paths based on the provided project_id and returns them.
    
    Args:
        project_id (str): The project ID to use for path updates
        
    Returns:
        dict: Dictionary containing all updated paths
    """
    global current_project_id
    current_project_id = project_id
    
    paths = {}
    
    # Update paths that need to be project-specific
    if project_id:
        project_root = PROJECTS_BASE / project_id
        paths['project_root'] = project_root
        
        # Update vector DB paths
        global VECTOR_DB_PATHS
        VECTOR_DB_PATHS = {
            'data_db': project_root / "vectordb" / "data_db",
            'template_db': project_root / "vectordb" / "template_db",
        }
        paths['vector_db_paths'] = VECTOR_DB_PATHS

        MODEL_SETTINGS = {
            'NOMIC_EMBED': "nomic-ai/nomic-embed-text-v1",
            'SENTENCE_TRANSFORMER': "sentence-transformers/all-MiniLM-L6-v2",
            'DEFAULT_K': 3,
            'MIN_RELEVANCE_SCORE': 0.5
        }
        paths['model_settings'] = MODEL_SETTINGS
        
        # Update input/output paths
        global INPUT_PDF_FOLDER, TEMPLATE_FOLDER, FIRST_WORKFLOW_OUTPUT_FOLDER, SECOND_WORKFLOW_OUTPUT_FOLDER, RETRIEVED_IMAGES_PATH
        global OUTPUT_DOCX_PATH, NODEWISE_OUTPUT_PATH
        
        INPUT_PDF_FOLDER = project_root / "data"
        TEMPLATE_FOLDER = project_root / "template"
        FIRST_WORKFLOW_OUTPUT_FOLDER = project_root / "workflow1_output"
        SECOND_WORKFLOW_OUTPUT_FOLDER = project_root / "workflow2_output"
        RETRIEVED_IMAGES_PATH = FIRST_WORKFLOW_OUTPUT_FOLDER / "retrieved_images"
        OUTPUT_DOCX_PATH = FIRST_WORKFLOW_OUTPUT_FOLDER / "output.docx"
        NODEWISE_OUTPUT_PATH = FIRST_WORKFLOW_OUTPUT_FOLDER / "nodewise_output"
        
        # Add all paths to return dictionary
        paths.update({
            'input_pdf_folder': INPUT_PDF_FOLDER,
            'template_folder': TEMPLATE_FOLDER,
            'workflow1_output': FIRST_WORKFLOW_OUTPUT_FOLDER,
            'workflow2_output': SECOND_WORKFLOW_OUTPUT_FOLDER,
            'retrieved_images': RETRIEVED_IMAGES_PATH,
            'output_docx': OUTPUT_DOCX_PATH,
            'nodewise_output': NODEWISE_OUTPUT_PATH
        })
        
    return paths

# def get_current_project_id():
#     """Returns the currently active project_id"""
#     return current_project_id



def get_current_project_id():
    """Returns the currently active project_id"""
    # Read project_id from cookie.json
    try:
        cookie_path = SAGAN_ROOT / 'cookie.json'
        with open(cookie_path, 'r') as f:
            cookie_data = json.load(f)
            current_project_id = cookie_data.get('project_id')
    except:
        pass
    return current_project_id

def create_directories():
    """Create all necessary directories if they don't exist."""
    # Only create project-specific directories if a project is active
    if current_project_id is None:
        return
        
    directories = [
        FIRST_WORKFLOW_OUTPUT_FOLDER,
        SECOND_WORKFLOW_OUTPUT_FOLDER,
        RETRIEVED_IMAGES_PATH,
        FIRST_WORKFLOW_OUTPUT_FOLDER / "images",
        SECOND_WORKFLOW_OUTPUT_FOLDER / "images",
        TEMPLATE_FOLDER,
        INPUT_PDF_FOLDER,
        NODEWISE_OUTPUT_PATH,
        TEMPLATE_FOLDER,
        VECTOR_DB_PATHS["data_db"],
        VECTOR_DB_PATHS["template_db"],
    ]
    
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)

def verify_paths():
    """Verify that all required paths exist."""
    required_paths = {
        "ENV_PATH": ENV_PATH,
        **{f"VECTOR_DB_{k.upper()}": v for k, v in VECTOR_DB_PATHS.items()},
        "SSL_CERT_PATH": SSL_CERT_PATH
    }
    
    missing_paths = []
    for name, path in required_paths.items():
        if not path.exists():
            missing_paths.append(f"{name}: {path}")
    
    if missing_paths:
        print("Warning: The following paths do not exist:")
        for path in missing_paths:
            print(f"  - {path}")
    
    return len(missing_paths) == 0

def print_project_paths():
    print("\n=== SAGAN Path Configuration ===\n")
    
    print("=== Root Paths ===")
    print(f"SAGAN_ROOT: {SAGAN_ROOT}")
    print(f"FIRST_WORKFLOW_ROOT: {FIRST_WORKFLOW_ROOT}")
    print(f"SECOND_WORKFLOW_ROOT: {SECOND_WORKFLOW_ROOT}")
    
    print("\n=== Template Path ===")
    print(f"TEMPLATE_FOLDER: {TEMPLATE_FOLDER}")
    
    print("\n=== Vector Database Paths ===")
    for db_name, db_path in VECTOR_DB_PATHS.items():
        print(f"{db_name}: {db_path}")
    
    print("\n=== Input/Output Paths ===")
    print(f"INPUT_PDF_FOLDER: {INPUT_PDF_FOLDER}")
    print(f"FIRST_WORKFLOW_OUTPUT_FOLDER: {FIRST_WORKFLOW_OUTPUT_FOLDER}")
    print(f"SECOND_WORKFLOW_OUTPUT_FOLDER: {SECOND_WORKFLOW_OUTPUT_FOLDER}")
    print(f"RETRIEVED_IMAGES_PATH: {RETRIEVED_IMAGES_PATH}")
    print(f"OUTPUT_DOCX_PATH: {OUTPUT_DOCX_PATH}")
    print(f"NODEWISE_OUTPUT_PATH: {NODEWISE_OUTPUT_PATH}")
    
    print("\n=== Environment and SSL Paths ===")
    print(f"ENV_PATH: {ENV_PATH}")
    print(f"SSL_CERT_PATH: {SSL_CERT_PATH}")
    
    print("\n=== Project Paths ===")
    print(f"PROJECTS_BASE: {PROJECTS_BASE}")
    if current_project_id:
        print(f"Current Project ID: {current_project_id}")
        print(f"Current Project Path: {PROJECTS_BASE / current_project_id}")
    else:
        print("No active project")
    
    print("\n=== Path Verification ===")
    missing = []
    for path_name, path in {
        "SAGAN_ROOT": SAGAN_ROOT,
        "TEMPLATE_FOLDER": TEMPLATE_FOLDER,
        "INPUT_PDF_FOLDER": INPUT_PDF_FOLDER,
        "FIRST_WORKFLOW_OUTPUT_FOLDER": FIRST_WORKFLOW_OUTPUT_FOLDER,
        "SECOND_WORKFLOW_OUTPUT_FOLDER": SECOND_WORKFLOW_OUTPUT_FOLDER,
        "RETRIEVED_IMAGES_PATH": RETRIEVED_IMAGES_PATH,
        "OUTPUT_DOCX_PATH": OUTPUT_DOCX_PATH,
        "NODEWISE_OUTPUT_PATH": NODEWISE_OUTPUT_PATH,
        "ENV_PATH": ENV_PATH,
        "SSL_CERT_PATH": SSL_CERT_PATH,
        "PROJECTS_BASE": PROJECTS_BASE
    }.items():
        exists = path.exists()  
        status = "✓" if exists else "✗"
        print(f"{status} {path_name}: {path}")
        if not exists:
            missing.append(path_name)
    
    if missing:
        print("\nWarning: The following paths do not exist:")
        for path in missing:
            print(f"  - {path}")
    else:
        print("\nAll core paths exist!")

# Remove or modify the auto-creation at import
# Instead of:
# create_directories()
# You might want to do:
if current_project_id:
    create_directories()


if __name__ == "__main__":
    print_project_paths()