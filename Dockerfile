FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Hugging Face Spaces require running on port 7860
EXPOSE 7860

# Run the FastAPI app
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "7860"]
