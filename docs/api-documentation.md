# API Documentation

## Base URL
`http://localhost:8000` (or your deployment URL)

## Authentication
Most endpoints are public for development. In production, implement authentication as needed.

## Session Management

### Create Session
Create a new disposable compute session.

```
POST /sessions
```

#### Request Body
```json
{
  "type": "preview|run_repo|fork_gui",
  "repo_url": "string",
  "repo_ref": "string (optional)",
  "pr_number": "integer (optional)",
  "ttl_minutes": "integer (optional, default: 30)"
}
```

#### Example Request
```bash
curl -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "type": "run_repo",
    "repo_url": "https://github.com/example/hello-world.git",
    "ttl_minutes": 60
  }'
```

#### Response
```json
{
  "session_id": "sess-20231201-123456-abcd",
  "status": "creating",
  "external_urls": ["https://abcd1234.preview.yourapp.dev"],
  "created_at": "2023-12-01T12:34:56.789Z"
}
```

#### Response Codes
- `200`: Session created successfully
- `400`: Invalid request parameters
- `500`: Internal server error

### Get Session Details
Retrieve details about a specific session.

```
GET /sessions/{session_id}
```

#### Example Request
```bash
curl http://localhost:8000/sessions/sess-20231201-123456-abcd
```

#### Response
```json
{
  "id": "sess-20231201-123456-abcd",
  "type": "run_repo",
  "status": "running",
  "created_at": "2023-12-01T12:34:56.789Z",
  "updated_at": "2023-12-01T12:35:00.123Z",
  "expires_at": "2023-12-01T13:34:56.789Z",
  "repo_url": "https://github.com/example/hello-world.git",
  "repo_ref": null,
  "pr_number": null,
  "ports": {
    "app": 3000
  },
  "metadata": {}
}
```

#### Response Codes
- `200`: Session details retrieved successfully
- `404`: Session not found
- `500`: Internal server error

### Destroy Session
Destroy a session and all its resources.

```
DELETE /sessions/{session_id}
```

#### Example Request
```bash
curl -X DELETE http://localhost:8000/sessions/sess-20231201-123456-abcd
```

#### Response
```json
{
  "message": "Session sess-20231201-123456-abcd destroyed successfully"
}
```

#### Response Codes
- `200`: Session destroyed successfully
- `404`: Session not found
- `500`: Internal server error

### Get Session Logs
Retrieve logs from a session's service.

```
GET /sessions/{session_id}/logs?service={service_name}&lines={number_of_lines}
```

#### Parameters
- `service`: Service name (default: "main")
- `lines`: Number of lines to return (default: 100)

#### Example Request
```bash
curl "http://localhost:8000/sessions/sess-20231201-123456-abcd/logs?service=app&lines=50"
```

#### Response
```json
{
  "service": "app",
  "logs": "Server started on port 3000\nConnected to database\n..."
}
```

#### Response Codes
- `200`: Logs retrieved successfully
- `404`: Session not found
- `500`: Internal server error

### Fork Session
Create a fork of a GUI session (for forkable GUI sessions only).

```
POST /sessions/{session_id}/fork
```

#### Request Body
```json
{
  "snapshot_id": "string (optional)"
}
```

If no snapshot_id is provided, a new snapshot will be created at the fork point.

#### Example Request
```bash
curl -X POST http://localhost:8000/sessions/sess-20231201-123456-abcd/fork \
  -H "Content-Type: application/json" \
  -d '{
    "snapshot_id": "snapshot-20231201-123456-efgh"
  }'
```

#### Response
```json
{
  "new_session_id": "fork-sess-20231201-123456-abcd-1234",
  "status": "created"
}
```

#### Response Codes
- `200`: Session forked successfully
- `404`: Session not found
- `500`: Internal server error

## Real-time Features

### WebSocket for Real-time Logs
Connect to receive real-time logs from a session.

```
WS /ws/logs/{session_id}?service={service_name}
```

#### Parameters
- `service`: Service name (default: "main")

#### Example Connection
```javascript
const ws = new WebSocket('ws://localhost:8000/ws/logs/sess-20231201-123456-abcd?service=app');

ws.onmessage = function(event) {
  const data = JSON.parse(event.data);
  console.log(`[${data.service}] ${data.logs}`);
};
```

#### Message Format
```json
{
  "service": "app",
  "logs": "Log message here...",
  "timestamp": "2023-12-01T12:34:56.789Z"
}
```

## System Endpoints

### Health Check
Check the health status of the API server.

```
GET /health
```

#### Example Request
```bash
curl http://localhost:8000/health
```

#### Response
```json
{
  "status": "healthy",
  "timestamp": "2023-12-01T12:34:56.789Z"
}
```

#### Response Codes
- `200`: System is healthy
- `500`: System is unhealthy

### API Documentation
Access the interactive API documentation.

```
GET /docs
```

### API Schema
Get the OpenAPI schema.

```
GET /openapi.json
```

## Error Handling

### Error Response Format
All error responses follow this format:

```json
{
  "detail": "Error message describing the issue"
}
```

### Common Error Codes
- `400 Bad Request`: Invalid request parameters
- `404 Not Found`: Requested resource does not exist
- `422 Unprocessable Entity`: Request validation failed
- `500 Internal Server Error`: Server-side error

