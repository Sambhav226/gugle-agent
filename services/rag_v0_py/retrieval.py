#!/usr/bin/env python

import asyncio
import os
import time
import httpx
from typing import Dict, List, Optional
from dotenv import load_dotenv
from pinecone import Pinecone
from loguru import logger
import traceback
import cohere

# Load environment variables
load_dotenv()

# Constants
COHERE_EMBEDDINGS_BASE_URL = "https://api.cohere.com/v2/embed"
COHERE_RERANK_BASE_URL = "https://api.cohere.com/v1/rerank"
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
COHERE_API_KEY = os.getenv("COHERE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "farmer-voice-index")
PINECONE_NAMESPACE = os.getenv("PINECONE_NAMESPACE", "farmer-rag")
DIMENSION = 1024


class RetrievalService:
    """Retrieval service for RAG applications using Pinecone and Cohere."""
    
    def __init__(self, index_name: Optional[str] = None, namespace: Optional[str] = None):
        """Initialize the retrieval service.
        
        Args:
            index_name: Pinecone index name (defaults to PINECONE_INDEX_NAME env var)
            namespace: Pinecone namespace (defaults to PINECONE_NAMESPACE env var)
        """
        self.index_name = index_name or PINECONE_INDEX_NAME
        self.namespace = namespace or PINECONE_NAMESPACE
        
        # Initialize Pinecone
        self.pc = Pinecone(api_key=PINECONE_API_KEY)
        self.index = self.pc.Index(self.index_name)
        
        # Cohere headers for HTTP API (same as upload process)
        self.cohere_headers = {
            "Authorization": f"Bearer {COHERE_API_KEY}",
            "Content-Type": "application/json",
        }
        
        # Shared HTTP client for better connection reuse
        self._http_client = None
        
        logger.info(f"RetrievalService initialized with index: {self.index_name}, namespace: {self.namespace}")

    async def _get_http_client(self):
        """Get or create shared HTTP client for better connection reuse"""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=30)
        return self._http_client

    async def close(self):
        """Close the HTTP client when done"""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()

    async def create_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Create embeddings using Cohere API"""
        start_time = time.time()

        payload = {
            "model": "embed-v4.0",
            "texts": texts,
            "input_type": "search_document",  # Same as upload process
            "embedding_types": ["float"],
            "output_dimension": 1024,  # Same as upload process
        }

        try:
            client = await self._get_http_client()
            response = await client.post(
                COHERE_EMBEDDINGS_BASE_URL,
                headers=self.cohere_headers,
                json=payload,
            )
            
            if response.status_code != 200:
                error_msg = f"Cohere API Error: {response.status_code}"
                try:
                    error_details = response.json()
                    logger.error(f"Error Response: {error_details}")
                    error_msg += f" - {error_details.get('error', {}).get('message', 'Unknown error')}"
                except:
                    pass
                raise Exception(error_msg)

            result_json = response.json()
            embeddings_by_type = result_json.get("embeddings", {})
            embeddings = embeddings_by_type.get("float", [])
            
            if not embeddings:
                raise ValueError("No float embeddings returned from Cohere API")
                
            logger.debug(f"Embedding creation time: {time.time() - start_time:.3f}s")
            return embeddings

        except httpx.HTTPError as e:
            raise Exception(f"Failed to create embeddings: {str(e)}")
        except Exception as e:
            raise Exception(f"Error processing embeddings: {str(e)}")

    async def query_pinecone(self, vector: List[float], top_k: int = 10, filter_dict: Optional[Dict] = None) -> List[Dict]:
        """Query Pinecone index with a vector"""
        start_time = time.time()
        
        try:
            query_params = {
                "vector": vector,
                "top_k": top_k,
                "include_metadata": True,
                "include_values": False,
                "namespace": self.namespace,  # Add namespace parameter
            }
            
            if filter_dict:
                query_params["filter"] = filter_dict
            
            response = self.index.query(**query_params)
            
            logger.debug(f"Pinecone query time: {time.time() - start_time:.3f}s")
            return response.get("matches", [])
            
        except Exception as e:
            logger.error(f"Pinecone query failed: {str(e)}")
            raise

    async def rerank_with_cohere(self, query: str, documents: List[Dict], top_n: int = 5) -> List[Dict]:
        """Rerank documents using Cohere re-rank API"""
        start_time = time.time()
        
        if not documents:
            return []
        
        # Prepare documents for reranking
        doc_texts = []
        for doc in documents:
            text = doc.get("metadata", {}).get("text", "")
            if text:
                doc_texts.append(text)
        
        if not doc_texts:
            return documents
        
        rerank_url = "https://api.cohere.com/v2/rerank"
        data = {
            "model": "rerank-v3.5",
            "query": query,
            "top_n": min(top_n, len(doc_texts)),
            "documents": doc_texts
            # "return_documents": False
        }

        try:
            client = await self._get_http_client()
            if client is None:
                logger.error("HTTP client is None, cannot perform reranking")
                return documents
                
            response = await client.post(
                rerank_url,
                headers=self.cohere_headers,
                json=data,
            )
            
            if response.status_code != 200:
                logger.error(f"Rerank API error: {response.status_code}")
                return documents
                
            response_data = response.json()  # Get JSON from Cohere response

            reranked_documents = []

            results = response_data.get("results", [])
            for result in results:
                doc_index = result.get("index")
                score = result.get("relevance_score")

                if isinstance(doc_index, int) and 0 <= doc_index < len(documents):
                    doc = documents[doc_index].copy()
                    doc["relevance_score"] = score
                    reranked_documents.append(doc)
                
            logger.debug(f"Cohere Rerank API call & processing time: {time.time() - start_time:.3f}s")
            return reranked_documents
            
        except Exception as e:
            logger.error(f"Reranking failed: {str(e)}")
            return documents  # Return original docs if reranking fails

    def deduplicate_results(self, results: List[Dict]) -> List[Dict]:
        """Remove duplicate documents based on ID"""
        start_time = time.time()
        seen_ids = set()
        unique_results = []
        
        for doc in results:
            doc_id = doc.get("id")
            if doc_id and doc_id not in seen_ids:
                seen_ids.add(doc_id)
                unique_results.append(doc)
        
        logger.debug(f"Deduplication time: {time.time() - start_time:.3f}s")
        return unique_results

    async def retrieve(
        self,
        query: str,
        top_k: int = 10,
        top_n: int = 5,
        rerank_threshold: float = 0.1,
        filter_dict: Optional[Dict] = None,
        include_rerank: bool = True
    ) -> List[Dict]:
        """Main retrieval method that combines embedding, querying, and reranking"""
        start_time = time.time()
        logger.info(f"Starting retrieval for query: '{query}'")

        try:
            # Step 1: Create embeddings
            emb_start = time.time()
            embeddings = await self.create_embeddings([query])
            query_vector = embeddings[0]
            logger.info(f"Embedding generation time: {time.time() - emb_start:.3f}s")

            # Step 2: Query Pinecone
            query_start = time.time()
            results = await self.query_pinecone(
                vector=query_vector,
                top_k=top_k,
                filter_dict=filter_dict
            )
            logger.info(f"Pinecone query time: {time.time() - query_start:.3f}s")

            if not results:
                logger.warning("No results found from Pinecone")
                return []

            # Step 3: Deduplicate results
            dedup_start = time.time()
            unique_results = self.deduplicate_results(results)
            
            # Add default relevance scores based on Pinecone scores
            for doc in unique_results:
                if "relevance_score" not in doc:
                    doc["relevance_score"] = doc.get("score", 0.5)  # Use Pinecone score or default to 0.5
            
            logger.info(f"Deduplication time: {time.time() - dedup_start:.3f}s")

            # Step 4: Rerank if requested
            if include_rerank and unique_results:
                logger.info(f"Starting reranking with {len(unique_results)} documents")
                rerank_start = time.time()
                reranked_results = await self.rerank_with_cohere(
                    query=query,
                    documents=unique_results,
                    top_n=top_n
                )
                logger.info(f"Reranking time: {time.time() - rerank_start:.3f}s")
                logger.info(f"Reranked results count: {len(reranked_results)}")

                # Filter by relevance threshold
                filtered_results = [
                    doc for doc in reranked_results
                    if doc.get("relevance_score", 0) >= rerank_threshold
                ]
                logger.info(f"Filtered results count: {len(filtered_results)}")
                
                # If no results after filtering, return top results without filtering
                if not filtered_results and reranked_results:
                    logger.info("No results after relevance filtering, returning top results")
                    filtered_results = reranked_results[:top_n]
                
                logger.info(f"Total retrieval time: {time.time() - start_time:.3f}s")
                return filtered_results
            else:
                logger.info(f"Total retrieval time (no rerank): {time.time() - start_time:.3f}s")
                return unique_results[:top_n]

        except Exception as e:
            logger.error(f"Retrieval failed: {str(e)}\n{traceback.format_exc()}")
            raise

    async def get_relevant_context(self, query: str, max_chars: int = 2000) -> str:
        """Get relevant context as a formatted string for the agent"""
        try:
            results = await self.retrieve(query, top_k=10, top_n=5, rerank_threshold=0.1)
            
            if not results:
                return "No relevant documents found."
            
            context_parts = []
            current_length = 0
            
            for i, doc in enumerate(results, 1):
                text = doc.get("metadata", {}).get("text", "")
                source = doc.get("metadata", {}).get("source", "Unknown")
                score = doc.get("relevance_score", 0)
                
                if text and current_length + len(text) <= max_chars:
                    context_parts.append(f"[Document {i}] (Source: {source}, Score: {score:.3f})\n{text}\n")
                    current_length += len(text)
                else:
                    break
            
            if context_parts:
                return "\n".join(context_parts)
            else:
                return "No relevant documents found."
                
        except Exception as e:
            logger.error(f"Error getting context: {str(e)}")
            return f"Error retrieving context: {str(e)}"


# Global retrieval service instance
_retrieval_service = None


async def get_retrieval_service() -> RetrievalService:
    """Get or create the global retrieval service instance"""
    global _retrieval_service
    if _retrieval_service is None:
        _retrieval_service = RetrievalService()
    return _retrieval_service


async def search_documents(query: str, top_k: int = 6, top_n: int = 3) -> Dict:
    """Tool function for the agent to search documents"""
    try:
        service = await get_retrieval_service()
        results = await service.retrieve(query, top_k=top_k, top_n=top_n)
        
        # Format results for the agent
        formatted_results = []
        for i, doc in enumerate(results, 1):
            formatted_results.append({
                "rank": i,
                "id": doc.get("id", "Unknown"),
                "text": doc.get("metadata", {}).get("text", ""),
                "source": doc.get("metadata", {}).get("source", "Unknown"),
                "relevance_score": doc.get("relevance_score", 0),
                "metadata": doc.get("metadata", {})
            })
        
        return {
            "query": query,
            "total_results": len(formatted_results),
            "results": formatted_results
        }
        
    except Exception as e:
        logger.error(f"Search documents failed: {str(e)}")
        return {
            "query": query,
            "error": str(e),
            "total_results": 0,
            "results": []
        }


async def get_context(query: str) -> Dict:
    """Tool function for the agent to get relevant context"""
    try:
        service = await get_retrieval_service()
        context = await service.get_relevant_context(query)
        
        return {
            "query": query,
            "context": context,
            "success": True
        }
        
    except Exception as e:
        logger.error(f"Get context failed: {str(e)}")
        return {
            "query": query,
            "context": f"Error retrieving context: {str(e)}",
            "success": False
        } 