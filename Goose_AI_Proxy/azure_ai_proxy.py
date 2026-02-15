import os
import json
import uuid
import logging
import requests

from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# =========================
# Load .env
# =========================

load_dotenv()  # loads .env into os.environ (env vars still override)

# =========================
# Logging setup
# =========================

logging.basicConfig(
    level=logging.DEBUG,  # change to INFO if too noisy
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("azure-ai-foundry-proxy")

# =========================
# Environment variables
# =========================

# Azure AI Foundry uses either API key or managed identity
AZURE_AI_API_KEY = os.environ["AZURE_AI_API_KEY"]
AZURE_AI_ENDPOINT = os.environ["AZURE_AI_ENDPOINT"]
# Example: https://your-ai-project.region.inference.ml.azure.com

# Default model if not specified
DEFAULT_MODEL = os.environ.get("DEFAULT_AI_MODEL", "gpt-5")

logger.debug("Azure AI Foundry proxy configuration loaded")
logger.debug("AZURE_AI_ENDPOINT=%s", AZURE_AI_ENDPOINT)
logger.debug("DEFAULT_MODEL=%s", DEFAULT_MODEL)

# =========================
# FastAPI app
# =========================

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# Helpers
# =========================

def scrub(payload: dict) -> dict:
    """Remove sensitive fields before logging."""
    redacted = dict(payload)
    redacted.pop("api_key", None)
    redacted.pop("authorization", None)
    return redacted


# =========================
# Routes
# =========================

@app.get("/v1/models")
async def models():
    logger.debug("GET /v1/models → returning available Azure AI Foundry models")

    # Common models available via Azure AI Foundry
    return {
        "object": "list",
        "data": [
            {"id": "gpt-5", "object": "model", "owned_by": "azure-ai"},
            {"id": "gpt-4o", "object": "model", "owned_by": "azure-ai"},
            {"id": "gpt-4o-mini", "object": "model", "owned_by": "azure-ai"},
            {"id": "o1-preview", "object": "model", "owned_by": "azure-ai"},
            {"id": "o1-mini", "object": "model", "owned_by": "azure-ai"},
            {"id": "Phi-3.5-MoE-instruct", "object": "model", "owned_by": "azure-ai"},
            {"id": "Phi-3.5-mini-instruct", "object": "model", "owned_by": "azure-ai"},
            {"id": "Mistral-large", "object": "model", "owned_by": "azure-ai"},
            {"id": "Mistral-large-2407", "object": "model", "owned_by": "azure-ai"},
            {"id": "Mistral-Nemo", "object": "model", "owned_by": "azure-ai"},
            {"id": "Mistral-small", "object": "model", "owned_by": "azure-ai"},
            {"id": "Meta-Llama-3.1-405B-Instruct", "object": "model", "owned_by": "azure-ai"},
            {"id": "Meta-Llama-3.1-70B-Instruct", "object": "model", "owned_by": "azure-ai"},
            {"id": "Meta-Llama-3.1-8B-Instruct", "object": "model", "owned_by": "azure-ai"},
            {"id": "Meta-Llama-3-70B-Instruct", "object": "model", "owned_by": "azure-ai"},
            {"id": "Meta-Llama-3-8B-Instruct", "object": "model", "owned_by": "azure-ai"},
            {"id": "Cohere-command-r-plus", "object": "model", "owned_by": "azure-ai"},
            {"id": "Cohere-command-r", "object": "model", "owned_by": "azure-ai"},
            {"id": "AI21-Jamba-Instruct", "object": "model", "owned_by": "azure-ai"},
        ],
    }


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    req_id = str(uuid.uuid4())[:8]

    logger.debug("[%s] Incoming request", req_id)
    logger.debug("[%s] Path: %s", req_id, request.url.path)

    body = await request.json()

    logger.debug("[%s] Incoming keys: %s", req_id, list(body.keys()))
    logger.debug(
        "[%s] Incoming payload:\n%s",
        req_id,
        json.dumps(scrub(body), indent=2),
    )

    model = body.get("model", DEFAULT_MODEL)
    
    logger.debug("[%s] Using model: %s", req_id, model)

    # Azure AI GitHub Models endpoint
    azure_ai_url = f"{AZURE_AI_ENDPOINT}"

    logger.debug("[%s] Azure AI URL: %s", req_id, azure_ai_url)

    headers = {
        "Content-Type": "application/json",
        "api-key": AZURE_AI_API_KEY,
    }

    # Azure AI GitHub Models uses standard OpenAI format
    # But we should ensure the model field is set correctly
    body["model"] = model

    # Handle streaming options - Azure AI supports standard streaming
    is_streaming = body.get("stream", False)
    
    logger.debug(
        "[%s] Payload sent to Azure AI:\n%s",
        req_id,
        json.dumps(scrub(body), indent=2),
    )

    try:
        if is_streaming:
            # For streaming responses, we need to handle differently
            resp = requests.post(
                azure_ai_url,
                headers=headers,
                json=body,
                timeout=120,
                stream=True,
            )
            
            logger.debug("[%s] Azure AI streaming response status: %s", req_id, resp.status_code)
            
            # Return streaming response using StreamingResponse
            from fastapi.responses import StreamingResponse
            
            def generate():
                for chunk in resp.iter_content(chunk_size=1024):
                    if chunk:
                        yield chunk
            
            return StreamingResponse(
                generate(),
                status_code=resp.status_code,
                media_type="text/event-stream",
            )
        else:
            # Non-streaming response
            resp = requests.post(
                azure_ai_url,
                headers=headers,
                json=body,
                timeout=120,
            )
            
            logger.debug("[%s] Azure AI response status: %s", req_id, resp.status_code)

            try:
                logger.debug(
                    "[%s] Azure AI response body:\n%s",
                    req_id,
                    json.dumps(resp.json(), indent=2),
                )
            except Exception:
                logger.debug(
                    "[%s] Azure AI response raw body:\n%s",
                    req_id,
                    resp.text,
                )

            return Response(
                content=resp.content,
                status_code=resp.status_code,
                media_type="application/json",
            )
            
    except Exception as e:
        logger.exception("[%s] Error calling Azure AI", req_id)
        return Response(
            content=json.dumps({"error": str(e)}),
            status_code=500,
            media_type="application/json",
        )


# =========================
# Health check
# =========================

@app.get("/health")
async def health():
    return {"status": "ok", "service": "azure-ai-foundry-proxy"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))  # Different default port from OpenAI proxy
    uvicorn.run(app, host="0.0.0.0", port=port)