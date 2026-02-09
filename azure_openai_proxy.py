import os
import json
import uuid
import logging
import requests

from fastapi import FastAPI, Request, Response
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
logger = logging.getLogger("azure-openai-proxy")

# =========================
# Environment variables
# =========================

AZURE_API_KEY = os.environ["AZURE_OPENAI_API_KEY"]
AZURE_BASE_URL = os.environ["AZURE_OPENAI_BASE_URL"]  # https://xxx.openai.azure.com
AZURE_API_VERSION = os.environ.get(
    "AZURE_OPENAI_API_VERSION", "2024-02-15-preview"
)
AZURE_DEPLOYMENT_NAME = os.environ.get("AZURE_DEPLOYMENT_NAME", "gpt-4.1")

logger.debug("Azure OpenAI proxy configuration loaded")
logger.debug("AZURE_BASE_URL=%s", AZURE_BASE_URL)
logger.debug("AZURE_API_VERSION=%s", AZURE_API_VERSION)
logger.debug("AZURE_DEPLOYMENT_NAME=%s", AZURE_DEPLOYMENT_NAME)

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
    logger.debug("GET /v1/models → returning fake model list (%s)", AZURE_DEPLOYMENT_NAME)

    return {
        "object": "list",
        "data": [
            {
                "id": AZURE_DEPLOYMENT_NAME,
                "object": "model",
                "owned_by": "azure",
            }
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

    deployment = body.get("model")
    if not deployment:
        logger.error("[%s] Missing 'model' field (Azure deployment name)", req_id)
        return Response(
            content='{"error":"model field required (Azure deployment name)"}',
            status_code=400,
            media_type="application/json",
        )

    azure_url = (
        f"{AZURE_BASE_URL}/openai/deployments/{deployment}/chat/completions"
        f"?api-version={AZURE_API_VERSION}"
    )

    logger.debug("[%s] Azure URL: %s", req_id, azure_url)

    headers = {
        "Content-Type": "application/json",
        "api-key": AZURE_API_KEY,
    }

    # Remove OpenAI-only / Azure-incompatible fields
    if not body.get("stream", False):
        if "stream_options" in body:
            logger.debug("[%s] Removing stream_options (stream=false)", req_id)
            body.pop("stream_options", None)

    logger.debug(
        "[%s] Payload sent to Azure:\n%s",
        req_id,
        json.dumps(scrub(body), indent=2),
    )

    try:
        resp = requests.post(
            azure_url,
            headers=headers,
            json=body,
            timeout=120,
        )
    except Exception as e:
        logger.exception("[%s] Error calling Azure OpenAI", req_id)
        return Response(
            content=json.dumps({"error": str(e)}),
            status_code=500,
            media_type="application/json",
        )

    logger.debug("[%s] Azure response status: %s", req_id, resp.status_code)

    try:
        logger.debug(
            "[%s] Azure response body:\n%s",
            req_id,
            json.dumps(resp.json(), indent=2),
        )
    except Exception:
        logger.debug(
            "[%s] Azure response raw body:\n%s",
            req_id,
            resp.text,
        )

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        media_type="application/json",
    )
