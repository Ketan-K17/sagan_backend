from langchain_chroma import Chroma
from langchain_community.embeddings.sentence_transformer import SentenceTransformerEmbeddings
from typing import List, Dict

def query_chromadb(chroma_db_path: str, llm_name: str, user_query: str) -> List[str]:
    """
    Query Chroma DB and retrieve documents based on user query.
    
    Args:
        chroma_db_path: Path to the Chroma DB directory.
        llm_name: Embedding model name.
        user_query: User query.
    
    Returns:
        List[Dict]: Retrieved documents with page content and metadata.
    """
    # Initialize the embedding function
    embedding_function = SentenceTransformerEmbeddings(model_name=llm_name)
    
    # Load Chroma DB from disk
    db = Chroma(persist_directory=chroma_db_path, embedding_function=embedding_function)
    
    # Perform similarity search
    docs = db.similarity_search(user_query, k=10)
    
    # Convert documents to dictionary format
    result = [doc.page_content for doc in docs]

    return result

# # Example usage:
# if __name__ == "__main__":
#     chroma_db_path = "C:/Users/ketan/Desktop/SPAIDER-SPACE/sagan_workflow/ingest_data/mychroma_db"
#     llm_name = "sentence-transformers/all-MiniLM-L6-v2"
#     user_query = "Describe the knowledgebase."
    
#     retrieved_docs = query_chromadb(chroma_db_path, llm_name, user_query)
    
#     for i, doc in enumerate(retrieved_docs, 1):
#         print(f"Document {i}:")
#         print(f"Content: {doc}...")  # Print first 100 characters
#         print()
