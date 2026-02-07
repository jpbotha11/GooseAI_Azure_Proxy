import os
import requests
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

AZURE_API_KEY = os.environ["AZURE_OPENAI_API_KEY"]
AZURE_BASE_URL = os.environ["AZURE_OPENAI_BASE_URL"]  # https://xxx.openai.azure.com
AZURE_API_VERSION = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/v1/models")
async def models():
    # Return a fake model list so Goose is happy
    return {
        "data": [
            {
                "id": os.environ.get("AZURE_DEPLOYMENT_NAME", "gpt-4.1"),
                "object": "model",
                "owned_by": "azure"
            }
        ],
        "object": "list"
    }


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()

    deployment = body.get("model")
    if not deployment:
        return Response(
            content='{"error":"model field required (Azure deployment name)"}',
            status_code=400,
            media_type="application/json",
        )

    azure_url = (
        f"{AZURE_BASE_URL}/openai/deployments/{deployment}/chat/completions"
        f"?api-version={AZURE_API_VERSION}"
    )

    headers = {
        "Content-Type": "application/json",
        "api-key": AZURE_API_KEY,
    }

    # Remove OpenAI-only fields if present
    # Remove Azure-incompatible fields
    if not body.get("stream", False):
        body.pop("stream_options", None)



    resp = requests.post(
        azure_url,
        headers=headers,
        json=body,
        timeout=120,
    )

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        media_type="application/json",
    )
