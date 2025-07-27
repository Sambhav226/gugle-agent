import asyncio
import uuid
from services.rag_v0_py.document_uploader import load_and_split_document, DocumentUploader

# 👇 Change this path if needed
FILENAME = "schemes.txt"

def extract_metadata(chunk: str):
    lines = chunk.split('\n')
    title = ""
    description = ""
    sector = ""

    for line in lines:
        if line.startswith("Title:"):
            title = line.replace("Title:", "").strip()
        elif line.startswith("Description:"):
            description = line.replace("Description:", "").strip()
        elif line.startswith("Relevant Sectors:"):
            sector = line.replace("Relevant Sectors:", "").strip()
    
    return {
        "title": title,
        "description": description,
        "sector": sector,
        "text": chunk.strip()
    }

async def upload_chunks():
    chunks = load_and_split_document(FILENAME, separator="---")
    uploader = DocumentUploader(index_name="farmer-voice-index", namespace="farmer-rag")

    for idx, chunk in enumerate(chunks):
        metadata = extract_metadata(chunk)
        doc_id = f"scheme-{uuid.uuid4()}"
        print(f"⬆️ Uploading scheme {idx + 1}/{len(chunks)}: {metadata['title']}")
        await uploader.upload_text(chunk.strip(), doc_id=doc_id, metadata=metadata)

    print(f"✅ Uploaded {len(chunks)} enriched schemes to Pinecone")

if __name__ == "__main__":
    asyncio.run(upload_chunks())
