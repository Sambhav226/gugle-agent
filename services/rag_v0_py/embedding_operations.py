#!/usr/bin/env python

import os
import requests
from typing import List, Dict
from dotenv import load_dotenv
import nltk
from loguru import logger

# Constants
load_dotenv(override=True)
COHERE_API_KEY = os.getenv("COHERE_API_KEY")
COHERE_EMBEDDINGS_BASE_URL = "https://api.cohere.com/v2/embed"

# Download required NLTK data
try:
    nltk.download('punkt_tab', quiet=True)
except:
    logger.warning("Could not download NLTK punkt_tab data")


def create_embeddings_cohere(texts: List[str]) -> List[Dict]:
    """Create embeddings using Cohere API"""
    logger.info(f"Creating embeddings for {len(texts)} texts")
    headers = {
        "Authorization": f"Bearer {COHERE_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "embed-v4.0",
        "texts": texts,   
        "input_type": "search_document",
        "embedding_types": ["float"],
        "output_dimension": 1024,
    }

    try:
        logger.debug("Making request to Cohere API")
        response = requests.post(
            COHERE_EMBEDDINGS_BASE_URL,
            headers=headers,
            json=payload,
            timeout=30
        )
        
        if response.status_code != 200:
            error_msg = f"API Error: {response.status_code}"
            try:
                error_details = response.json()
                logger.error(f"Error Response: {error_details}")
                error_msg += f" - {error_details.get('error', {}).get('message', 'Unknown error')}"
            except:
                pass
            raise Exception(error_msg)
        
        result_json = response.json()

        embeddings_by_type = result_json.get("embeddings", {})

        # Extract only the "float" embeddings — shape: List[List[float]]
        embeddings = embeddings_by_type.get("float", [])
        if not embeddings:
            raise ValueError("No float embeddings returned from Cohere API")
        logger.success(f"Successfully created {len(embeddings)} embeddings")
        return embeddings
                
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to create embeddings: {str(e)}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Error processing embeddings: {str(e)}", exc_info=True)
        raise


async def enrich_with_embeddings(entries: List[dict]) -> List[dict]:
    """Enrich entries with embeddings"""
    logger.info(f"Starting enrichment for {len(entries)} entries")
    texts = []
    for entry in entries:
        texts.append(entry["text"])
    
    # Create embeddings
    try:
        embedding_results = create_embeddings_cohere(texts)
        
        # Update entries with embeddings
        for idx, (entry, embedding_data) in enumerate(
            zip(entries, embedding_results)
        ):
            entry["embedding"] = embedding_data
            
            entry.update({
                "embedding_model": "Cohere's embed-v4.0",
                "embedding_dimensions": 1024,
            })
        logger.success(f"Successfully enriched {len(entries)} entries")
        return entries
        
    except Exception as e:
        logger.error(f"Failed to enrich entries: {str(e)}", exc_info=True)
        return [] 