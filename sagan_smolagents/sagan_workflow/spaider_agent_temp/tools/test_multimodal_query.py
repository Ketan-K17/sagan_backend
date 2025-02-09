import json
import sys
import os
from multimodal_query import NomicVisionQuerier
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
import importlib.util

# Dynamically resolve the path to config.py
CURRENT_FILE = Path(__file__).resolve()
SAGAN_MULTIMODAL = CURRENT_FILE.parent.parent.parent.parent
CONFIG_PATH = SAGAN_MULTIMODAL / "config.py"

# Load config.py dynamically
spec = importlib.util.spec_from_file_location("config", CONFIG_PATH)
config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config)

# Initialize the querier
querier = NomicVisionQuerier()

# Query the vector database
results = querier.multimodal_vectordb_query(
    persist_dir=config.VECTOR_DB_PATHS['astro_ai2'],
    query="Show me comparison of Computational Density Per Watt of State-of-the-art Rad-Hard Processors",
    k=5,
)

# Print the results (structured output)
print(results)

# Optionally save results to a JSON file
with open("query_results.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=4)
