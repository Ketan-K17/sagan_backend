from typing import Dict
from pathlib import Path

def get_project_paths(project_id: str, projects_base: Path) -> Dict[str, Path]:
    """
    Get all paths for a specific project.
    
    Args:
        project_id (str): Unique identifier for the project
        
    Returns:
        Dict[str, Path]: Dictionary of project-specific paths
    """
    if not project_id:
        raise ValueError("Project ID cannot be empty")
    
    PROJECTS_BASE = projects_base
        
    project_root = PROJECTS_BASE / project_id
    print("GET_PROJECT_PATHS: generating paths for project: ", project_id)
    
    # Define project-specific paths
    paths = {
        "root": project_root,
        "data": project_root / "data",
        "vectordb": project_root / "vectordb",
        "template": project_root / "template",
        "workflow1_output": project_root / "workflow1_output",
        "workflow2_output": project_root / "workflow2_output",
        "state": project_root / "state.json",
        "nodewise_output": project_root / "workflow1_output" / "nodewise_output",
        "retrieved_images": project_root / "workflow1_output" / "retrieved_images",
        "output_docx": project_root / "workflow1_output" / "output.docx"
    }
    
    print("GET_PROJECT_PATHS: generated ", len(paths), " paths for project ", project_id)
    return paths