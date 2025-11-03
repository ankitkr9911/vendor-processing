# 🐳 Docker Deployment Guide - Vendor Registration System

## 📋 Overview

This guide provides complete Docker containerization for the AI-powered Vendor Registration System. The system consists of 4 application containers plus Redis infrastructure that work together to handle vendor registrations via chatbot and email.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                       Docker Compose Stack                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐        │
│  │   Backend    │───▶│ Queue Service│───▶│ Async Worker │        │
│  │  (FastAPI)   │    │   (Node.js)  │    │   (Node.js)  │        │
│  │  Port: 8001  │    │  Port: 3000  │    │     (BG)     │        │
│  └───────┬──────┘    └───────┬──────┘    └──────┬───────┘        │
│          │                   │                   │                 │
│          │                   ├──────────────────────┐              │
│          │                   │                      │              │
│          │          ┌────────▼────────┐    ┌───────▼────────┐    │
│          │          │  Stage3         │    │                │    │
│          │          │  Scheduler      │    │                │    │
│          │          │  (Node.js BG)   │    │                │    │
│          │          └────────┬────────┘    │                │    │
│          │                   │             │                │    │
│          └───────────────────┴─────────────┴────────────────┘    │
│                              │                                    │
│                     ┌────────▼────────┐                           │
│                     │  Redis (Cache)  │                           │
│                     │   Port: 6379    │                           │
│                     └─────────────────┘                           │
│                                                                   │
│  External Dependencies:                                          │
│  - MongoDB Atlas (Cloud Database)                                │
│  - OpenAI API (Document Extraction)                              │
│  - Nylas API (Email Webhooks)                                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📦 Container Specifications

### 1. Backend Container (FastAPI)
- **Base Image:** `python:3.10-slim`
- **Port:** 8001
- **Purpose:** 
  - Chatbot registration APIs (6 endpoints)
  - Nylas webhook processing
  - Document upload and validation
  - MongoDB operations
- **System Dependencies:**
  - **Poppler-utils:** Required for pdf2image (PDF to image conversion in OCR service)
  - **PyMuPDF (fitz):** Main PDF processing library (no system deps needed)
  - **Tesseract OCR:** Fallback OCR engine with multi-language support
  - **Hindi + English language data**
- **Health Check:** `GET /health` every 30s

### 2. Queue Service Container (Node.js)
- **Base Image:** `node:20-slim`
- **Port:** 3000
- **Purpose:**
  - BullMQ job queue management
  - Bull Board dashboard (queue monitoring)
  - API endpoints for queue status
- **Health Check:** `GET /health` every 30s

### 3. Async Worker Container (Node.js)
- **Base Image:** `node:20-slim`
- **Port:** None (background worker)
- **Purpose:**
  - Stage 4: Parallel document extraction
  - 50 concurrent job processing
  - OpenAI Vision API calls
- **Scaling:** Can deploy multiple replicas

### 4. Stage 3 Scheduler Container (Node.js)
- **Base Image:** `node:20-slim`
- **Port:** None (background scheduler)
- **Purpose:**
  - Stage 3: Smart document batching
  - Runs every 5 seconds (*/5 * * * * *)
  - Creates batches of 10 documents per vendor
- **Scaling:** Should NOT scale (only 1 instance needed)

---

## 🗄️ Infrastructure Dependencies

### Redis (included in docker-compose)
- **Base Image:** `redis:7-alpine`
- **Port:** 6379
- **Purpose:** 
  - BullMQ job queue backend
  - Job state persistence
- **Persistence:** Append-only file (AOF) enabled
- **Note:** Infrastructure component, not an application container

### External Services (client must provide)
- **MongoDB Atlas:** Cloud database
- **OpenAI API:** Document extraction
- **Nylas API:** Email webhooks

---

## 🚀 Quick Start

