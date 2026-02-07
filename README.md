# Goose + Azure OpenAI Proxy

This is a lightweight **OpenAI-compatible proxy** that allows Goose AI to communicate with **Azure OpenAI deployments**. It handles the differences between Azure and OpenAI endpoints, making Goose work without modification.  

---

## Features

- `/v1/models` endpoint (fake model list for Goose)  
- `/v1/chat/completions` endpoint forwarding requests to Azure  
- Automatically injects `api-version` and routes to the correct Azure deployment  
- Removes incompatible fields like `stream_options` when streaming is disabled  
- Fully local and configurable via environment variables  

---

## Requirements

- Python 3.10+  
- `pip` for installing dependencies  

Python packages:

```bash
pip install fastapi uvicorn requests
```

---

## Setup

1. **Clone the repository or copy the proxy file**

```bash
git clone <repo-url>
cd <repo-folder>
```

2. **Set environment variables** (replace with your values)

**Windows PowerShell:**

```powershell
$env:AZURE_OPENAI_API_KEY="YOUR_AZURE_KEY"
$env:AZURE_OPENAI_BASE_URL="https://<resource>.openai.azure.com"
$env:AZURE_API_VERSION="2024-02-15-preview"
$env:AZURE_DEPLOYMENT_NAME="gpt-4.1"
```

**Linux / macOS:**

```bash
export AZURE_OPENAI_API_KEY="YOUR_AZURE_KEY"
export AZURE_OPENAI_BASE_URL="https://<resource>.openai.azure.com"
export AZURE_API_VERSION="2024-02-15-preview"
export AZURE_DEPLOYMENT_NAME="gpt-4.1"
```

> **Important:** Do not include `/openai` in `AZURE_OPENAI_BASE_URL`.

---

## Running the Proxy

Run the proxy locally using Uvicorn:

```bash
uvicorn azure_openai_proxy:app --host 127.0.0.1 --port 8000
```

- Default URL: `http://127.0.0.1:8000`  
- The server listens only locally by default.

---

## Configure Goose AI

Set Goose’s OpenAI connection to use the proxy:

```powershell
$env:OPENAI_API_KEY="dummy-key"
$env:OPENAI_API_BASE="http://127.0.0.1:8000"
$env:OPENAI_MODEL="<AZURE_DEPLOYMENT_NAME>"
```

- `OPENAI_MODEL` must be your **Azure deployment name**  
- The API key can be any value (the proxy ignores it)

---

## Testing the Proxy

**Test models endpoint:**

```bash
curl http://127.0.0.1:8000/v1/models
```

**Test chat completions endpoint:**

```bash
curl -X POST http://127.0.0.1:8000/v1/chat/completions \
-H "Content-Type: application/json" \
-d '{"model":"<AZURE_DEPLOYMENT_NAME>","messages":[{"role":"user","content":"Hello"}]}'
```

---

## Security Notes

- Do not expose this proxy publicly without authentication.  
- Keep it bound to `127.0.0.1` for local use.  
- Never commit your API keys to source control.  
- CORS is open (`*`) for local development; lock it down if exposed publicly.

---

## Optional Enhancements

- Support **streaming responses**  
- Add **Responses API** or embeddings endpoints  
- Dockerize the proxy for deployment  
- Add **token-based authentication** for remote access

---

## License

MIT License — free to use, modify, and distribute.

