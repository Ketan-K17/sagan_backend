#!/usr/bin/env python3
"""
Simple driver component that creates the langgraph graph object and prints the mermaid diagram.
"""

from dotenv import load_dotenv
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

# Load environment variables
load_dotenv(dotenv_path=config.ENV_PATH)

# Import the graph creation functions
from graph import create_graph, compile_graph

def main():
    """
    Main driver function that creates the graph and prints the mermaid diagram.
    """
    print("Creating langgraph graph object...")
    
    # Create the graph builder
    builder = create_graph()
    
    # Compile the graph
    graph = compile_graph(builder)
    
    print("Graph created successfully!")
    print("\nMermaid diagram representation:")
    print("=" * 50)
    
    # Print the mermaid diagram
    print(graph.get_graph().draw_mermaid())
    
    print("=" * 50)
    print("Driver execution completed.")

if __name__ == "__main__":
    main() 