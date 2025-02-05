import os
import chardet
import argparse
from langchain_community.document_loaders import Docx2txtLoader, TextLoader, CSVLoader, PyMuPDFLoader, PyPDFLoader, UnstructuredPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain.schema import Document
from langchain_huggingface.embeddings import HuggingFaceEmbeddings

# Function to detect the encoding of a file
def detect_encoding(file_path):
    with open(file_path, 'rb') as f: 
        raw_data = f.read()
    result = chardet.detect(raw_data)
    return result['encoding']

# Function to load documents based on file type
def load_document(file):
    name, extension = os.path.splitext(file)
    
    try:
        # Load PDF files using PyMuPDFLoader first, fallback to PyPDFLoader if an error occurs
        if extension == '.pdf': 
            print(f'Loading {file} with UnstructuredPDFLoader')
            try:
                loader = UnstructuredPDFLoader(file)
                data = loader.load()
            except Exception as e:
                print(f'UnstructuredPDFLoader failed for {file}, trying PyMuPDFLoader. Error: {e}')
                try:
                    loader = PyMuPDFLoader(file)
                    data = loader.load()
                except Exception as e:
                    print(f'PyMuPDFLoader failed for {file}, trying PyPDFLoader. Error: {e}')
                    try:
                        loader = PyPDFLoader(file)
                        data = loader.load()
                    except Exception as e:
                        print(f'PyPDFLoader also failed for {file}. Error: {e}')
                        return None
        # Load DOCX files
        elif extension == '.docx': 
            print(f'Loading {file}') 
            loader = Docx2txtLoader(file)
            data = loader.load()
        # Load TXT files
        elif extension == '.txt': 
            loader = TextLoader(file)
            data = loader.load()
        # Load CSV files with detected encoding
        elif extension == '.csv': 
            print(f'Loading {file}')
            encoding = detect_encoding(file)
            loader = CSVLoader(file, encoding=encoding)
            data = loader.load()
        else: 
            print('Document format is not supported!') 
            return None

        return data

    except Exception as e:
        print(f'Error loading {file}: {e}')
        return None

# Function to split data into chunks
def chunk_data(data, chunk_size=512, chunk_overlap=100): 
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap) 
    chunks = text_splitter.split_documents(data) 
    return chunks

# Function to create embeddings and store in Chroma vector store
def create_embeddings(chunks, persist_directory='./mychroma_db'):
    # Specify the model name explicitly to ensure consistency
    # llm_name = "sentence-transformers/all-MiniLM-L6-v2"
    embeddings_model = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
    
    # Debugging: Print model name and persist directory
    # print(f'Using embedding model: {llm_name}')
    print(f'Persist directory: {persist_directory}')

    # Create Chroma vector store with batch processing to avoid exceeding batch size limit
    vector_store = None
    batch_size = 5000
    for i in range(0, len(chunks), batch_size):
        batch_chunks = chunks[i:i+batch_size]
        print(f'Creating embeddings for batch {i // batch_size + 1} / {len(chunks) // batch_size + 1}')
        if vector_store is None:
            vector_store = Chroma.from_documents(batch_chunks, embeddings_model, persist_directory=persist_directory)
        else:
            vector_store.add_documents(batch_chunks)

    # Debugging: Print confirmation message
    print(f'Created Chroma vector store with {len(chunks)} chunks.')
    
    return vector_store

# Function to process all documents in a folder
def process_folder(folder_path, persist_directory='./mychroma_db'):
    all_chunks = []
    for root, _, files in os.walk(folder_path):
        for file in files:
            file_path = os.path.join(root, file)
            data = load_document(file_path)
            if data is not None:
                chunks = chunk_data(data)
                all_chunks.extend(chunks)
    
    # Debugging: Print number of chunks before creating embeddings
    print(f'Total chunks to be embedded: {len(all_chunks)}')
    print(all_chunks[0:20])
    
    vector_store = create_embeddings(all_chunks, persist_directory)

     # Check if vector_store is None
    if vector_store is None:
        print("Error: vector_store is None. Check the create_embeddings function.")
        return  # Exit the function if vector_store is None
    
    # vector_store.persist()
    
    # Debugging: Print final confirmation message
    print(f'Chroma DB has been created and stored at {persist_directory}')

# Example usage
# folder_path = '/mnt/tier2/project/p200475/crewai_app/app_scripts/context_dataset/'  # Replace with your actual folder path
# persist_directory = './mychroma_db'
# process_folder(folder_path, persist_directory)

def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Process documents and create a Chroma vector store.')
    parser.add_argument('--folder-path', 
                        required=True,
                        help='Path to the folder containing documents to process')
    parser.add_argument('--persist-dir', 
                        default='./mychroma_db',
                        help='Directory to store the Chroma database (default: ./mychroma_db)')
    parser.add_argument('--chunk-size', 
                        type=int, 
                        default=512,
                        help='Size of text chunks (default: 512)')
    parser.add_argument('--chunk-overlap', 
                        type=int, 
                        default=100,
                        help='Overlap between chunks (default: 100)')

    # Parse arguments
    args = parser.parse_args()

    # Process the folder
    print(f"Processing documents from: {args.folder_path}")
    print(f"Storing Chroma DB in: {args.persist_dir}")
    print(f"Chunk size: {args.chunk_size}, Chunk overlap: {args.chunk_overlap}")
    
    process_folder(args.folder_path, args.persist_dir)

if __name__ == "__main__":
    main()

# Updated command format:
# python ingest_data.py --folder-path /path/to/your/documents --persist-dir /path/to/store/db --chunk-size 512 --chunk-overlap 100
