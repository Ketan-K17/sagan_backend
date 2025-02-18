from datetime import datetime
import json
from typing import Dict, List, Optional
from pathlib import Path
import shutil
from tkinter import Tk, filedialog
from colorama import Fore, Style, init


import config_utils
import config
import ingest_data.ingest_data as ingest_data

chunk_settings = {
            "data_db": {
                "chunk_size": 256,
                "chunk_overlap": 50
            },
            "template_db": {
                "chunk_size": 128,  # Smaller chunks for template
                "chunk_overlap": 24
            }
                }

def create_project_id():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    project_id = f"project_{timestamp}"
    return project_id

def update_state(state_path: Path, updates: Dict):
    """Update state with new information"""
    with open(state_path) as f:
        state = json.load(f)
    
    # Deep update state
    for key, value in updates.items():
        if isinstance(value, dict) and key in state:
            state[key].update(value)
        else:
            state[key] = value
            
    state["last_modified"] = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    save_state(state_path, state)
    

def save_state(state_path: str, state: Dict):
        """Save project state to JSON file"""
        # Ensure parent directory exists
        Path(state_path).parent.mkdir(parents=True, exist_ok=True)
        
        with open(state_path, "w") as f:
            json.dump(state, f, indent=2)


def create_new_project(name: str) -> Dict:
        """Create new project structure"""
        project_id = create_project_id()
        timestamp = project_id.replace("project_", "")  # Extract timestamp from project_id


        # Get paths first
        paths = config_utils.get_project_paths(project_id, config.PROJECTS_BASE)
        
        # Create directories
        for path in paths.values():
            if isinstance(path, Path) and not path.suffix:
                path.mkdir(parents=True, exist_ok=True)
        
        state = {
            "project_id": project_id,
            "name": name,
            "created_at": timestamp,
            "last_modified": timestamp,
            "paths": {k: str(v) for k, v in paths.items()},  # Convert paths to strings
            "workflows_completed": []
        }
        # Save state file explicitly
        state_path = paths["state"]
        with open(state_path, 'w') as f:
            json.dump(state, f, indent=4)

        return state


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


def create_data_vectordb(project_id: str, files: List[Path]) -> bool:
        """Create vector database for input data files"""
        paths = config_utils.get_project_paths(project_id, config.PROJECTS_BASE)
        
        try:
            # Copy files to data directory
            data_dir = paths["data"]
            data_dir.mkdir(parents=True, exist_ok=True)
            
            processed_files = []
            failed_files = []
            
            for file in files:
                try:
                    if not file.exists():
                        failed_files.append(file.name)
                        continue
                    
                    target_path = data_dir / file.name
                    shutil.copy2(file, target_path)
                    processed_files.append(file.name)

                except Exception as e:
                    failed_files.append(file.name)

            if not processed_files:
                print("No files were successfully copied")
                return False

            # Create vector database
            vectordb_dir = paths["vectordb"] / "data_db"
            vectordb_dir.mkdir(parents=True, exist_ok=True)

            ingest_data.create_vectordb(
                data_folder=str(data_dir),
                persist_folder=str(vectordb_dir),
                chunk_size=chunk_settings["data_db"]["chunk_size"],
                chunk_overlap=chunk_settings["data_db"]["chunk_overlap"]
            )

            update_state(paths["state"], {
                "vectordb": {
                    "data": str(vectordb_dir),
                    "files": processed_files
                }
            })

        except Exception as e:
            print(f"Failed to create data vectordb: {e}")
            return False
        

def create_template_vectordb(project_id: str, template_file: Path) -> bool:
        """Create vector database for template file"""
        paths = config_utils.get_project_paths(project_id, config.PROJECTS_BASE)
        
        try:
            # Copy template to template directory
            template_dir = paths["template"]
            template_dir.mkdir(parents=True, exist_ok=True)
            
            target_path = template_dir / template_file.name
            shutil.copy2(template_file, target_path)
            print(f"Copied template: {template_file} to {target_path}")

            # Create vector database
            vectordb_dir = paths["vectordb"] / "template_db"
            vectordb_dir.mkdir(parents=True, exist_ok=True)

            ingest_data.create_vectordb(
                data_folder=str(template_dir),
                persist_folder=str(vectordb_dir),
                chunk_size=chunk_settings["template_db"]["chunk_size"],
                chunk_overlap=chunk_settings["template_db"]["chunk_overlap"]
            )

            # Update state
            update_state(paths["state"], {
                "vectordb": {
                    "template": str(vectordb_dir),
                    "template_file": str(target_path)
                }
            })
            return True

        except Exception as e:
            print(f"Failed to create template vectordb: {e}")
            return False
        

