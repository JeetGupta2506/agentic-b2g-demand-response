# API Documentation

The Agentic AI HEMS API provides endpoints for running the orchestrator and fetching available LLM models.

## Base URL

- **Local**: `http://localhost:5000`
- **Docker**: `http://localhost:5000`

## Endpoints

### Health Check

**GET** `/api/health`

Health check endpoint for monitoring container status.

**Rate Limit**: No limit

**Response:**
```json
{
  "status": "ok"
}
```

---

### Run Orchestrator (Streaming)

**POST** `/api/run/stream`

Run the orchestrator with real-time streaming output. This is the primary endpoint used by the dashboard.

**Rate Limit**: 20 requests/minute

**Request Body:**
```json
{
  "prompt": "Schedule my EV charging for tomorrow",
  "model": "model-name"
}
```

**Parameters:**
- `prompt` (string, required): Natural language instruction for the orchestrator
- `model` (string, optional): LLM model ID. If not provided, uses configured default model

**Response:**

Server-Sent Events (SSE) stream with the following event types:

```
data: {"type": "stdout", "content": "Agent output line\n"}

data: {"type": "done", "returncode": 0}

data: {"type": "error", "content": "Error message"}
```

**Event Types:**
- `stdout`: Real-time output from orchestrator execution
- `done`: Execution completed successfully
- `error`: Error occurred during execution

**Example (JavaScript):**
```javascript
const eventSource = new EventSource('/api/run/stream', {
  method: 'POST',
  body: JSON.stringify({
    prompt: 'Schedule dishwasher for tomorrow',
    model: 'model-name'
  })
});

eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log(data.type, data.content);
};
```

---

### Run Orchestrator (Blocking)

**POST** `/api/run`

Run the orchestrator and return complete output after execution finishes.

**Rate Limit**: 20 requests/minute

**Request Body:**
```json
{
  "prompt": "Schedule washing machine tomorrow morning"
}
```

**Parameters:**
- `prompt` (string, required): Natural language instruction for the orchestrator

**Response:**
```json
{
  "success": true,
  "prompt": "Schedule washing machine tomorrow morning",
  "stdout": "Complete orchestrator output...",
  "stderr": "Any error messages...",
  "returncode": 0
}
```

**Error Response (408 Timeout):**
```json
{
  "success": false,
  "error": "Orchestrator timed out after 5 minutes"
}
```

**Error Response (500 Server Error):**
```json
{
  "success": false,
  "error": "Error message"
}
```

---

### Get Available Models

**GET** `/api/models`

Fetch available LLM models from the configured provider API.

**Rate Limit**: 30 requests/minute

**Query Parameters:**
- `recently_used` (string, optional): Comma-separated list of recently used model IDs

**Response:**
```json
{
  "success": true,
  "provider": "cerebras",
  "most_used": [
    {
      "id": "model-id",
      "name": "Model Name",
      "description": "Model description",
      "created": 1704067200
    }
  ],
  "newest": [
    {
      "id": "model-id",
      "name": "Model Name",
      "description": "Model description",
      "created": 1735689600
    }
  ],
  "other": [...]
}
```

**Model Categories:**
- `most_used`: Models from the `recently_used` query parameter
- `newest`: Top 4 newest models (sorted by `created` timestamp)
- `other`: All remaining models

**Error Response:**
```json
{
  "success": false,
  "error": "No API key found. Set CEREBRAS_API_KEY, OPENAI_API_KEY, or LLM_API_KEY",
  "provider": "cerebras"
}
```

---

## Rate Limiting

The API implements rate limiting to prevent quota exhaustion:

- **Default Limits**: 200 requests/day, 50 requests/hour
- **Orchestrator Endpoints**: 20 requests/minute (expensive LLM operations)
- **Model List**: 30 requests/minute
- **Health Check**: No limit

**Rate Limit Headers:**
- `X-RateLimit-Limit`: Total requests allowed in window
- `X-RateLimit-Remaining`: Requests remaining in window
- `X-RateLimit-Reset`: Unix timestamp when limit resets

**Rate Limit Exceeded (429):**
```json
{
  "error": "Rate limit exceeded"
}
```

---

## CORS

CORS is enabled for local development. All origins are allowed by default.

For production deployment, configure CORS in `api.py`:
```python
CORS(app, origins=['https://yourdomain.com'])
```

---

## Timeout Configuration

- **Orchestrator Execution**: 5 minutes (300 seconds)
- **Model API Fetch**: 10 seconds

Timeouts can be adjusted in `api.py` if needed for complex scenarios.
