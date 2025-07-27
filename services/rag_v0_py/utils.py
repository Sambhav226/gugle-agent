#!/usr/bin/env python

def get_vectors_prefix(doc_id: str) -> str:
    """Generate a prefix for vectors based on document ID.
    
    Args:
        doc_id: The document ID to generate a prefix for.
        
    Returns:
        A string prefix for the document's vectors.
    """
    return f"doc_{doc_id}_" 