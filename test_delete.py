import os
from dotenv import load_dotenv
from pinecone import Pinecone

# Load environment variables from .env
load_dotenv()

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_ENVIRONMENT = os.getenv("PINECONE_ENVIRONMENT", "us-east-1")  # optional
INDEX_NAME = "farmer-voice-index"
NAMESPACE = "farmer-rag"  # or "" if not using namespace

# Initialize Pinecone client
pc = Pinecone(api_key=PINECONE_API_KEY)

# Connect to the index
index = pc.Index(INDEX_NAME)

# Delete all vectors from the namespace
print(f"Deleting all vectors from index '{INDEX_NAME}', namespace '{NAMESPACE}'")
index.delete(delete_all=True, namespace=NAMESPACE)
print("✅ All vectors deleted successfully.")
