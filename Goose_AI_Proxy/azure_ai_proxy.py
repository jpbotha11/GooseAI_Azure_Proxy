import os
import json
import uuid
import logging
import requests
import time
from collections import deque
from threading import Lock

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
# Example: https://your-resource.cognitiveservices.azure.com

# API version for Azure OpenAI style endpoints
AZURE_AI_API_VERSION = os.environ.get("AZURE_AI_API_VERSION", "2024-05-01-preview")

# Default model if not specified
DEFAULT_MODEL = os.environ.get("DEFAULT_AI_MODEL", "gpt-5")

# Rate limiting configuration
RATE_LIMIT_DELAY = float(os.environ.get("RATE_LIMIT_DELAY", "0"))  # Seconds between requests (0 = disabled)
RATE_LIMIT_RPM = int(os.environ.get("RATE_LIMIT_RPM", "0"))  # Requests per minute (0 = disabled)
RATE_LIMIT_TPM = int(os.environ.get("RATE_LIMIT_TPM", "0"))  # Tokens per minute (0 = disabled)

logger.debug("Azure AI Foundry proxy configuration loaded")
logger.debug("AZURE_AI_ENDPOINT=%s", AZURE_AI_ENDPOINT)
logger.debug("AZURE_AI_API_VERSION=%s", AZURE_AI_API_VERSION)
logger.debug("DEFAULT_MODEL=%s", DEFAULT_MODEL)
logger.debug("RATE_LIMIT_DELAY=%s seconds", RATE_LIMIT_DELAY)
logger.debug("RATE_LIMIT_RPM=%s", RATE_LIMIT_RPM if RATE_LIMIT_RPM > 0 else "disabled")
logger.debug("RATE_LIMIT_TPM=%s", RATE_LIMIT_TPM if RATE_LIMIT_TPM > 0 else "disabled")

# =========================
# Rate Limiter
# =========================

class RateLimiter:
    """Simple rate limiter with RPM and TPM tracking."""
    
    def __init__(self, rpm=0, tpm=0, delay=0):
        self.rpm = rpm  # Requests per minute
        self.tpm = tpm  # Tokens per minute
        self.delay = delay  # Fixed delay between requests
        
        self.request_times = deque()
        self.token_usage = deque()
        self.lock = Lock()
        self.last_request_time = 0
        
    def estimate_tokens(self, payload: dict) -> int:
        """Rough token estimation (4 chars ≈ 1 token)."""
        messages = payload.get("messages", [])
        text = json.dumps(messages)
        estimated = len(text) // 4
        
        # Add output tokens estimate
        max_tokens = payload.get("max_tokens", 1000)
        estimated += max_tokens
        
        return estimated
    
    def wait_if_needed(self, payload: dict):
        """Block if rate limits would be exceeded."""
        with self.lock:
            now = time.time()
            
            # Fixed delay between requests
            if self.delay > 0:
                time_since_last = now - self.last_request_time
                if time_since_last < self.delay:
                    sleep_time = self.delay - time_since_last
                    logger.info("Rate limit: sleeping %.2f seconds", sleep_time)
                    time.sleep(sleep_time)
                    now = time.time()
            
            # Clean old entries (older than 60 seconds)
            cutoff = now - 60
            while self.request_times and self.request_times[0] < cutoff:
                self.request_times.popleft()
            while self.token_usage and self.token_usage[0][0] < cutoff:
                self.token_usage.popleft()
            
            # Check RPM limit
            if self.rpm > 0:
                if len(self.request_times) >= self.rpm:
                    # Wait until oldest request falls out of window
                    sleep_time = 60 - (now - self.request_times[0])
                    if sleep_time > 0:
                        logger.info("RPM limit: sleeping %.2f seconds", sleep_time)
                        time.sleep(sleep_time)
                        now = time.time()
                        # Clean again after sleep
                        cutoff = now - 60
                        while self.request_times and self.request_times[0] < cutoff:
                            self.request_times.popleft()
            
            # Check TPM limit
            if self.tpm > 0:
                estimated_tokens = self.estimate_tokens(payload)
                current_tokens = sum(tokens for _, tokens in self.token_usage)
                
                if current_tokens + estimated_tokens > self.tpm:
                    # Wait until we have enough token budget
                    if self.token_usage:  # Make sure we have entries
                        sleep_time = 60 - (now - self.token_usage[0][0])
                        if sleep_time > 0:
                            logger.info(
                                "TPM limit: sleeping %.2f seconds (current: %d, estimated: %d, limit: %d)",
                                sleep_time, current_tokens, estimated_tokens, self.tpm
                            )
                            time.sleep(sleep_time)
                            now = time.time()
                            # Clean again after sleep
                            cutoff = now - 60
                            while self.token_usage and self.token_usage[0][0] < cutoff:
                                self.token_usage.popleft()
                
                # Record token usage
                self.token_usage.append((now, estimated_tokens))
            
            # Record request
            self.request_times.append(now)
            self.last_request_time = now

# Initialize rate limiter
rate_limiter = RateLimiter(
    rpm=RATE_LIMIT_RPM,
    tpm=RATE_LIMIT_TPM,
    delay=RATE_LIMIT_DELAY
)

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
            {"id": "gpt-5.2-chat", "object": "model", "owned_by": "azure-ai"},
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

    # Apply rate limiting
    rate_limiter.wait_if_needed(body)

    model = body.get("model", DEFAULT_MODEL)
    #model = DEFAULT_MODEL
    
    logger.debug("[%s] Using model: %s", req_id, model)

    # Azure AI Foundry endpoint (Azure OpenAI style)
    # Format: https://xxx-resource.cognitiveservices.azure.com/openai/deployments/{model}/chat/completions?api-version={version}
    azure_ai_url = f"{AZURE_AI_ENDPOINT}/openai/deployments/{model}/chat/completions?api-version={AZURE_AI_API_VERSION}"

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
    port = int(os.environ.get("PORT", 8001))  # Different default port from OpenAI proxy
    uvicorn.run(app, host="0.0.0.0", port=port)