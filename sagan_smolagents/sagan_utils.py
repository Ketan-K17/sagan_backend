from datetime import datetime
import json
from typing import Dict

import config_utils

def create_project_id():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    project_id = f"project_{timestamp}"
    return project_id


def create_new_project(name: str) -> Dict:
        """Create new project structure"""
        project_id = create_project_id()
        
        try:
            # Get paths first
            paths = config_utils.get_project_paths(project_id, config.PROJECTS_BASE)
            
            # Create directories
            for path in paths.values():
                if isinstance(path, Path) and not path.suffix:
                    path.mkdir(parents=True, exist_ok=True)
                    logger.debug(f"Created directory: {path}")
            
            state = {
                "project_id": project_id,
                "name": name,
                "created_at": timestamp,
                "last_modified": timestamp,
                "paths": {k: str(v) for k, v in paths.items()},  # Convert paths to strings
                "workflows_completed": []
            }
            
            self._save_state(paths["state"], state)
            return state
            
        except Exception as e:
            logger.error(f"Failed to create project: {e}")
            raise


def get_all_projects() -> Dict:
    """Returns a dictionary of project_id -> project_state.json"""
    projects = {}
            
        # List all project directories
    for path in config.PROJECTS_BASE.glob("project_*"):
        if not path.is_dir():
            continue
            
        state_file = path / "state.json"
    
        if state_file.exists():
            with open(state_file) as f:
                state = json.load(f)
                projects[path.name] = state

    return projects


if __name__ == "__main__":
    projects = get_all_projects()
    for key, value in projects.items():
        print(f"{key.upper()}:")
        for sub_key, sub_value in value.items():
            print(f"  {sub_key.upper()}: {sub_value}")