### Prerequisites
1. **Docker** (version 20.10+)
2. **Docker Compose** (version 2.0+)
3. **Git** (to clone repository)
4. **MongoDB Atlas Account** (free tier works)
5. **OpenAI API Key** (GPT-4 Vision access)
6. **Nylas Developer Account** (email webhooks)

---

### Step 1: Clone Repository

```bash
git clone https://github.com/ankitkr9911/vendor-processing.git
cd vendor-processing
```

---

### Step 2: Configure Environment Variables

```bash
# Copy template
cp .env.example .env

# Edit with your credentials
nano .env  # or use any text editor
```

**Required Configuration:**

```env
# MongoDB Atlas Connection String
MONGO_URI=mongodb+srv://username:password@cluster0.mongodb.net/invoice_processing?retryWrites=true&w=majority

# OpenAI API Key (GPT-4 Vision)
OPENAI_API_KEY=sk-proj-your-actual-key-here

# Nylas Email API
NYLAS_API_KEY=nyk_v0_your-key
NYLAS_CLIENT_ID=your-client-id
NYLAS_GRANT_ID=your-grant-id
NYLAS_CLIENT_SECRET=nyk_v0_your-secret
NYLAS_REDIRECT_URI=http://your-server-ip:8001/api/v1/admin/nylas/callback
NYLAS_WEBHOOK_SECRET=your-webhook-secret

# Admin Portal
ADMIN_EMAIL=admin@vendorportal.com
ADMIN_PASSWORD=secure_password_here

# JWT Secret (generate random string)
JWT_SECRET_KEY=your-secure-jwt-secret-key
```

---

### Step 3: Build and Start Services

```bash
# Build all containers
docker-compose build

# Start all services in detached mode
docker-compose up -d

# View logs
docker-compose logs -f
```

**Expected Output:**
```
✅ Redis started on port 6379
✅ Backend started on port 8001
✅ Queue Service started on port 3000
✅ Async Worker started (background)
```

---

### Step 4: Verify Deployment

```bash
# Check all containers are running
docker-compose ps

# Expected output:
# NAME                    STATUS              PORTS
# vendor-backend          Up (healthy)        0.0.0.0:8001->8001/tcp
# vendor-queue-service    Up (healthy)        0.0.0.0:3000->3000/tcp
# vendor-async-worker     Up                  -
# vendor-redis            Up (healthy)        0.0.0.0:6379->6379/tcp
```

**Health Checks:**

```bash
# Backend health
curl http://localhost:8001/health

# Queue service health
curl http://localhost:3000/health

# Redis health
docker exec vendor-redis redis-cli ping
# Should return: PONG
```

---

## 📡 Accessing Services

### 1. FastAPI Backend
- **API Documentation:** http://localhost:8001/docs
- **ReDoc Documentation:** http://localhost:8001/redoc
- **Health Check:** http://localhost:8001/health
- **Chatbot Start:** POST http://localhost:8001/api/v1/chat/start

### 2. Queue Service
- **Bull Board Dashboard:** http://localhost:3000/admin/queues
  - Monitor job queues
  - View job statistics
  - Inspect failed jobs
- **Queue Stats:** http://localhost:3000/api/queue/stats

### 3. Redis
- **Port:** 6379 (localhost only)
- **Connect:** `redis-cli -h localhost -p 6379`

---

## 🔧 Management Commands

### Container Management

```bash
# Start all services
docker-compose up -d

# Stop all services
docker-compose down

# Restart specific service
docker-compose restart backend
docker-compose restart queue_service
docker-compose restart async_worker

# View logs (all services)
docker-compose logs -f

# View logs (specific service)
docker-compose logs -f backend
docker-compose logs -f queue_service
docker-compose logs -f async_worker

# Check container status
docker-compose ps

# Execute command in container
docker-compose exec backend bash
docker-compose exec queue_service sh
docker-compose exec redis redis-cli
```

---

### Scaling Workers

```bash
# Scale async workers to 3 replicas
docker-compose up -d --scale async_worker=3

# View scaled workers
docker-compose ps async_worker
```

