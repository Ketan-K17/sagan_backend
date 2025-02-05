from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from typing import Dict, Any
import datetime
from pathlib import Path
import json
import os
import sys
import shutil
import importlib.util

# Get the path to the spaider_agent_temp directory
CURRENT_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
SPAIDER_AGENT_TEMP_DIR = CURRENT_DIR.parent

# Import using relative imports
sys.path.append(str(SPAIDER_AGENT_TEMP_DIR))
from schemas import State

# Dynamically resolve the path to config.py
CURRENT_FILE = Path(__file__).resolve()
SAGAN_MULTIMODAL = CURRENT_FILE.parent.parent.parent.parent
CONFIG_PATH = SAGAN_MULTIMODAL / "config.py"

# Load config.py dynamically
spec = importlib.util.spec_from_file_location("config", CONFIG_PATH)
config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config)


# print the state in the node_test scripts in a readable format.
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

# saves the state in outputpdf/nodewise_output in .txt format (to be read by human) and .json format (to be read by machine to reconstruct state)
def save_state_for_testing(state: State, node_name: str, output_dir: Path = config.NODEWISE_OUTPUT_PATH):
    """
    Save the state in a format suitable for testing.
    Creates both a human-readable and a machine-readable version.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save machine-readable JSON version
    json_path = output_dir / f"{node_name}_state.json"
    serialized_state = serialize_state(state, node_name)
    with json_path.open('w', encoding='utf-8') as f:
        json.dump(serialized_state, f, indent=2, ensure_ascii=False)
    
    # Save human-readable text version
    txt_path = output_dir / f"{node_name}.txt"
    with txt_path.open('w', encoding='utf-8') as f:
        f.write(f"{node_name.upper()} OUTPUT:\n")
        f.write("=" * 80 + "\n\n")
        
        # Write state fields excluding messages
        f.write("STATE FIELDS:\n")
        f.write("-" * 40 + "\n")
        for field_name, field_value in state.items():
            if field_name != "messages":
                f.write(f"{field_name.upper()}: {field_value}\n")
        
        # Write messages separately for better readability
        f.write("\nMESSAGE HISTORY:\n")
        f.write("-" * 40 + "\n")
        for msg in state.get("messages", []):
            f.write(f"{(msg.type).upper()}: {msg.content}\n")
            if msg.additional_kwargs:
                f.write(f"Additional kwargs: {msg.additional_kwargs}\n")
            f.write("-" * 20 + "\n")


# reconstructs the state for a given node, given its .json file in outputpdf/nodewise_output
def load_state_for_testing(node_name: str, output_dir: Path = config.   NODEWISE_OUTPUT_PATH) -> State:
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