import os
import sys
import torch
import json
import fitz  # PyMuPDF
from transformers import AutoModel, AutoTokenizer
from langchain_community.vectorstores import Chroma
from langchain.embeddings.base import Embeddings
from typing import List, Dict, Union
from PIL import Image
import io
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


class NomicVisionQuerier(Embeddings):
    def __init__(self, model_name: str = "nomic-ai/nomic-embed-text-v1"):
        print(f"Loading model {model_name}...")
        self.tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
        self.model = AutoModel.from_pretrained(model_name, trust_remote_code=True)
        if torch.cuda.is_available():
            self.model = self.model.to("cuda")
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Using device: {self.device}")
        # Update to use the config path
        self.images_dir = str(config.RETRIEVED_IMAGES_PATH)
        os.makedirs(self.images_dir, exist_ok=True)

    def search_similar(self, persist_dir: str, query: str, k: int = 5) -> Dict[str, List[Dict[str, Union[str, List[str]]]]]:
        try:
            vector_store = Chroma(persist_directory=persist_dir, embedding_function=self)
            results = vector_store.similarity_search_with_relevance_scores(query, k=k)
            print(f"Raw Tool Results: {results}")

            formatted_results = []
            for doc, score_dict in results:
                score = score_dict.get('relevance', 0) if isinstance(score_dict, dict) else score_dict
                metadata = doc.metadata
                content = doc.page_content
                source = metadata.get("source", "Unknown source")
                if source != "Unknown source":
                    pdf_filename = os.path.basename(source)
                    source = str(config.INPUT_PDF_FOLDER / pdf_filename)
                page_num = metadata.get("page", 0)
                images = self.extract_images_from_pdf(source, page_num)
                formatted_results.append({"content": content, "images": images, "score": score})

            return {"Results": formatted_results}
        except Exception as e:
            print(f"Error in search_similar: {e}")
            raise

    def extract_images_from_pdf(self, pdf_path: str, page_num: int) -> List[str]:
        """Extract images from a specific page of a PDF and save them."""
        try:
            doc = fitz.open(pdf_path)
            page = doc[page_num - 1]  # Convert to 0-based index
            image_list = page.get_images()
            saved_images = []

            for img_idx, img in enumerate(image_list):
                try:
                    xref = img[0]
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image["image"]

                    # Generate unique filename
                    image_filename = f"{os.path.basename(pdf_path)}_page{page_num}_img{img_idx}.png"
                    
                    # Save to the actual path from config
                    image_path = config.RETRIEVED_IMAGES_PATH / image_filename

                    # Save image
                    with open(image_path, "wb") as img_file:
                        img_file.write(image_bytes)

                    # Store the absolute path
                    saved_images.append(str(image_path))

                except Exception as e:
                    print(f"Error extracting image {img_idx}: {str(e)}")

            return saved_images
        except Exception as e:
            print(f"Error processing PDF {pdf_path}: {str(e)}")
            return []

    def embed_query(self, query: str) -> List[float]:
        """Generate embeddings for query text."""
        inputs = self.tokenizer(query, return_tensors="pt", padding=True, truncation=True)
        if self.device == "cuda":
            inputs = {k: v.to("cuda") for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self.model(**inputs)
            embedding = outputs.last_hidden_state.mean(dim=1).cpu().numpy()

        return embedding[0].tolist()

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Required by Langchain but not used for querying."""
        return [self.embed_query(text) for text in texts]

    def multimodal_vectordb_query(
        self, persist_dir: str, query: str, k: int = 5
    ) -> Dict[str, List[Dict[str, Union[str, List[str]]]]]:
        """Search for similar items and return results in section_answers schema."""
        vector_store = Chroma(
            persist_directory=persist_dir,
            embedding_function=self,
        )

        print(f"\nProcessing query: {query}\n")

        results = vector_store.similarity_search_with_relevance_scores(query, k=k)

        if not results:
            print("No results found.")
            return {"Results": []}

        formatted_results = []

        for doc, score in results:
            metadata = doc.metadata
            content = doc.page_content
            source = metadata.get("source", "Unknown source")
            if source != "Unknown source":
                pdf_filename = os.path.basename(source)
                source = str(config.INPUT_PDF_FOLDER / pdf_filename)
            page_num = metadata.get("page", 0)

            # Extract images
            images = self.extract_images_from_pdf(source, page_num)

            # Format the result to match section_answers schema
            formatted_results.append({
                "content": content,
                "images": images,
            })

        return {"Results": formatted_results}
    


if __name__ == "__main__":
    # Initialize the querier
    querier = NomicVisionQuerier()

    # Query the vector database
    results = querier.multimodal_vectordb_query(
        persist_dir=str(config.VECTOR_DB_PATHS['astro_ai2']),
        query="Show me comparison of Computational Density Per Watt of State-of-the-art Rad-Hard Processors",
        k=10,
    )

    # Print metadata from all documents
    if results["Results"] and len(results["Results"]) > 0:
        for i, result in enumerate(results["Results"]):
            print(f"\nMetadata from document {i + 1}:")
            print(json.dumps(result, indent=2))