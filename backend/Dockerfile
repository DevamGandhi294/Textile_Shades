# Backend for Hugging Face Spaces (Docker Space): the web API in api.py + the AI model.
FROM python:3.13-slim

# OpenCV needs these system libraries
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

# Hugging Face runs the container as user 1000
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH PYTHONUNBUFFERED=1
WORKDIR /home/user/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

COPY --chown=user . .

# One process only: uploaded photos are kept in memory between requests
EXPOSE 7860
CMD ["python", "api.py", "--host", "0.0.0.0", "--port", "7860"]
