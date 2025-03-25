from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from typing import Dict, Any
import datetime
from pathlib import Path
import json
import os
import sys
import shutil
import importlib.util
from types import ModuleType

# Local imports
from schemas import State

# helper function to load the config.py file dynamically
def load_config_file() -> ModuleType:
    # Dynamically resolve the path to config.py
    CURRENT_FILE = Path(__file__).resolve()
    project_root = CURRENT_FILE.parent.parent.parent.parent
    CONFIG_PATH = project_root / "config.py"
    # Load config.py dynamically
    spec = importlib.util.spec_from_file_location("config", CONFIG_PATH)
    config = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config)
    return config

# Get the path to the spaider_agent_temp directory
CURRENT_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
SPAIDER_AGENT_TEMP_DIR = CURRENT_DIR.parent
sys.path.append(str(SPAIDER_AGENT_TEMP_DIR))

configfile = load_config_file()

# getting project_id from cookie.json
CURRENT_FILE = Path(__file__).resolve()
project_root = CURRENT_FILE.parent.parent.parent.parent

# getting project_id from cookie.json
with open(project_root / "cookie.json", "r") as f:
    cookie_data = json.load(f)
    current_project_id = cookie_data.get("project_id")


def print_state(state):
    """Print the state in a human-readable format."""
    print("STATE:")
    print("=" * 40)
    for key, value in state.items():
        if key == "messages":
            print(f"{key.upper()}:")
            for msg in value:
                print(f"  - {(msg.type).upper()}: {msg.content}")
        else:
            print(f"{key.upper()}: {value}")
    print("=" * 40)


def serialize_message(msg):
    """Helper function to serialize a message object."""
    if isinstance(msg, (SystemMessage, HumanMessage, AIMessage, ToolMessage)):
        serialized = {
            'type': msg.type,
            'content': msg.content,
            'additional_kwargs': msg.additional_kwargs,
        }
        # Add response_metadata for AIMessage
        if isinstance(msg, AIMessage) and hasattr(msg, 'response_metadata'):
            serialized['response_metadata'] = msg.response_metadata
        return serialized
    return str(msg)

# helper fn for save_state_for_testing
def serialize_state(state: State, node_name: str) -> Dict[str, Any]:
    """
    Serialize the state object into a JSON-compatible dictionary.
    Handles special cases like message objects and includes metadata.
    """
    serialized = {
        'metadata': {
            'node_name': node_name,
            'timestamp': str(datetime.datetime.now()),
        },
        'state': {}
    }
    
    for key, value in state.items():
        if key == 'messages':
            serialized['state'][key] = [serialize_message(msg) for msg in value]
        elif isinstance(value, (list, dict, str, int, float, bool, type(None))):
            serialized['state'][key] = value
        else:
            # For other types, convert to string representation
            serialized['state'][key] = str(value)
    
    return serialized


def save_state_for_testing(state: State, node_name: str):
    """
    Save the state in .json format so it can be reused.
    """
    configfile = load_config_file()

    current_project_id = configfile.get_current_project_id()
    updated_paths = configfile.update_project_paths(current_project_id)
    
    # Use the path from config
    output_dir = updated_paths['nodewise_output']
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save machine-readable JSON version
    json_path = output_dir / f"{node_name}_state.json"
    serialized_state = serialize_state(state, node_name)
    with json_path.open('w', encoding='utf-8') as f:
        json.dump(serialized_state, f, indent=2, ensure_ascii=False)


# reconstructs the state for a given node, given its .json file in outputpdf/nodewise_output
def load_state_for_testing(node_name: str, output_dir: Path = None) -> State:
    """
    Load a previously saved state for testing purposes.
    Reconstructs the full State object with proper message types and metadata.
    """
    
    json_path = output_dir / f"{node_name}_state.json"
    if not json_path.exists():
        raise FileNotFoundError(f"No saved state found for node: {node_name}")
    
    with json_path.open('r', encoding='utf-8') as f:
        data = json.load(f)
    
    state_dict = data['state']
    
    # Reconstruct message objects with full metadata
    if 'messages' in state_dict:
        messages = []
        for msg_data in state_dict['messages']:
            msg_type = msg_data['type']
            content = msg_data['content']
            additional_kwargs = msg_data.get('additional_kwargs', {})
            response_metadata = msg_data.get('response_metadata', {})
            
            # Create appropriate message object based on type
            if msg_type == 'system':
                msg = SystemMessage(
                    content=content,
                    additional_kwargs=additional_kwargs
                )
            elif msg_type == 'human':
                msg = HumanMessage(
                    content=content,
                    additional_kwargs=additional_kwargs
                )
            elif msg_type == 'ai':
                # For AI messages, include response_metadata
                msg = AIMessage(
                    content=content,
                    additional_kwargs=additional_kwargs,
                    response_metadata=response_metadata
                )
            elif msg_type == 'tool':
                msg = ToolMessage(
                    content=content,
                    additional_kwargs=additional_kwargs
                )
            else:
                continue  # Skip unknown message types
                
            messages.append(msg)
        
        state_dict['messages'] = messages
    
    # Create and return State object with all fields from the original state
    return State(**state_dict)


# Helper function to copy figures
def copy_figures(source_dir: Path, dest_dir: Path):
    """Copy all figures from the source directory to the destination directory."""
    for item in source_dir.glob("figures/*"):
        if item.is_file():
            shutil.copy(item, dest_dir / item.name)