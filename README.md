# Messaging Service

This project is a FastAPI-based messaging service for creating conversations, managing recipients, sending messages, and tracking delivery updates through webhooks and background workers.

## Run with Docker Compose

### 1. Copy the environment file

```bash
cp .env.example .env
```

### 2. Change required environment variables


### 3. Start the stack

```bash
docker compose up --build
```

This starts:
- PostgreSQL
- Redis
- the API service
- Celery workers
- Celery beat
- Flower

### 4. Check the API health

Open the following URLs:

- http://localhost:8000/health
- http://localhost:8000/docs

## Default API base URL

When running locally with Docker Compose, use:

```text
http://localhost:8000/api/v1
```

## Authentication

Most endpoints require an API key header:

```http
X-API-Key: dev-key-1
```

The example values are defined in the environment file.

## Test the APIs

#### Import MessagingServiceAPI.postman_collection.json to test apis on postman

#### Or You can use swagger docs to test apis on this url http://localhost:8000/docs

#### or 

### 1. Create a recipient

```bash
curl -X POST http://localhost:8000/api/v1/recipients \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: dev-key-1' \
  -d '{
    "name": "Alice Nguyen",
    "phone_number": "+15551230001",
    "email": "alice@example.com",
    "external_id": "alice-001"
  }'
```

### 2. Create a conversation

```bash
curl -X POST http://localhost:8000/api/v1/conversations \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: dev-key-1' \
  -d '{
    "subject": "Welcome campaign",
    "metadata": {"channel": "sms"}
  }'
```

### 3. Send a message to one or multiple recipients

```bash
curl -X POST http://localhost:8000/api/v1/conversations/<conversation_id>/messages \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: dev-key-1' \
  -d '{
    "recipient_ids": ["<recipient_id>"],
    "channel": "sms",
    "content": "Hello from the messaging service",
    "idempotency_key": "demo-send-001"
  }'
```

To send to multiple recipients, pass several IDs:

```bash
curl -X POST http://localhost:8000/api/v1/conversations/<conversation_id>/messages \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: dev-key-1' \
  -d '{
    "recipient_ids": ["<recipient_id_1>", "<recipient_id_2>"],
    "channel": "sms",
    "content": "Hello to multiple recipients",
    "idempotency_key": "demo-send-002"
  }'
```

### 4. Upload recipients with CSV

```bash
curl -X POST http://localhost:8000/api/v1/recipients/import \
  -H 'X-API-Key: dev-key-1' \
  -F 'file=@recipient_test.csv'
```

### 5. View import job status

```bash
curl -X GET http://localhost:8000/api/v1/recipients/import/<job_id> \
  -H 'X-API-Key: dev-key-1'
```

## Run the tests

```bash
pytest
```

## Useful Docker commands

```bash
docker compose ps
docker compose logs -f api
docker compose logs -f worker
docker compose down
```

## Project structure

- app/api/v1/: API routes
- app/services/: business logic
- app/repositories/: persistence access
- app/models/: SQLAlchemy models
- app/workers/: Celery tasks
- tests/: automated tests
