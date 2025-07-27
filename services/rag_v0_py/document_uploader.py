#!/usr/bin/env python

import asyncio
import os
import uuid
from typing import List, Dict, Optional
from pathlib import Path
import json
from dotenv import load_dotenv
from loguru import logger

# Import the utility functions from the provided code
from .utils import get_vectors_prefix
from .pinecone_operations import (
    ensure_index_exists, 
    upsert_batch, 
    ingest_embedded_data,
    delete_batch,
    update_metadata_batch
)
from .embedding_operations import (
    create_embeddings_cohere,
    enrich_with_embeddings
)

# Load environment variables
load_dotenv(override=True)

# Required environment variables
PINECONE_API_KEY = os.getenv('PINECONE_API_KEY')
PINECONE_ENVIRONMENT = os.getenv('PINECONE_ENVIRONMENT', 'us-east-1')
COHERE_API_KEY = os.getenv("COHERE_API_KEY")

# Default configuration - can be overridden by environment variables
DEFAULT_INDEX_NAME = os.getenv('PINECONE_INDEX_NAME', 'farmer-voice-index')
DEFAULT_NAMESPACE = os.getenv('PINECONE_NAMESPACE', 'farmer-rag')
DEFAULT_BATCH_SIZE = 100


class DocumentChunker:
    """Handles document chunking for RAG applications."""
    
    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
    
    def chunk_text(self, text: str, doc_id: str) -> List[Dict]:
        """Split text into chunks with metadata.
        
        Args:
            text: The text to chunk
            doc_id: Document identifier
            
        Returns:
            List of chunk dictionaries with metadata
        """
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + self.chunk_size
            
            # If this isn't the last chunk, try to break at a sentence boundary
            if end < len(text):
                # Look for sentence endings within the last 100 characters
                search_start = max(start + self.chunk_size - 100, start)
                for i in range(search_start, end):
                    if text[i] in '.!?':
                        end = i + 1
                        break
            
            chunk_text = text[start:end].strip()
            if chunk_text:
                chunk_id = f"{doc_id}_chunk_{len(chunks) + 1}"
                chunks.append({
                    "id": chunk_id,
                    "text": chunk_text,
                    "doc_id": doc_id,
                    "chunk_index": len(chunks) + 1,
                    "start_char": start,
                    "end_char": end
                })
            
            # Move start position, accounting for overlap
            start = end - self.chunk_overlap
            if start >= len(text):
                break
        
        return chunks


