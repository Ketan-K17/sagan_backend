from pathlib import Path
from config import (
    FIRST_WORKFLOW_ROOT,
    SECOND_WORKFLOW_ROOT,
    SAGAN_ROOT,
    VECTOR_DB_PATHS,
    OUTPUT_BASE,
    OUTPUT_PDF_PATH,
    RETRIEVED_IMAGES_PATH,
    TEX_OUTPUT_PATH,
    PDF_OUTPUT_PATH,
    MD_OUTPUT_PATH,
    ENV_PATH,
    SSL_CERT_PATH,
    create_directories
)

def print_path_info(name: str, path: Path):
    """Print information about a path"""
    print(f"\n{name}:")
    print(f"  Absolute path: {path.absolute()}")
    print(f"  Exists: {path.exists()}")
    if path.exists():
        print(f"  Type: {'Directory' if path.is_dir() else 'File'}")
        if path.is_dir():
            try:
                contents = list(path.iterdir())
                print(f"  Contains {len(contents)} items")
                if contents:
                    print("  First few items:")
                    for item in contents[:3]:
                        print(f"    - {item.name}")
            except PermissionError:
                print("  Cannot list contents (Permission denied)")
    print(f"  Parent exists: {path.parent.exists()}")

def test_paths():
    print("Testing all paths from config...\n")
    
    print("=== Base Paths ===")
    print_path_info("FIRST_WORKFLOW_ROOT", FIRST_WORKFLOW_ROOT)
    print_path_info("SECOND_WORKFLOW_ROOT", SECOND_WORKFLOW_ROOT)
    print_path_info("SAGAN_ROOT", SAGAN_ROOT)
    
    print("\n=== Database Paths ===")
    for name, path in VECTOR_DB_PATHS.items():
        print_path_info(f"VECTOR_DB_{name.upper()}", path)
    
    print("\n=== Output Paths ===")
    print_path_info("OUTPUT_BASE", OUTPUT_BASE)
    print_path_info("OUTPUT_PDF_PATH", OUTPUT_PDF_PATH)
    print_path_info("RETRIEVED_IMAGES_PATH", RETRIEVED_IMAGES_PATH)
    print_path_info("TEX_OUTPUT_PATH", TEX_OUTPUT_PATH)
    print_path_info("PDF_OUTPUT_PATH", PDF_OUTPUT_PATH)
    print_path_info("MD_OUTPUT_PATH", MD_OUTPUT_PATH)
    
    print("\n=== Configuration Files ===")
    print_path_info("ENV_PATH", ENV_PATH)
    print_path_info("SSL_CERT_PATH", SSL_CERT_PATH)
    
    print("\n=== Testing Directory Creation ===")
    print("Creating directories...")
    create_directories()
    print("Checking created directories...")
    for path in [OUTPUT_PDF_PATH, RETRIEVED_IMAGES_PATH, OUTPUT_PDF_PATH / "images"]:
        exists = path.exists()
        is_dir = path.is_dir()
        print(f"{path.name}: {'✓' if exists and is_dir else '✗'} ({'exists' if exists else 'missing'}, {'directory' if is_dir else 'not directory'})")

if __name__ == "__main__":
    test_paths()