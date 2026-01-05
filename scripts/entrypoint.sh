#!/bin/bash
set -e

echo "🛡️  Svalinn AI Container Starting..."

# 1. Check for Models
# We check for one of the key files. If missing, we run the downloader.
if [ ! -f "/app/models/qwen2.5-1.5b-instruct-q4_k_m.gguf" ]; then
    echo "⚠️  Models not found in /app/models."
    if [ "$AUTO_DOWNLOAD_MODELS" = "true" ]; then
        echo "⬇️  Auto-downloading models... (This may take a while)"
        python scripts/download_models.py
    else
        echo "❌ Auto-download disabled. Please mount a volume with models or set AUTO_DOWNLOAD_MODELS=true"
    fi
else
    echo "✅ Models found."
fi

# 2. Start the Server
# We use exec so uvicorn becomes PID 1 (receives signals correctly)
echo "🚀 Starting API Server..."
exec uvicorn svalinn_ai.api.server:app --host 0.0.0.0 --port 8000 --workers 1