class DocumentUploader:
    """Main class for uploading documents to Pinecone with embeddings."""
    
    def __init__(
        self,
        index_name: str = None,
        namespace: str = None,
        chunk_size: int = 1000,
        chunk_overlap: int = 200
    ):
        # Use provided values or fall back to environment variables
        self.index_name = index_name or DEFAULT_INDEX_NAME
        self.namespace = namespace or DEFAULT_NAMESPACE
        self.chunker = DocumentChunker(chunk_size, chunk_overlap)
        
        # Validate environment variables
        if not PINECONE_API_KEY:
            raise ValueError("PINECONE_API_KEY environment variable is required")
        if not COHERE_API_KEY:
            raise ValueError("COHERE_API_KEY environment variable is required")
        
        # Validate index name and namespace
        if not self.index_name:
            raise ValueError("Index name is required. Set PINECONE_INDEX_NAME environment variable or pass index_name parameter.")
        if not self.namespace:
            raise ValueError("Namespace is required. Set PINECONE_NAMESPACE environment variable or pass namespace parameter.")
        
        # Log the configuration being used
        logger.info(f"DocumentUploader initialized with index: {self.index_name}, namespace: {self.namespace}")
    
    async def upload_text(
        self, 
        text: str, 
        doc_id: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> str:
        """Upload text content to Pinecone with embeddings.
        
        Args:
            text: The text content to upload
            doc_id: Optional document ID (generated if not provided)
            metadata: Optional metadata to attach to all chunks
            
        Returns:
            The document ID used for upload
        """
        if not doc_id:
            doc_id = str(uuid.uuid4())
        
        logger.info(f"Processing document {doc_id} with {len(text)} characters")
        
        # Step 1: Chunk the text
        chunks = self.chunker.chunk_text(text, doc_id)
        logger.info(f"Created {len(chunks)} chunks from document {doc_id}")
        
        # Step 2: Add metadata to chunks
        if metadata:
            for chunk in chunks:
                chunk.update(metadata)
        
        # Step 3: Create embeddings
        enriched_chunks = await enrich_with_embeddings(chunks)
        
        if not enriched_chunks:
            raise Exception("Failed to create embeddings for document chunks")
        
        # Step 4: Upload to Pinecone
        await ingest_embedded_data(
            enriched_chunks,
            self.index_name,
            self.namespace
        )
        
        logger.success(f"Successfully uploaded document {doc_id} with {len(enriched_chunks)} chunks")
        return doc_id
    
    async def upload_file(
        self, 
        file_path: str, 
        doc_id: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> str:
        """Upload a file to Pinecone with embeddings.
        
        Args:
            file_path: Path to the file to upload
            doc_id: Optional document ID (generated if not provided)
            metadata: Optional metadata to attach to all chunks
            
        Returns:
            The document ID used for upload
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        # Read file content
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()
        except UnicodeDecodeError:
            # Try with different encoding
            with open(file_path, 'r', encoding='latin-1') as f:
                text = f.read()
        
        # Add file metadata
        file_metadata = {
            "file_name": file_path.name,
            "file_path": str(file_path),
            "file_size": file_path.stat().st_size,
            "file_extension": file_path.suffix
        }
        
        if metadata:
            file_metadata.update(metadata)
        
        return await self.upload_text(text, doc_id, file_metadata)
    
    async def upload_directory(
        self, 
        directory_path: str,
        file_extensions: Optional[List[str]] = None,
        metadata: Optional[Dict] = None
    ) -> List[str]:
        """Upload all files in a directory to Pinecone.
        
        Args:
            directory_path: Path to the directory
            file_extensions: List of file extensions to process (e.g., ['.txt', '.md'])
            metadata: Optional metadata to attach to all documents
            
        Returns:
            List of document IDs that were uploaded
        """
        directory = Path(directory_path)
        if not directory.exists() or not directory.is_dir():
            raise ValueError(f"Directory not found: {directory_path}")
        
        if file_extensions is None:
            file_extensions = ['.txt', '.md', '.py', '.js', '.ts', '.html', '.css', '.json']
        
        uploaded_docs = []
        
        for file_path in directory.rglob('*'):
            if file_path.is_file() and file_path.suffix.lower() in file_extensions:
                try:
                    doc_id = await self.upload_file(str(file_path), metadata=metadata)
                    uploaded_docs.append(doc_id)
                    logger.info(f"Uploaded {file_path.name} as document {doc_id}")
                except Exception as e:
                    logger.error(f"Failed to upload {file_path}: {e}")
        
        logger.success(f"Uploaded {len(uploaded_docs)} documents from directory {directory_path}")
        return uploaded_docs
    
    async def delete_document(self, doc_id: str) -> None:
        """Delete a document and all its chunks from Pinecone.
        
        Args:
            doc_id: The document ID to delete
        """
        from .pinecone_operations import delete_batch
        
        logger.info(f"Deleting document {doc_id} from namespace {self.namespace}")
        delete_batch(self.index_name, self.namespace, doc_id)
        logger.success(f"Successfully deleted document {doc_id}")
    
    async def update_document_metadata(self, doc_id: str, metadata_delta: Dict) -> None:
        """Update metadata for all chunks of a document.
        
        Args:
            doc_id: The document ID to update
            metadata_delta: Metadata to add/update
        """
        logger.info(f"Updating metadata for document {doc_id}")
        await update_metadata_batch(self.index_name, self.namespace, doc_id, metadata_delta)
        logger.success(f"Successfully updated metadata for document {doc_id}")
    

def load_and_split_document(file_path: str, separator: str = "---") -> list:
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    return [chunk.strip() for chunk in content.split(separator) if chunk.strip()]


async def main():
    """Example usage of the DocumentUploader."""
    
    # Initialize the uploader
    uploader = DocumentUploader(
        index_name="farmer-voice-index",
        namespace="documents"
    )
    
    # Example 1: Upload text
    sample_text = """
    This is a sample document about farming techniques.
    Farmers use various methods to improve crop yields.
    Sustainable farming practices are important for the environment.
    """
    
    doc_id = await uploader.upload_text(
        sample_text,
        metadata={"source": "example", "category": "farming"}
    )
    print(f"Uploaded text document with ID: {doc_id}")
    
    # Example 2: Upload a file
    # doc_id = await uploader.upload_file("path/to/your/document.txt")
    # print(f"Uploaded file document with ID: {doc_id}")
    
    # Example 3: Upload a directory
    # doc_ids = await uploader.upload_directory("path/to/documents")
    # print(f"Uploaded {len(doc_ids)} documents")


if __name__ == "__main__":
    asyncio.run(main()) 
