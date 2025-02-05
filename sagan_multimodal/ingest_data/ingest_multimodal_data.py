import os
import fitz
import torch
from PIL import Image
import io
from typing import List, Dict
from transformers import AutoModel, AutoImageProcessor
from langchain_community.vectorstores import Chroma
from langchain.embeddings.base import Embeddings
from langchain.schema import Document
from pathlib import Path
import tempfile
import shutil
from tqdm import tqdm

class NomicVisionEmbeddings(Embeddings):
    def __init__(self, model_name: str = "nomic-ai/nomic-embed-vision-v1.5"):
        print(f"Loading model {model_name}...")
        self.processor = AutoImageProcessor.from_pretrained(model_name, trust_remote_code=True)
        self.model = AutoModel.from_pretrained(model_name, trust_remote_code=True)
        if torch.cuda.is_available():
            self.model = self.model.to('cuda')
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        print(f"Using device: {self.device}")

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed search docs."""
        # Since we already have pre-computed embeddings, this won't be used
        return [[0.0] * 768] * len(texts)  # Return dummy embeddings

    def embed_query(self, text: str) -> List[float]:
        """Embed query text."""
        # Since we already have pre-computed embeddings, this won't be used
        return [0.0] * 768  # Return dummy embeddings

class PrecomputedEmbeddings(Embeddings):
    def __init__(self, embeddings_list: List[List[float]]):
        self.embeddings = embeddings_list
        self.current_idx = 0

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Return precomputed embeddings."""
        batch_embeddings = self.embeddings[self.current_idx:self.current_idx + len(texts)]
        self.current_idx += len(texts)
        return batch_embeddings

    def embed_query(self, text: str) -> List[float]:
        """Embed query text."""
        # For query time, we'll need to implement proper embedding
        raise NotImplementedError("Query embedding not implemented")

class NomicVisionProcessor:
    def __init__(self, model_name: str = "nomic-ai/nomic-embed-vision-v1.5"):
        print(f"Loading model {model_name}...")
        self.processor = AutoImageProcessor.from_pretrained(model_name, trust_remote_code=True)
        self.model = AutoModel.from_pretrained(model_name, trust_remote_code=True)
        if torch.cuda.is_available():
            self.model = self.model.to('cuda')
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        self.image_dir = "extracted_images"
        os.makedirs(self.image_dir, exist_ok=True)
        print(f"Using device: {self.device}")

    def embed_image(self, image: Image.Image) -> List[float]:
        """Generate embedding for an image."""
        inputs = self.processor(images=image, return_tensors="pt")
        if self.device == 'cuda':
            inputs = {k: v.to('cuda') for k, v in inputs.items()}
        
        with torch.no_grad():
            outputs = self.model(**inputs)
            embedding = outputs.last_hidden_state.mean(dim=1).cpu().numpy()
        
        return embedding[0].tolist()

    def process_pdf(self, pdf_path: str) -> List[Dict]:
        """Extract and process images from PDF."""
        doc = fitz.open(pdf_path)
        items = []
        
        for page_num in tqdm(range(len(doc)), desc=f"Processing pages from {os.path.basename(pdf_path)}"):
            page = doc[page_num]
            
            # Extract images
            image_list = page.get_images()
            for img_idx, img in enumerate(image_list):
                try:
                    xref = img[0]
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image["image"]
                    
                    # Save image to disk
                    image_filename = f"{os.path.basename(pdf_path)}_page{page_num}_img{img_idx}.png"
                    image_path = os.path.join(self.image_dir, image_filename)
                    
                    with open(image_path, 'wb') as img_file:
                        img_file.write(image_bytes)
                    
                    # Create embedding for image
                    image = Image.open(io.BytesIO(image_bytes)).convert('RGB')
                    embedding = self.embed_image(image)
                    
                    items.append({
                        'content_type': 'image',
                        'content': image_path,
                        'embedding': embedding,
                        'metadata': {
                            'source_pdf': pdf_path,
                            'page_num': page_num,
                            'image_index': img_idx,
                            'type': 'image'
                        }
                    })
                    print(f"Processed image {img_idx} from page {page_num}")
                except Exception as e:
                    print(f"Error processing image {img_idx} on page {page_num}: {str(e)}")
                    continue
        
        return items

def process_pdf_folder(input_folder: str, persist_dir: str):
    """Process all PDFs in a folder and create vector store."""
    processor = NomicVisionProcessor()
    documents = []
    embeddings_list = []
    
    pdf_files = list(Path(input_folder).rglob("*.pdf"))
    print(f"Found {len(pdf_files)} PDF files")
    
    for pdf_path in pdf_files:
        print(f"\nProcessing {pdf_path}")
        try:
            items = processor.process_pdf(str(pdf_path))
            
            for item in items:
                doc = Document(
                    page_content=item['content'],
                    metadata=item['metadata']
                )
                documents.append(doc)
                embeddings_list.append(item['embedding'])
        except Exception as e:
            print(f"Error processing {pdf_path}: {str(e)}")
            continue
    
    if not documents:
        print("No documents were processed successfully.")
        return None
        
    print(f"\nCreating vector store with {len(documents)} documents...")
    
    # Create embedding function with precomputed embeddings
    embedding_func = PrecomputedEmbeddings(embeddings_list)
    
    # Create vector store
    vector_store = Chroma.from_documents(
        documents=documents,
        embedding=embedding_func,
        persist_directory=persist_dir
    )
    
    return vector_store

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Create vector database from PDF files')
    parser.add_argument("--persist-dir", required=True, 
                      help="Directory to store vector database")
    parser.add_argument("--input-folder", required=True,
                      help="Input folder containing PDFs")
    
    args = parser.parse_args()
    
    print("Creating vector database...")
    vector_store = process_pdf_folder(args.input_folder, args.persist_dir)
    if vector_store is not None:
        vector_store.persist()
        print("Done!")
    else:
        print("Failed to create vector store - no documents were processed successfully.")

if __name__ == "__main__":
    main()