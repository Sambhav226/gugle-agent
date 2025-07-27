#!/usr/bin/env python

import asyncio
import os
import pinecone
from pinecone import Pinecone
from dotenv import load_dotenv
from loguru import logger
from .utils import get_vectors_prefix

# Load environment variables
load_dotenv(override=True)

# Required environment variables
PINECONE_API_KEY = os.getenv('PINECONE_API_KEY')
PINECONE_ENVIRONMENT = os.getenv('PINECONE_ENVIRONMENT', 'us-east-1')

DIMENSION = 1024  # Cohere embeddings dimension


def ensure_index_exists(pc, index_name):
    """Check if index exists, create if it doesn't"""
    try:
        # Get list of existing indexes
        existing_indexes = pc.list_indexes().names()
        logger.info(f"Available indexes: {existing_indexes}")
        
        if index_name not in existing_indexes:
            logger.info(f"Index '{index_name}' not found. Creating new Pinecone index...")
            pc.create_index(
                name=index_name,
                dimension=DIMENSION,
                metric="dotproduct",
                spec=pinecone.ServerlessSpec(
                    cloud="aws",
                    region=PINECONE_ENVIRONMENT
                )
            )
            logger.success(f"✅ Successfully created new index: {index_name}")
        else:
            logger.info(f"✅ Using existing index: {index_name}")
            
    except Exception as e:
        logger.error(f"Exception in ensure_index_exists: {e}", exc_info=True)
        raise


def upsert_batch(index, vectors, namespace, batch_size=100):
    """Upsert vectors to Pinecone in batches"""
    total_batches = len(vectors)//batch_size + 1
    logger.info(f"Upserting {len(vectors)} vectors in {total_batches} batches")
    
    for i in range(0, len(vectors), batch_size):
        batch = vectors[i:i + batch_size]
        try:
            index.upsert(
                vectors=batch,
                namespace=namespace
            )
            logger.debug(f"Upserted batch {i//batch_size + 1} of {total_batches}")
        except Exception as e:
            logger.error(f"Error upserting batch: {str(e)}", exc_info=True)
            raise


def delete_batch(index_name, namespace, doc_id):
    """Delete vectors with a specific prefix from Pinecone"""
    pc = Pinecone(api_key=PINECONE_API_KEY)
    prefix = get_vectors_prefix(doc_id)
    index = pc.Index(index_name)
    logger.info(f"Deleting vectors with prefix {prefix} from namespace {namespace}")
    try:
        for ids in index.list(prefix=prefix, namespace=namespace):
            index.delete(ids=ids, namespace=namespace)
        logger.success(f"Successfully deleted vectors with prefix {prefix}")
    except Exception as e:
        logger.error(f"Failed to delete vectors: {str(e)}", exc_info=True)
        raise
    return 


async def update_metadata_batch(index_name, namespace, doc_id, metadata_delta={}):
    """Update metadata for vectors with a specific prefix"""
    if not metadata_delta:
        logger.warning("No metadata provided for update")
        return
    pc = Pinecone(api_key=PINECONE_API_KEY, pool_threads=30)
    prefix = get_vectors_prefix(doc_id)
    index = pc.Index(index_name)
    logger.info(f"Updating vectors with prefix {prefix} from namespace {namespace}")
    processed = 0
    for ids in index.list(prefix=prefix, namespace=namespace):
        tasks = [asyncio.to_thread(index.update, id=id, set_metadata=metadata_delta, namespace=namespace) for id in ids]
        await asyncio.gather(*tasks)
        processed += len(ids)
    logger.success(f"Successfully updated {processed} vectors with prefix {prefix}")
    return


def prepare_vectors(data):
    """Prepare vectors for upsertion"""
    try:
        logger.debug(f"Preparing {len(data)} vectors for upsertion")
        vectors = []
        for i, item in enumerate(data):
            chunk_index = i + 1
            item["chunk_index"] = chunk_index

            embedding = item.get("embedding")

            metadata = {k: v for k, v in item.items() if k not in ["embedding", "id"]}

            vector = {
                "id": item["id"],
                "values": embedding,
                "metadata": metadata
            }
            vectors.append(vector)
        logger.debug(f"Prepared {len(vectors)} vectors")
        return vectors
    except Exception as e:
        logger.error(f"Exception in prepare_vectors: {e}", exc_info=True)
        return []


async def ingest_embedded_data(embedded_data: list[dict],
                         index_name: str, 
                         namespace: str) -> None:
    """Main function to ingest embedded data into Pinecone"""
    logger.info(f"Initializing Pinecone ingestion for {len(embedded_data)} vectors, namespace: {namespace}, index: {index_name}")
    pc = Pinecone(api_key=PINECONE_API_KEY)
    ensure_index_exists(pc, index_name)
    index = pc.Index(index_name)

    vectors = prepare_vectors(embedded_data)
    if vectors:
        upsert_batch(index, vectors, namespace)
        logger.success(f"Successfully processed {len(vectors)} vectors")
    else:
        logger.warning("No valid vectors found for ingestion")

    return 