def update_vectordb(project_id: str, files: List[Path]) -> bool:
        """Update vector database with new files."""
        print(f"Updating vector database for project: {project_id}")
        paths = config_utils.get_project_paths(project_id, config.PROJECTS_BASE)
        
        try:
            # Track successful and failed files
            processed_files = []
            failed_files = []
            
            # Copy files to project data directory
            data_dir = paths["data"]
            data_dir.mkdir(parents=True, exist_ok=True)
            
            # Only process new files that don't already exist
            for file in files:
                try:
                    if not file.exists():
                        print(f"Source file not found: {file}")
                        failed_files.append(file.name)
                        continue
                    
                    target_path = data_dir / file.name
                    if target_path.exists():
                        print(f"File already exists, skipping: {file.name}")
                        continue
                        
                    shutil.copy2(file, target_path)
                    print(f"Copied file: {file} to {target_path}")
                    processed_files.append(file.name)
                    
                except Exception as e:
                    print(f"Failed to copy file {file}: {e}")
                    failed_files.append(file.name)
            
            if not processed_files:
                print("No new files to process")
                return True  # Return True since this isn't an error case
                
            # Process only new files and add to existing vectordb
            vectordb_dir = paths["vectordb"] / "data_db"
            vectordb_dir.mkdir(parents=True, exist_ok=True)
            
            # Create temporary folder for new files only
            temp_dir = data_dir / "temp_new_files"
            temp_dir.mkdir(exist_ok=True)
            
            try:
                # Copy new files to temp directory
                for file_name in processed_files:
                    shutil.copy2(data_dir / file_name, temp_dir / file_name)
                
                # Process only new files and add to existing vectordb
                ingest_data.create_vectordb(
                    data_folder=str(temp_dir),
                    persist_folder=str(vectordb_dir),
                    chunk_size=chunk_settings["data_db"]["chunk_size"],
                    chunk_overlap=chunk_settings["data_db"]["chunk_overlap"],
                    update_existing=True  # Flag to indicate we're updating existing vectordb
                )
                
                # Update state with new files
                update_state(paths["state"], {
                    "vectordb": {
                        "data": str(vectordb_dir),
                        "files": processed_files  # Add only new files to state
                    }
                })
                
                print("Vector database updated successfully")
                print(f"Successfully processed: {', '.join(processed_files)}")
                if failed_files:
                    print(f"Failed to process: {', '.join(failed_files)}")
                    
                return True
                
            except Exception as e:
                print(f"Vector database update failed: {e}")
                return False
                
            finally:
                # Clean up temp directory
                if temp_dir.exists():
                    shutil.rmtree(temp_dir)
                    
        except Exception as e:
            print(f"Failed to update vector database: {e}")
            return False
        

class UIHandler:
    """Handles all user interface operations."""
    
    @staticmethod
    def select_files(title: str, filetypes: list) -> list:
        """Show file selection dialog."""
        print(f"Opening file selection dialog: {title}")
        root = Tk()
        root.withdraw()
        try:
            files = filedialog.askopenfilenames(
                title=title,
                filetypes=filetypes
            )
            selected_files = [Path(f) for f in files]
            print(f"Selected files: {selected_files}")
            return selected_files
        finally:
            root.destroy()
            
    @staticmethod
    def select_template() -> Optional[Path]:
        """Select template file"""
        root = Tk()
        root.withdraw()
        try:
            file = filedialog.askopenfilename(
                title="Select project template",
                filetypes=[("Word files", "*.docx")]
            )
            return Path(file) if file else None
        finally:
            root.destroy()

def handle_project_choice(project_id: str):
    """Handle project menu choices"""
    # Show file selection dialog for new files
    files = UIHandler.select_files(
        "Select files to add to vector database",
        [
            ('PDF files', '*.pdf'),
            ('Text files', '*.txt'),
            ('Word files', '*.docx'),
            ('CSV files', '*.csv')
        ]
    )
    if files:
        print(f"\n{Fore.YELLOW}Updating vector database...{Style.RESET_ALL}")
        if update_vectordb(project_id, files):
            print(f"{Fore.GREEN}Vector database updated successfully!{Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}Failed to update vector database.{Style.RESET_ALL}")


if __name__ == "__main__":
    projects = get_all_projects()
    for key, value in projects.items():
        print(f"{key.upper()}:")
        for sub_key, sub_value in value.items():
            print(f"  {sub_key.upper()}: {sub_value}")