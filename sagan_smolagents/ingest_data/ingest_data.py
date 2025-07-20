import os
import sys
from typing import Optional
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import (
    PyPDFLoader,
    TextLoader,
    CSVLoader,
    Docx2txtLoader,
    UnstructuredMarkdownLoader,
)
from langchain.document_loaders.base import BaseLoader

def load_documents(data_folder: str) -> list:
    """
    Load documents from the data folder.
    Supported file types: PDF, TXT, CSV, DOCX, MD.
    """
    supported_extensions = {
        ".pdf": PyPDFLoader,
        ".txt": TextLoader,
        ".csv": CSVLoader,
        ".docx": Docx2txtLoader,
        ".md": UnstructuredMarkdownLoader,
    }
    documents = []

    for root, _, files in os.walk(data_folder):
        for file in files:
            file_path = os.path.join(root, file)
            ext = os.path.splitext(file)[-1].lower()

            if ext in supported_extensions:
                try:
                    loader: BaseLoader = supported_extensions[ext](file_path)
                    docs = loader.load()
                    documents.extend(docs)
                    print(f"Loaded {len(docs)} document(s) from {file_path}")
                except Exception as e:
                    print(f"Error loading {file_path}: {e}")
            else:
                print(f"Unsupported file type: {file_path}")

    return documents


def create_vectordb(
    data_folder: str,
    persist_folder: str,
    chunk_size: int,
    chunk_overlap: int,
    embedding_model: Optional[str] = "sentence-transformers/all-MiniLM-L6-v1",
    update_existing: bool = False
):
    """Create or update a vector database from the documents in the data folder."""
    # Step 1: Load documents
    documents = load_documents(data_folder)

    if not documents:
        print("No documents found. Exiting.")
        return

    # Step 2: Split documents into chunks
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, chunk_overlap=chunk_overlap
    )
    chunks = text_splitter.split_documents(documents)
    print(f"Split {len(documents)} documents into {len(chunks)} chunks.")

    # Step 3: Initialize embedding model
    try:
        embeddings = HuggingFaceEmbeddings(model_name=embedding_model)
        print(f"Using embedding model: {embedding_model}")
    except Exception as e:
        print(f"Error initializing embedding model: {e}")
        return

    # Step 4: Create or update the vector database
    try:
        if update_existing and os.path.exists(persist_folder):
            # Load existing vectordb
            vectordb = Chroma(
                persist_directory=persist_folder,
                embedding_function=embeddings
            )
            # Add new documents
            vectordb.add_documents(chunks)
        else:
            # Create new vectordb
            vectordb = Chroma.from_documents(
                documents=chunks,
                embedding=embeddings,
                persist_directory=persist_folder
            )
        
        vectordb.persist()
        print(f"Vector database {'updated' if update_existing else 'created'} and persisted at: {persist_folder}")
        return True
    except Exception as e:
        print(f"Error {'updating' if update_existing else 'creating'} vector database: {e}")
        return False


if __name__ == "__main__":
    # Parse inputs
    if len(sys.argv) < 5:
        print(
            "Usage: python script.py <data_folder> <persist_folder> <chunk_size> <chunk_overlap> [embedding_model]"
        )
        sys.exit(1)

    data_folder = sys.argv[1]
    persist_folder = sys.argv[2]
    chunk_size = int(sys.argv[3])
    chunk_overlap = int(sys.argv[4])
    embedding_model = sys.argv[5] if len(sys.argv) > 5 else "sentence-transformers/all-MiniLM-L6-v1"

    # Validate inputs
    if not os.path.isdir(data_folder):
        print(f"Data folder does not exist: {data_folder}")
        sys.exit(1)

    if not os.path.exists(persist_folder):
        os.makedirs(persist_folder, exist_ok=True)

    # Create vector database
    create_vectordb(data_folder, persist_folder, chunk_size, chunk_overlap, embedding_model)