## Rate Limiting

The API implements rate limiting to prevent abuse:
- Anonymous requests: 100 requests per hour per IP
- Bearer token requests: 1000 requests per hour per token

## Examples

### Example 1: Create a Preview Environment
```bash
curl -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "type": "preview",
    "repo_url": "https://github.com/example/myapp.git",
    "repo_ref": "feature/new-feature",
    "pr_number": 142,
    "ttl_minutes": 120
  }'
```

### Example 2: Run a Repository
```bash
curl -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "type": "run_repo",
    "repo_url": "https://github.com/example/hello-world.git",
    "ttl_minutes": 60
  }'
```

### Example 3: Create a Forkable GUI Session
```bash
curl -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "type": "fork_gui",
    "repo_url": "https://github.com/example/3d-editor.git",
    "ttl_minutes": 180
  }'
```

### Example 4: Get Session Status and Logs
```bash
# Get session details
curl http://localhost:8000/sessions/sess-20231201-123456-abcd

# Get session logs
curl "http://localhost:8000/sessions/sess-20231201-123456-abcd/logs?lines=50"
```

### Example 5: Fork a GUI Session
```bash
curl -X POST http://localhost:8000/sessions/sess-20231201-123456-abcd/fork \
  -H "Content-Type: application/json" \
  -d '{}'
```

## SDK Examples

### Python SDK
```python
import requests
import json

class DisposableComputeClient:
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
    
    def create_session(self, session_type, repo_url, **kwargs):
        payload = {
            "type": session_type,
            "repo_url": repo_url
        }
        payload.update(kwargs)
        
        response = requests.post(f"{self.base_url}/sessions", json=payload)
        return response.json()
    
    def get_session(self, session_id):
        response = requests.get(f"{self.base_url}/sessions/{session_id}")
        return response.json()
    
    def destroy_session(self, session_id):
        response = requests.delete(f"{self.base_url}/sessions/{session_id}")
        return response.json()
    
    def get_logs(self, session_id, service="main", lines=100):
        params = {"service": service, "lines": lines}
        response = requests.get(f"{self.base_url}/sessions/{session_id}/logs", params=params)
        return response.json()

# Usage
client = DisposableComputeClient()
session = client.create_session(
    session_type="run_repo",
    repo_url="https://github.com/example/hello-world.git",
    ttl_minutes=60
)
print(f"Created session: {session['session_id']}")
```

### JavaScript/Node.js SDK
```javascript
class DisposableComputeClient {
  constructor(baseUrl = "http://localhost:8000") {
    this.baseUrl = baseUrl;
  }
  
  async createSession(sessionType, repoUrl, options = {}) {
    const response = await fetch(`${this.baseUrl}/sessions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        type: sessionType,
        repo_url: repoUrl,
        ...options
      })
    });
    
    return await response.json();
  }
  
  async getSession(sessionId) {
    const response = await fetch(`${this.baseUrl}/sessions/${sessionId}`);
    return await response.json();
  }
  
  async destroySession(sessionId) {
    const response = await fetch(`${this.baseUrl}/sessions/${sessionId}`, {
      method: 'DELETE'
    });
    
    return await response.json();
  }
  
  async getLogs(sessionId, service = "main", lines = 100) {
    const response = await fetch(
      `${this.baseUrl}/sessions/${sessionId}/logs?service=${service}&lines=${lines}`
    );
    return await response.json();
  }
}

// Usage
const client = new DisposableComputeClient();
client.createSession("run_repo", "https://github.com/example/hello-world.git", {
  ttl_minutes: 60
}).then(session => {
  console.log(`Created session: ${session.session_id}`);
});
```

## Webhook Integration

The platform can be extended to support webhooks for GitHub integration:

### GitHub Webhook Payload
```json
{
  "action": "opened",
  "number": 142,
  "pull_request": {
    "head": {
      "repo": {
        "clone_url": "https://github.com/example/myapp.git"
      },
      "ref": "feature/new-feature"
    }
  }
}
```

### Webhook Handler
```python
from fastapi import FastAPI, Request
import hashlib
import hmac
import json

@app.post("/webhooks/github")
async def github_webhook(request: Request):
    # Verify webhook signature
    signature = request.headers.get('X-Hub-Signature-256')
    body = await request.body()

    # Verify signature (implement your secret verification)
    expected_signature = "sha256=" + hmac.new(
        secret.encode(),
        body,
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(signature, expected_signature):
        return {"error": "Invalid signature"}

    payload = json.loads(body)

    if payload.get("action") == "opened":
        pr = payload["pull_request"]
        repo_url = pr["head"]["repo"]["clone_url"]
        ref = pr["head"]["ref"]
        pr_number = payload["number"]

        # Create preview environment
        session = await session_manager.create_session(
            session_type="preview",
            repo_url=repo_url,
            repo_ref=ref,
            pr_number=pr_number
        )

        return {"message": f"Created preview for PR #{pr_number}", "session_id": session.id}

    return {"message": "Webhook processed"}
```

This API documentation provides comprehensive information about all endpoints, request/response formats, examples, and integration patterns for the Disposable Compute Platform.