---

### Data Management

```bash
# Backup MongoDB data (from container)
docker-compose exec backend python -c "
from database import db
import json
vendors = list(db.get_vendors_collection().find())
with open('backup.json', 'w') as f:
    json.dump(vendors, f, default=str)
"

# Clean Redis queue data
docker-compose exec redis redis-cli FLUSHALL

# View vendor files
ls -la backend/vendors/
```

---

### Cleanup

```bash
# Stop and remove containers
docker-compose down

# Remove containers + volumes (CAUTION: deletes Redis data)
docker-compose down -v

# Remove containers + volumes + images
docker-compose down -v --rmi all

# Clean up Docker system
docker system prune -af
```

---

## 🔍 Troubleshooting

### Backend Container Not Starting

**Check logs:**
```bash
docker-compose logs backend
```

**Common Issues:**
1. **Missing .env file**
   ```
   Solution: Copy .env.example to .env and configure
   ```

2. **MongoDB connection failed**
   ```
   Error: MONGO_URI not set or invalid
   Solution: Verify MongoDB Atlas URI in .env
   ```

3. **OpenAI API key invalid**
   ```
   Error: Incorrect API key provided
   Solution: Update OPENAI_API_KEY in .env
   ```

---

### Queue Service Connection Errors

**Check Redis connection:**
```bash
docker-compose logs redis
docker-compose exec redis redis-cli ping
```

**Check service logs:**
```bash
docker-compose logs queue_service
```

**Common Issues:**
1. **Redis not responding**
   ```
   Solution: Restart Redis container
   docker-compose restart redis
   ```

2. **Backend API unreachable**
   ```
   Error: ECONNREFUSED backend:8001
   Solution: Ensure backend container is healthy
   docker-compose ps backend
   ```

---

### Worker Not Processing Jobs

**Check worker logs:**
```bash
docker-compose logs async_worker
```

**Check queue dashboard:**
- Open: http://localhost:3000/admin/queues
- Look for failed jobs
- Check job error messages

**Common Issues:**
1. **OpenAI API rate limit**
   ```
   Error: Rate limit exceeded
   Solution: Wait or upgrade OpenAI plan
   ```

2. **Redis connection lost**
   ```
   Solution: Restart worker
   docker-compose restart async_worker
   ```

---

### Health Check Failures

**View health check status:**
```bash
docker-compose ps
```

**Check specific service:**
```bash
# Backend
curl http://localhost:8001/health

# Queue service
curl http://localhost:3000/health

# Redis
docker-compose exec redis redis-cli ping
```

---

##  Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MONGO_URI` | ✅ Yes | - | MongoDB Atlas connection string |
| `OPENAI_API_KEY` | ✅ Yes | - | OpenAI API key (GPT-4 Vision) |
| `NYLAS_API_KEY` | ✅ Yes | - | Nylas email API key |
| `NYLAS_CLIENT_ID` | ✅ Yes | - | Nylas OAuth client ID |
| `NYLAS_GRANT_ID` | ✅ Yes | - | Nylas grant ID for email access |
| `NYLAS_CLIENT_SECRET` | ✅ Yes | - | Nylas OAuth client secret |
| `NYLAS_REDIRECT_URI` | ✅ Yes | - | OAuth callback URL |
| `NYLAS_WEBHOOK_SECRET` | ✅ Yes | - | Webhook signature verification |
| `JWT_SECRET_KEY` | ✅ Yes | - | JWT token signing key |
| `ADMIN_EMAIL` | ✅ Yes | - | Admin portal login email |
| `ADMIN_PASSWORD` | ✅ Yes | - | Admin portal login password |
| `BATCH_SIZE` | No | 10 | Documents per batch |
| `STAGE3_SCHEDULE_INTERVAL` | No | */5 * * * * * | Batch creation cron |
| `WORKER_CONCURRENCY` | No | 50 | Max concurrent jobs |


## 📄 License

MIT License - See LICENSE file for details
