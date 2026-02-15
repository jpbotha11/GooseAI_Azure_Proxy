# Docker Setup for Azure Proxies

Run both Azure OpenAI and Azure AI Foundry proxies in Docker containers.

## Quick Start

### 1. Create .env file

Copy the example and fill in your credentials:

```bash
cp .env.docker.example .env
```

Edit `.env` with your actual credentials:

```env
# Azure OpenAI
AZURE_OPENAI_API_KEY=your-actual-key
AZURE_OPENAI_BASE_URL=https://your-resource.openai.azure.com
AZURE_DEPLOYMENT_NAME=gpt-4o

# Azure AI Foundry
AZURE_AI_API_KEY=your-actual-key
AZURE_AI_ENDPOINT=https://your-resource.cognitiveservices.azure.com
DEFAULT_AI_MODEL=gpt-5

# Rate limiting (optional)
RATE_LIMIT_DELAY=3
```

### 2. Build and Start

```bash
# Build and start both proxies
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

### 3. Test

```bash
# Test Azure OpenAI proxy
curl http://localhost:8000/v1/models

# Test Azure AI Foundry proxy
curl http://localhost:8001/v1/models
```

## Docker Commands

### Start Services
```bash
# Start both proxies
docker-compose up -d

# Start only one proxy
docker-compose up -d azure-openai-proxy
docker-compose up -d azure-ai-proxy
```

### View Logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f azure-openai-proxy
docker-compose logs -f azure-ai-proxy
```

### Stop Services
```bash
# Stop all
docker-compose down

# Stop specific service
docker-compose stop azure-openai-proxy
docker-compose stop azure-ai-proxy
```

### Restart Services
```bash
# Restart all
docker-compose restart

# Restart specific service
docker-compose restart azure-openai-proxy
docker-compose restart azure-ai-proxy
```

### Rebuild After Code Changes
```bash
# Rebuild and restart
docker-compose up -d --build
```

## Service URLs

Once running, the proxies are available at:

- **Azure OpenAI Proxy**: http://localhost:8000
- **Azure AI Foundry Proxy**: http://localhost:8001

## Configuration

### Environment Variables

All configuration is done via the `.env` file. See `.env.docker.example` for all options.

### Rate Limiting

To add rate limiting to Azure AI Foundry proxy:

```env
RATE_LIMIT_DELAY=3      # 3 seconds between requests
RATE_LIMIT_RPM=10       # Max 10 requests per minute
RATE_LIMIT_TPM=40000    # Max 40k tokens per minute
```

### Port Changes

To use different ports, edit `docker-compose.yml`:

```yaml
ports:
  - "9000:8000"  # Maps external port 9000 to internal 8000
```

## Health Checks

Both services include health checks:

- Azure OpenAI: `http://localhost:8000/v1/models`
- Azure AI Foundry: `http://localhost:8001/health`

Check service health:
```bash
docker-compose ps
```

## Troubleshooting

### View Container Logs
```bash
docker-compose logs -f azure-openai-proxy
docker-compose logs -f azure-ai-proxy
```

### Check if Containers are Running
```bash
docker-compose ps
```

### Test from Inside Container
```bash
docker exec -it azure-openai-proxy curl http://localhost:8000/v1/models
docker exec -it azure-ai-foundry-proxy curl http://localhost:8001/health
```

### Environment Variable Issues
```bash
# Check what env vars are set in container
docker-compose exec azure-openai-proxy env | grep AZURE
docker-compose exec azure-ai-proxy env | grep AZURE
```

### Rebuild from Scratch
```bash
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

## Using with Goose

Point Goose to the Docker containers:

### Azure OpenAI
```bash
export OPENAI_API_BASE=http://localhost:8000/v1
export OPENAI_API_KEY=dummy
```

### Azure AI Foundry
```bash
export OPENAI_API_BASE=http://localhost:8001/v1
export OPENAI_API_KEY=dummy
```

## Production Deployment

For production:

1. **Use secrets management** instead of `.env` file
2. **Add authentication** to proxy endpoints
3. **Use a reverse proxy** (nginx, traefik)
4. **Enable logging** to external system
5. **Set resource limits** in docker-compose.yml:

```yaml
services:
  azure-openai-proxy:
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 512M
        reservations:
          cpus: '0.5'
          memory: 256M
```

## Files Structure

```
.
├── Dockerfile                    # Container image definition
├── docker-compose.yml           # Service orchestration
├── .env                        # Your credentials (gitignored)
├── .env.docker.example         # Example configuration
├── azure_openai_proxy.py       # Azure OpenAI proxy code
├── azure_ai_proxy.py           # Azure AI Foundry proxy code
└── requirements.txt            # Python dependencies
```

## Network

Both containers are on the same Docker network (`azure-proxy-network`), allowing them to communicate if needed.

To access from another container:
- `http://azure-openai-proxy:8000`
- `http://azure-ai-foundry-proxy:8001`