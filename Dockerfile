# 1. Base Image
FROM python:3.10

# 2. Set Environment Variables
WORKDIR /app

# Set environment variables that are not secret.
ENV PYTHONUNBUFFERED 1
ENV PORT 8080

# 3. Copy Application Files
# Copy requirements.txt first to leverage Docker cache
COPY requirements.txt .

# 4. Install Dependencies
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy All Your Code
# This copies livekit_agent.py, market_data.csv, form_filler/, services/ etc.
COPY . .

# 6. Define the Command to Run the Application
# Use the livekit-agents CLI command to run the agent.
# It uses the entrypoint function defined in your livekit_agent.py.
CMD ["python3", "livekit_agent.py", "start"]