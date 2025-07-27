# Document Upload System for Pinecone RAG

This module provides a comprehensive solution for uploading documents to Pinecone with embeddings for RAG (Retrieval-Augmented Generation) applications.

## Features

- **Document Chunking**: Intelligent text chunking with configurable size and overlap
- **Embedding Generation**: Uses Cohere's embed-v4.0 model for high-quality embeddings
- **Dense Vectors**: High-quality embeddings using Cohere's embed-v4.0 model
- **Batch Processing**: Efficient batch uploads to Pinecone
- **Multiple Input Types**: Support for text, files, and directories
- **Metadata Management**: Rich metadata support for documents and chunks
- **Error Handling**: Robust error handling and logging

## Prerequisites

### Environment Variables

Set the following environment variables:

```bash
export PINECONE_API_KEY="your-pinecone-api-key"
export COHERE_API_KEY="your-cohere-api-key"
export PINECONE_ENVIRONMENT="us-east-1"  # Optional, defaults to us-east-1
export PINECONE_INDEX_NAME="your-index-name"  # Optional, defaults to "farmer-voice-index"
export PINECONE_NAMESPACE="your-namespace"    # Optional, defaults to "documents"
```

### Dependencies

The system requires the following Python packages:

```bash
pip install pinecone
pip install cohere
pip install loguru
pip install python-dotenv
pip install nltk
pip install requests
```

## Quick Start

### Using the Command-Line Script

The easiest way to upload documents is using the command-line script:

```bash
# Upload a single file
python upload_documents.py --file path/to/document.txt

# Upload a directory
python upload_documents.py --directory path/to/documents/

# Upload text directly
python upload_documents.py --text "Your text content here"
```

### Using the Python API

```python
import asyncio
from app.services.rag_v0_py import DocumentUploader

async def upload_my_documents():
    # Initialize uploader (uses environment variables by default)
    uploader = DocumentUploader(
        chunk_size=1000,
        chunk_overlap=200
    )

    # Upload text
    doc_id = await uploader.upload_text(
        "Your document content here",
        metadata={"source": "manual", "category": "example"}
    )

    # Upload a file
    doc_id = await uploader.upload_file(
        "path/to/document.txt",
        metadata={"source": "file", "category": "documentation"}
    )

    # Upload a directory
    doc_ids = await uploader.upload_directory(
        "path/to/documents/",
        file_extensions=[".txt", ".md", ".py"],
        metadata={"source": "directory", "category": "code"}
    )

# Run the upload
asyncio.run(upload_my_documents())
```

## Configuration Options

### DocumentUploader Parameters

- `index_name`: Pinecone index name (default: from `PINECONE_INDEX_NAME` env var or "farmer-voice-index")
- `namespace`: Pinecone namespace (default: from `PINECONE_NAMESPACE` env var or "documents")
- `chunk_size`: Size of text chunks in characters (default: 1000)
- `chunk_overlap`: Overlap between chunks in characters (default: 200)

### Chunking Strategy

The system uses intelligent chunking that:

- Respects sentence boundaries when possible
- Maintains configurable chunk size and overlap
- Preserves document structure and context

### Embedding Configuration

- **Model**: Cohere embed-v4.0
- **Dimensions**: 1024
- **Input Type**: search_document

## File Structure

```
app/services/rag_v0_py/
├── __init__.py                 # Package exports
├── utils.py                    # Utility functions
├── document_uploader.py        # Main uploader class
├── pinecone_operations.py      # Pinecone-specific operations
├── embedding_operations.py     # Embedding generation
└── README.md                   # This file
```

## API Reference

### DocumentUploader Class

#### Methods

- `upload_text(text, doc_id=None, metadata=None)`: Upload text content
- `upload_file(file_path, doc_id=None, metadata=None)`: Upload a file
- `upload_directory(directory_path, file_extensions=None, metadata=None)`: Upload directory
- `delete_document(doc_id)`: Delete a document and all its chunks
- `update_document_metadata(doc_id, metadata_delta)`: Update document metadata

### DocumentChunker Class

#### Methods

- `chunk_text(text, doc_id)`: Split text into chunks with metadata

## Command-Line Options

### Basic Usage

```bash
# Upload a file
python upload_documents.py --file document.txt

# Upload a directory
python upload_documents.py --directory ./documents/

# Upload text
python upload_documents.py --text "Your content here"
```

### Advanced Options

```bash
# Custom index and namespace
python upload_documents.py --file document.txt --index-name my-index --namespace my-namespace

# Custom chunking parameters
python upload_documents.py --file document.txt --chunk-size 500 --chunk-overlap 100

# Custom file extensions for directory upload
python upload_documents.py --directory ./docs/ --extensions .txt .md .rst

# Add metadata
python upload_documents.py --file document.txt --metadata '{"source": "manual", "category": "docs"}'

# Custom document ID
python upload_documents.py --file document.txt --doc-id my-custom-id
```

## Error Handling

The system includes comprehensive error handling:

- **API Errors**: Handles Cohere and Pinecone API errors gracefully
- **File Errors**: Validates file existence and readability
- **Network Errors**: Retries and timeout handling
- **Validation**: Input validation and error messages

## Logging

The system uses structured logging with different levels:

- **INFO**: General progress information
- **DEBUG**: Detailed operation information
- **SUCCESS**: Successful operations
- **WARNING**: Non-critical issues
- **ERROR**: Errors that need attention

## Best Practices

1. **Chunk Size**: Use 500-1000 characters for most documents
2. **Overlap**: Use 10-20% of chunk size for overlap
3. **Metadata**: Add rich metadata for better search and filtering
4. **Batch Size**: The system automatically handles batching for large documents
5. **Error Recovery**: Check logs for any failed uploads and retry if needed

## Troubleshooting

### Common Issues

1. **Missing API Keys**: Ensure all environment variables are set
2. **Network Issues**: Check internet connectivity and API endpoints
3. **File Permissions**: Ensure read access to files being uploaded
4. **Index Limits**: Check Pinecone index limits and quotas

### Debug Mode

Enable debug logging for detailed information:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Examples

### Uploading Documentation

```bash
python upload_documents.py --directory ./docs/ \
    --extensions .md .txt .rst \
    --metadata '{"source": "documentation", "version": "1.0"}' \
    --index-name docs-index
```

### Uploading Code Files

```bash
python upload_documents.py --directory ./src/ \
    --extensions .py .js .ts .java \
    --metadata '{"source": "codebase", "language": "python"}' \
    --chunk-size 800
```

### Uploading Research Papers

```bash
python upload_documents.py --file research_paper.txt \
    --metadata '{"source": "research", "author": "John Doe", "year": 2024}' \
    --chunk-size 1200 \
    --chunk-overlap 300
```
