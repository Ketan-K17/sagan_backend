import chromadb
import os
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

def check_db():
    db_path = config.VECTOR_DB_PATHS['astro_ai2']
    
    print(f"Checking database at: {db_path}")
    print(f"Path exists: {os.path.exists(db_path)}")
    
    try:
        client = chromadb.PersistentClient(path=db_path)
        collections = client.list_collections()
        print(f"\nFound collections: {len(collections)}")
        
        for collection in collections:
            print(f"\nCollection: {collection.name}")
            print(f"Count: {collection.count()}")
            
            # Try to peek at the data
            try:
                peek = collection.peek()
                print(f"Sample data available: {bool(peek)}")
            except Exception as e:
                print(f"Error peeking collection: {e}")
                
    except Exception as e:
        print(f"Error accessing database: {e}")
        import traceback
        print(traceback.format_exc())

if __name__ == "__main__":
    check_db() 