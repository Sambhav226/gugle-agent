#!/bin/bash
set -e # Exit immediately if a command exits with a non-zero status.

# --- Configuration Variables (REPLACE THESE IF DIFFERENT FROM DEFAULTS) ---
PROJECT_ID="farmer-agent-466818"             # Your Google Cloud Project ID (Filled from gcloud init)
REGION="us-central1"                         # The GCP region for your Cloud Run service (e.g., us-central1, europe-west1)
SERVICE_NAME="livekit-agent-service"         # The name for your Cloud Run service
IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}:latest"

# LiveKit specific environment variables
# IMPORTANT: For production, consider using Google Secret Manager for these.
LIVEKIT_URL="wss://google-78a573z8.livekit.cloud"
LIVEKIT_API_KEY="APIemzLJe7w652j"
LIVEKIT_API_SECRET="QjzkY4eRs8YxOPo3mIkfEopXSKyDWdlXRa60NKD7YA"
LIVEKIT_SIP_URI="sip:6xhhqxjqs9b.sip.livekit.cloud"

# Other application-specific environment variables
PINECONE_API_KEY="pcsk_6wiNh2_NVxQJXtDtMdc4TeFtgwSiT2nYzMBY57Rts51uJsdbzKTVLsP1FbjPzvjDnYZ1o6"
COHERE_API_KEY="V5opD1DHzb5UKVKvL3ercfKYv5fqz4HA9ngiMd1d"
PINECONE_ENVIRONMENT="us-east-1"
PINECONE_INDEX_NAME="farmer-voice-index"
PINECONE_NAMESPACE="farmer-rag"
GOOGLE_API_KEY="AIzaSyBXnot3rhCxrt62KjsEfls2F4Sloy03j84"

# Service account for the Cloud Run service.
SERVICE_ACCOUNT_EMAIL="farmer-agent-466818@appspot.gserviceaccount.com"

# --- Script Execution ---
echo "--- Ensuring Docker Buildx builder is ready ---"
# Create a new builder if one doesn't exist, or use the default.
# Ensure it supports multiple platforms.
# The '|| true' allows the script to continue if 'create' fails because it already exists.
docker buildx create --name mybuilder --use || true
docker buildx inspect --bootstrap

echo "--- Building Docker image for linux/amd64 architecture and pushing to GCR ---"
# Use docker buildx to build for the target platform and push directly.
# The --push flag here eliminates the need for a separate 'docker push' command.
docker buildx build --platform linux/amd64 -t "${IMAGE_NAME}" --push .

echo "--- Deploying to Google Cloud Run ---"
gcloud run deploy "${SERVICE_NAME}" \
  --image "${IMAGE_NAME}" \
  --region "${REGION}" \
  --platform managed \
  --allow-unauthenticated \
  --port 8080 \
  --set-env-vars="LIVEKIT_URL=${LIVEKIT_URL},\
LIVEKIT_API_KEY=${LIVEKIT_API_KEY},\
LIVEKIT_API_SECRET=${LIVEKIT_API_SECRET},\
LIVEKIT_SIP_URI=${LIVEKIT_SIP_URI},\
PINECONE_API_KEY=${PINECONE_API_KEY},\
COHERE_API_KEY=${COHERE_API_KEY},\
PINECONE_ENVIRONMENT=${PINECONE_ENVIRONMENT},\
PINECONE_INDEX_NAME=${PINECONE_INDEX_NAME},\
PINECONE_NAMESPACE=${PINECONE_NAMESPACE},\
GOOGLE_API_KEY=${GOOGLE_API_KEY}" \
  --service-account="${SERVICE_ACCOUNT_EMAIL}" \
  --memory 512Mi \
  --cpu 1 \
  --timeout 300s \
  --concurrency 80 \
  --project "${PROJECT_ID}"

echo "--- Deployment complete! ---"
echo "You may need to configure your LiveKit server to connect to this agent's URL."

# The describe command will only work if the service deployed successfully.
SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)' 2>/dev/null)
if [ -n "$SERVICE_URL" ]; then
  echo "Cloud Run service URL: $SERVICE_URL"
else
  echo "Could not retrieve Cloud Run service URL. Check Cloud Run console for status and URL."
  echo "Troubleshooting tip: Check the output of 'docker buildx build' and the Google Container Registry (https://console.cloud.google.com/artifacts/gcr/containers) for your project."
fi