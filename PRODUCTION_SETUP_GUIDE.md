# 🚀 Production Setup Guide - Vendor Registration System

> **Complete guide for frontend team to integrate with the AI-powered vendor registration system**

---

## 📋 Table of Contents

1. [System Overview](#system-overview)
2. [Architecture](#architecture)
3. [Quick Start](#quick-start)
4. [API Documentation - Chatbot Registration](#api-documentation---chatbot-registration)
5. [Email Registration Flow](#email-registration-flow)
6. [Folder Structure](#folder-structure)
7. [Environment Configuration](#environment-configuration)
8. [Testing](#testing)
9. [Troubleshooting](#troubleshooting)

---

## 🎯 System Overview

This is a **production-ready AI agent-based vendor registration system** that accepts vendor registrations through:

1. **Chatbot Interface** - Interactive conversational registration via REST APIs
2. **Email Submission** - Automated processing via Nylas webhook integration

### Key Features:
- ✅ Conversational chatbot for guided vendor registration
- ✅ Automatic document validation (Aadhaar, PAN, GST, Catalogue)
- ✅ AI-powered OCR using OpenAI Vision API
- ✅ CSV catalogue processing with Pandas
- ✅ Real-time webhook processing for email submissions
- ✅ Automated batch processing with BullMQ + Redis
- ✅ MongoDB Atlas for data persistence

### Supported Documents:
1. **Aadhaar Card** (PDF/PNG/JPG) - Identity proof
2. **PAN Card** (PDF/PNG/JPG) - Tax identification
3. **GST Certificate** (PDF/PNG/JPG) - Business registration
4. **Catalogue** (CSV) - Product inventory (optional for email, required for chatbot)

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         VENDOR REGISTRATION                      │
│                                                                  │
│  ┌──────────────┐              ┌─────────────────┐             │
│  │   Chatbot    │              │  Email Webhook  │             │
│  │   (Frontend) │              │   (Nylas API)   │             │
│  └──────┬───────┘              └────────┬────────┘             │
│         │                               │                       │
│         └───────────┬───────────────────┘                       │
│                     ▼                                            │
│         ┌─────────────────────┐                                 │
│         │   FastAPI Backend   │                                 │
│         │   (Port 8001)       │                                 │
│         │  • Chatbot APIs     │                                 │
│         │  • Webhook Handler  │                                 │
│         │  • PDF Converter    │                                 │
│         │  • CSV Processor    │                                 │
│         └──────────┬──────────┘                                 │
│                    │                                             │
│         ┌──────────▼──────────┐                                 │
│         │   MongoDB Atlas     │                                 │
│         │  (Cloud Database)   │                                 │
│         │  • Vendor Records   │                                 │
│         │  • Documents Meta   │                                 │
│         │  • Batches          │                                 │
│         └──────────┬──────────┘                                 │
│                    │                                             │
│         ┌──────────▼──────────┐                                 │
│         │  Queue Service      │                                 │
│         │  (Node.js + BullMQ) │                                 │
│         │  (Port 3000)        │                                 │
│         │  • Stage 3 Scheduler│                                 │
│         │  • Document Batching│                                 │
│         │  • Job Queue        │                                 │
│         └──────────┬──────────┘                                 │
│                    │                                             │
│         ┌──────────▼──────────┐                                 │
│         │   Redis Queue       │                                 │
│         │   (Port 6379)       │                                 │
│         └──────────┬──────────┘                                 │
│                    │                                             │
│         ┌──────────▼──────────┐                                 │
│         │  Async Workers      │                                 │
│         │  • 50 Concurrent    │                                 │
│         │  • OpenAI Vision    │                                 │
│         │  • OCR Extraction   │                                 │
│         └─────────────────────┘                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Processing Pipeline:

**Stage 1**: Frontend submission (Chatbot/Email)
**Stage 2**: Document download + PDF conversion + Catalogue processing (immediate)
**Stage 3**: Smart batching (every 5 seconds, excludes catalogue)
**Stage 4**: AI extraction with OpenAI Vision API (Aadhaar/PAN/GST only)

---

## ⚡ Quick Start

### Prerequisites:
- Python 3.14+
- Node.js 24.10+
- Redis 5.0+ (running on localhost:6379)
- MongoDB Atlas account (cloud database)

### 1️⃣ Start FastAPI Backend (Python)

```powershell
cd backend

# Activate virtual environment
..\vendor\Scripts\activate

# Install dependencies (first time only)
pip install -r requirements.txt

# Start server with 4 workers
uvicorn main:app --host 0.0.0.0 --port 8001 --workers 4
```

**Expected Output:**
```
✅ MongoDB connected!
   Database: invoice_processing
INFO: Uvicorn running on http://0.0.0.0:8001
```

**API Base URL:** `http://164.52.222.144:8001`

---

### 2️⃣ Start Queue Service (Node.js)

```powershell
cd queue_service

# Install dependencies (first time only)
npm install

# Start queue service with scheduler
node index.js
```

**Expected Output:**
```
📅 Stage 3 Scheduler Configuration:
   🔄 Schedule: */5 * * * * * (every 5 seconds)
✅ Stage 3 auto-scheduler initialized
🚀 BullMQ Queue Service running on port 3000
```

---

### 3️⃣ Start Stage 3 Scheduler Worker (Node.js)

```powershell
cd queue_service

# Start scheduler worker (separate terminal)
node workers/stage3_scheduler_worker.js
```

**Expected Output:**
```
📅 Stage 3 Scheduler Configuration:
   🔄 Schedule: */5 * * * * * (every 5 seconds)
🚀 Stage 3 Scheduler Worker started
📅 Listening for scheduled batch creation jobs
```

---

### 4️⃣ Start Async Worker (Node.js)

```powershell
cd queue_service

# Start worker (50 concurrent jobs)
node workers/async_extraction_worker.js
```

**Expected Output:**
```
🚀 Async Worker started with concurrency: 50
📊 Processing queue: document_extraction
```

---

## 📡 API Documentation - Chatbot Registration

### Base URL
```
http://164.52.222.144:8001/api/v1/chat
```

---

### 1. **POST** `/api/v1/chat/start` - Start Chat Session

**Description:** Initialize a new vendor registration session

**Request:**
```http
POST /api/v1/chat/start
Content-Type: application/json

{}
```

**Response:**
```json
{
  "session_id": "abc123def456",
  "message": "Welcome! I'll help you register as a vendor. Please provide your full name.",
  "stage": "COLLECT_BASIC_INFO",
  "next_step": "full_name"
}
```

**Frontend Usage:**
```javascript
const response = await fetch('http://164.52.222.144:8001/api/v1/chat/start', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({})
});
const data = await response.json();
console.log('Session ID:', data.session_id);
```

---

### 2. **POST** `/api/v1/chat/message/{session_id}` - Send Message

**Description:** Send user responses to collect basic information

**Request:**
```http
POST /api/v1/chat/message/{session_id}
Content-Type: application/json

{
  "message": "Ankit Kumar"
}
```

**Response Examples:**

**Collecting Name:**
```json
{
  "response": "Thank you! What is your company name?",
  "stage": "COLLECT_BASIC_INFO",
  "next_step": "company_name",
  "progress": {
    "collected": ["full_name"],
    "remaining": ["company_name", "age", "gender", "role", "email", "mobile", "address"]
  }
}
```

**All Info Collected:**
```json
{
  "response": "Perfect! Now please upload your documents:\n1. Aadhaar Card (PDF/PNG/JPG)\n2. PAN Card (PDF/PNG/JPG)\n3. GST Certificate (PDF/PNG/JPG)\n4. Product Catalogue (CSV)\n\nPlease upload Aadhaar first.",
  "stage": "AADHAAR_REQUEST",
  "basic_info": {
    "full_name": "Ankit Kumar",
    "company_name": "TechCorp",
    "age": "30",
    "gender": "Male",
    "role": "Vendor",
    "email": "ankit@techcorp.com",
    "mobile": "+91-9876543210",
    "address": "123 Street, Delhi-110001"
  }
}
```

**Frontend Usage:**
```javascript
const response = await fetch(`http://164.52.222.144:8001/api/v1/chat/message/${sessionId}`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ message: userInput })
});
const data = await response.json();
console.log('Bot Response:', data.response);
```

---

### 3. **POST** `/api/v1/chat/upload-document/{session_id}` - Upload Document

**Description:** Upload vendor documents (Aadhaar/PAN/GST/Catalogue)

**Request:**
```http
POST /api/v1/chat/upload-document/{session_id}
Content-Type: multipart/form-data

document_type: aadhaar
file: [binary file data]
```

**Parameters:**
- `document_type`: One of `aadhaar`, `pan`, `gst`, `catalogue`
- `file`: Binary file (PDF/PNG/JPG for docs, CSV for catalogue)

**Validation Rules:**
| Document Type | Allowed Extensions | Max Size |
|--------------|-------------------|----------|
| Aadhaar      | .pdf, .png, .jpg  | 10 MB    |
| PAN          | .pdf, .png, .jpg  | 10 MB    |
| GST          | .pdf, .png, .jpg  | 10 MB    |
| Catalogue    | .csv              | 10 MB    |

**Response:**
```json
{
  "message": "✅ Aadhaar uploaded successfully! Please upload PAN Card next.",
  "document_type": "aadhaar",
  "filename": "aadhaar.pdf",
  "stage": "PAN_REQUEST",
  "documents_status": {
    "aadhaar": "✅",
    "pan": "⏳",
    "gst": "⏳",
    "catalogue": "⏳"
  }
}
```

**Error Response:**
```json
{
  "detail": "Invalid file type for aadhaar. Expected: .pdf, .png, .jpg"
}
```

**Frontend Usage (with FormData):**
```javascript
const formData = new FormData();
formData.append('document_type', 'aadhaar');
formData.append('file', fileInput.files[0]);

const response = await fetch(`http://164.52.222.144:8001/api/v1/chat/upload-document/${sessionId}`, {
  method: 'POST',
  body: formData
});
const data = await response.json();
console.log('Upload Status:', data.message);
```

---

### 4. **GET** `/api/v1/chat/confirmation-summary/{session_id}` - Get Confirmation Summary

**Description:** Retrieve complete vendor information before final submission

**Request:**
```http
GET /api/v1/chat/confirmation-summary/{session_id}
```

**Response:**
```json
{
  "session_id": "abc123def456",
  "basic_info": {
    "full_name": "Ankit Kumar",
    "company_name": "TechCorp",
    "age": "30",
    "gender": "Male",
    "role": "Vendor",
    "email": "ankit@techcorp.com",
    "mobile": "+91-9876543210",
    "address": "123 Street, Delhi-110001"
  },
  "documents": {
    "aadhaar": {
      "filename": "aadhaar.pdf",
      "uploaded_at": "2025-11-02T10:30:00",
      "status": "uploaded"
    },
    "pan": {
      "filename": "pan.pdf",
      "uploaded_at": "2025-11-02T10:31:00",
      "status": "uploaded"
    },
    "gst": {
      "filename": "gst.pdf",
      "uploaded_at": "2025-11-02T10:32:00",
      "status": "uploaded"
    },
    "catalogue": {
      "filename": "products.csv",
      "uploaded_at": "2025-11-02T10:33:00",
      "status": "uploaded"
    }
  },
  "ready_for_submission": true,
  "message": "Please review the information. Type 'confirm' to submit or 'cancel' to abort."
}
```

**Frontend Usage:**
```javascript
const response = await fetch(`http://164.52.222.144:8001/api/v1/chat/confirmation-summary/${sessionId}`);
const data = await response.json();

// Display summary to user
console.log('Vendor Name:', data.basic_info.full_name);
console.log('Documents:', Object.keys(data.documents).length);
console.log('Ready:', data.ready_for_submission);
```

---

### 5. **POST** `/api/v1/chat/confirm-and-submit` - Confirm And Submit Vendor

**Description:** Final submission - creates vendor record and triggers processing

**Request:**
```http
POST /api/v1/chat/confirm-and-submit
Content-Type: application/json

{
  "session_id": "abc123def456"
}
```

**Response (Success):**
```json
{
  "status": "success",
  "vendor_id": "VENDOR_0065_ankit_techcorp_com",
  "message": "✅ Registration successful! Your vendor ID is VENDOR_0065_ankit_techcorp_com. Documents are being processed.",
  "processing_info": {
    "catalogue_processed": true,
    "catalogue_products": 20,
    "documents_queued": ["aadhaar", "pan", "gst"],
    "estimated_processing_time": "2-3 minutes"
  }
}
```

**Response (Error - Missing Documents):**
```json
{
  "detail": "Cannot submit: Missing documents - PAN, GST"
}
```

**Frontend Usage:**
```javascript
const response = await fetch('http://164.52.222.144:8001/api/v1/chat/confirm-and-submit', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ session_id: sessionId })
});
const data = await response.json();

if (data.status === 'success') {
  console.log('Vendor ID:', data.vendor_id);
  console.log('Catalogue Products:', data.processing_info.catalogue_products);
  // Show success message to user
} else {
  console.error('Submission failed:', data.detail);
}
```

---

### 6. **GET** `/api/v1/chat/history/{session_id}` - Get Chat History

**Description:** Retrieve complete conversation history for a session

**Request:**
```http
GET /api/v1/chat/history/{session_id}
```

**Response:**
```json
{
  "session_id": "abc123def456",
  "messages": [
    {
      "sender": "bot",
      "message": "Welcome! I'll help you register as a vendor.",
      "timestamp": "2025-11-02T10:25:00"
    },
    {
      "sender": "user",
      "message": "Ankit Kumar",
      "timestamp": "2025-11-02T10:25:30"
    },
    {
      "sender": "bot",
      "message": "Thank you! What is your company name?",
      "timestamp": "2025-11-02T10:25:31"
    }
  ],
  "current_stage": "DOCUMENT_UPLOAD",
  "basic_info": { ... }
}
```

---

## 📧 Email Registration Flow

### Overview
Vendors can also register by sending an email with documents attached. The system automatically processes emails via **Nylas webhook integration**.

### Email Format:

**To:** `your-nylas-email@example.com`

**Subject:** `Vendor Registration - CompanyName`

**Body:**
```
Hello,

Please register our company as a vendor with the following details:

Full Name: Rajesh Sharma
Age: 35
Gender: Male
Role: Vendor
Company: AutoParts India
Official Email: rajesh@autoparts.com
Mobile: +91-9988776655
Registered Address: 45 MG Road, Bangalore-560001

Please find the attached documents.

Thank you!
```

**Attachments:**
- `aadhaar.pdf` (or `aadhar_card.png`)
- `pan.pdf` (or `pan_card.jpg`)
- `gst.pdf` (or `gst_certificate.pdf`)
- `catalogue.csv` (optional - product inventory)

### Processing:
1. Nylas sends webhook to `http://164.52.222.144:8001/webhooks/nylas/message-created`
2. Backend validates subject, body, and attachments
3. Downloads attachments and converts PDFs to images
4. Processes CSV catalogue immediately (if present)
5. Creates MongoDB vendor record with status `ready_for_extraction`
6. Stage 3 scheduler picks up vendor within 5 seconds
7. Creates batches for Aadhaar/PAN/GST (catalogue skipped)
8. Async worker extracts data using OpenAI Vision API

### Webhook Endpoint:
```
POST http://164.52.222.144:8001/webhooks/nylas/message-created
```

**Response:**
```json
{
  "status": "success",
  "vendor_id": "VENDOR_0066_rajesh_autoparts_com",
  "processing_started": true
}
```

---

## 📁 Folder Structure

```
vendor_backend/
├── backend/                          # FastAPI Python Backend
│   ├── main.py                       # FastAPI app entry point
│   ├── models.py                     # Pydantic data models (DocumentType, ChatStage, etc.)
│   ├── database.py                   # MongoDB connection setup
│   ├── requirements.txt              # Python dependencies
│   ├── .env                          # Backend configuration (MongoDB, OpenAI, Nylas)
│   │
│   ├── routes/                       # API endpoints
│   │   ├── chat_enhanced.py          # 🔥 Chatbot registration APIs (6 endpoints)
│   │   ├── documents.py              # Document management
│   │   ├── vendor_processing.py      # Vendor CRUD operations
│   │   └── webhook_endpoints.py      # Nylas webhook handler
│   │
│   ├── services/                     # Business logic
│   │   ├── webhook_processor.py      # 🔥 Email registration processor
│   │   ├── vendor_email_service.py   # Email validation & classification
│   │   ├── nylas_service.py          # Nylas API client
│   │   ├── ocr_service.py            # OpenAI Vision API integration
│   │   └── tts_service.py            # Text-to-speech (optional)
│   │
│   ├── utils/                        # Utilities
│   │   ├── catalogue_processor.py    # 🔥 CSV catalogue processor (Pandas)
│   │   ├── pdf_converter.py          # PDF to PNG conversion
│   │   ├── csv_parser.py             # CSV parsing utilities
│   │   ├── validators.py             # Input validation
│   │   └── mongo_utils.py            # MongoDB helpers
│   │
│   ├── vendors/                      # 🗂️ Vendor workspace storage
│   │   └── VENDOR_0001_email_com/
│   │       ├── documents/            # Original uploaded files
│   │       ├── extracted/            # AI extraction results (JSON)
│   │       ├── metadata.json         # Vendor metadata
│   │       └── email_raw.json        # Raw email data (if from email)
│   │
│   └── data/                         # Session data (chatbot)
│       ├── chat_messages.json        # Chat history
│       ├── documents.json            # Document metadata
│       └── vendor_drafts.json        # In-progress registrations
│
├── queue_service/                    # Node.js Queue Service (BullMQ)
│   ├── index.js                      # 🔥 Main server + Stage 3 scheduler
│   ├── package.json                  # Node.js dependencies
│   ├── .env                          # Queue service configuration
│   │
│   ├── queues/                       # BullMQ queue definitions
│   │   └── document_queue.js         # Document extraction queue
│   │
│   ├── services/                     # Queue business logic
│   │   ├── stage3_scheduler.js       # 🔥 Auto-scheduler (every 5 seconds)
│   │   ├── batching_service.js       # 🔥 Smart document batching
│   │   ├── extraction_service.js     # Document extraction logic
│   │   ├── mongo_service.js          # MongoDB operations
│   │   └── async_extraction_service.js # Async job submission
│   │
│   ├── workers/                      # Background workers
│   │   ├── async_extraction_worker.js # 🔥 50 concurrent workers
│   │   └── stage3_scheduler_worker.js # Scheduler worker (DO NOT RUN - conflicts with index.js)
│   │
│   └── routes/                       # Callback endpoints
│       └── callback_routes.js        # OCR result callbacks
│
└── vendor/                           # Python virtual environment
    └── (Python 3.14 environment)
```

---

## 🔑 Key Files Explained

### **Backend (Python)**

#### 1. `backend/main.py`
- **Purpose:** FastAPI application entry point
- **Responsibilities:**
  - Initialize FastAPI app
  - Register all API routes
  - Setup CORS middleware
  - MongoDB connection on startup
  - Health check endpoint

#### 2. `backend/routes/chat_enhanced.py` ⭐
- **Purpose:** Complete chatbot registration flow
- **Key Functions:**
  - `start_chat()` - Initialize session
  - `send_message()` - Process user input
  - `upload_document_endpoint()` - Handle file uploads
  - `get_confirmation_summary()` - Pre-submission review
  - `confirm_and_submit_vendor()` - Final submission + processing
  - `get_chat_history()` - Retrieve conversation
- **Stage Management:**
  - COLLECT_BASIC_INFO → Ask for name, company, email, etc.
  - AADHAAR_REQUEST → Request Aadhaar upload
  - PAN_REQUEST → Request PAN upload
  - GST_REQUEST → Request GST upload
  - CATALOGUE_REQUEST → Request catalogue CSV
  - READY_FOR_CONFIRMATION → All docs uploaded
  - PROCESSING → Vendor created, extraction started

#### 3. `backend/services/webhook_processor.py` ⭐
- **Purpose:** Process vendor registration emails
- **Key Functions:**
  - `process_webhook()` - Main webhook handler
  - `_create_vendor_and_download()` - Create vendor + download attachments
  - `extract_basic_info()` - Parse email body for vendor details
  - Immediate catalogue processing (Stage 2)
  - MongoDB vendor record creation

#### 4. `backend/utils/catalogue_processor.py` ⭐
- **Purpose:** CSV catalogue validation and parsing
- **Key Functions:**
  - `process_csv()` - Read CSV with multiple encoding support
  - `validate_columns()` - Check required columns (Model Name, Years, etc.)
  - `calculate_confidence()` - Data quality score (0.0-1.0)
  - `save_to_extracted_folder()` - Save parsed JSON
- **Encoding Support:** UTF-8, Latin-1, ISO-8859-1, Windows-1252

#### 5. `backend/models.py`
- **Purpose:** Pydantic data models
- **Key Models:**
  - `DocumentType` - Enum: aadhaar, pan, gst, catalogue
  - `ChatStage` - Enum: conversation stages
  - `BasicDetailsData` - Vendor basic info schema
  - `ChatMessage` - Message structure

---

### **Queue Service (Node.js)**

#### 6. `queue_service/index.js` ⭐
- **Purpose:** Main queue service with auto-scheduler
- **Responsibilities:**
  - Start Express server on port 3000
  - Initialize BullMQ queues
  - Start Stage 3 scheduler (every 5 seconds)
  - Register callback routes
  - Health check endpoints

#### 7. `queue_service/services/stage3_scheduler.js` ⭐
- **Purpose:** Automated batch creation scheduler
- **Configuration:**
  - Interval: Every 5 seconds (`*/5 * * * * *`)
  - Min vendors: 1 (process immediately)
- **Key Functions:**
  - `initialize()` - Setup cron job
  - `processScheduledJob()` - Execute batching logic
  - Calls `batchingService.createBatchesFromReadyVendors()`

#### 8. `queue_service/workers/stage3_scheduler_worker.js` ⭐
- **Purpose:** Stage 3 scheduler worker (run separately)
- **Responsibilities:**
  - Listen to stage3_scheduler queue
  - Process scheduled batch creation jobs
  - Executes every 5 seconds via cron
- **How to run:** `node workers/stage3_scheduler_worker.js` (separate terminal)

#### 8. `queue_service/workers/stage3_scheduler_worker.js` ⭐
- **Purpose:** Stage 3 scheduler worker (run separately)
- **Responsibilities:**
  - Listen to stage3_scheduler queue
  - Process scheduled batch creation jobs
  - Executes every 5 seconds via cron
- **How to run:** `node workers/stage3_scheduler_worker.js` (separate terminal)

#### 9. `queue_service/services/batching_service.js` ⭐
- **Purpose:** Smart document grouping and batch creation
- **Key Functions:**
  - `createBatchesFromReadyVendors()` - Main batching logic
  - `groupDocumentsByType()` - Group by aadhaar/pan/gst (excludes catalogue!)
  - `createBatches()` - Create 10-document batches
  - `addBatchesToQueue()` - Submit to BullMQ
- **Batch Size:** 10 documents per batch (configurable in .env)

#### 10. `queue_service/workers/async_extraction_worker.js` ⭐
- **Purpose:** Process batches with OpenAI Vision API
- **Configuration:**
  - Concurrency: 50 jobs simultaneously
  - Rate limit: 500 RPM (OpenAI)
- **Key Functions:**
  - Read document images from file system
  - Submit to OpenAI Vision API for OCR
  - Save extracted JSON to `vendors/{vendor_id}/extracted/`
  - Update MongoDB with extraction results

#### 11. `queue_service/services/mongo_service.js`
- **Purpose:** MongoDB operations for queue service
- **Key Functions:**
  - `getVendorsReadyForExtraction()` - Find vendors with status `ready_for_extraction`
  - `updateVendorsStatus()` - Update to `processing` or `completed`
  - `saveBatch()` - Store batch metadata

---

## 🔧 Environment Configuration

### Backend `.env` (FastAPI)

```properties
# MongoDB Atlas (Cloud Database)
MONGO_URI=mongodb+srv://invoice_user:password@cluster0.mongodb.net/invoice_processing?retryWrites=true&w=majority

# OpenAI API (for OCR)
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxx

# Nylas Email API
NYLAS_API_KEY=nyk_v0_xxxxxxxxxxxxx
NYLAS_CLIENT_ID=xxxxxxxxxxxxx
NYLAS_GRANT_ID=xxxxxxxxxxxxx
NYLAS_CLIENT_SECRET=nyk_v0_xxxxxxxxxxxxx
NYLAS_WEBHOOK_SECRET=xxxxxxxxxxxxx

# Server Configuration
HOST=0.0.0.0
PORT=8001
```

### Queue Service `.env` (Node.js)

```properties
# Environment
NODE_ENV=production

# Server
PORT=3000
SERVER_URL=http://164.52.222.144:8001

# MongoDB Atlas (Same as backend)
MONGO_URI=mongodb+srv://invoice_user:password@cluster0.mongodb.net/invoice_processing?retryWrites=true&w=majority

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# OpenAI API
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxx
OPENAI_RATE_LIMIT_RPM=500

# Stage 3 Scheduler
STAGE3_AUTO_ENABLED=true
STAGE3_SCHEDULE_INTERVAL=*/5 * * * * *
STAGE3_MIN_VENDORS=1

# Batching
BATCH_SIZE=10
```

---

## 🧪 Testing

### Test Chatbot Registration (Postman/cURL)

#### Step 1: Start Session
```bash
curl -X POST http://164.52.222.144:8001/api/v1/chat/start \
  -H "Content-Type: application/json" \
  -d '{}'
```

#### Step 2: Send Messages
```bash
curl -X POST http://164.52.222.144:8001/api/v1/chat/message/{session_id} \
  -H "Content-Type: application/json" \
  -d '{"message": "Ankit Kumar"}'
```

#### Step 3: Upload Documents
```bash
curl -X POST http://164.52.222.144:8001/api/v1/chat/upload-document/{session_id} \
  -F "document_type=aadhaar" \
  -F "file=@aadhaar.pdf"
```

#### Step 4: Get Summary
```bash
curl -X GET http://164.52.222.144:8001/api/v1/chat/confirmation-summary/{session_id}
```

#### Step 5: Submit
```bash
curl -X POST http://164.52.222.144:8001/api/v1/chat/confirm-and-submit \
  -H "Content-Type: application/json" \
  -d '{"session_id": "{session_id}"}'
```

### Test Email Registration

Send email to Nylas-configured address with:
- Subject: "Vendor Registration - TestCompany"
- Body: Vendor details (name, email, mobile, address, company)
- Attachments: aadhaar.pdf, pan.pdf, gst.pdf, catalogue.csv

### Check Processing Status

```bash
# Check queue dashboard
http://localhost:3000/admin/queues

# Check extracted data
ls backend/vendors/VENDOR_0065_*/extracted/
```

---

## 🐛 Troubleshooting

### Issue: "MongoDB connection refused"
**Solution:** Check `.env` file has correct `MONGO_URI` for MongoDB Atlas

### Issue: "Documents not being processed"
**Solution:** 
1. Ensure Redis is running: `redis-server`
2. Check queue service is running: `node index.js`
3. Start async worker: `node workers/async_extraction_worker.js`
4. Verify vendor status in MongoDB is `ready_for_extraction`

### Issue: "Catalogue encoding error"
**Solution:** Catalogue processor now supports UTF-8, Latin-1, ISO-8859-1, Windows-1252. Ensure CSV is in one of these formats.

### Issue: "Scheduler running every 1 minute instead of 5 seconds"
**Solution:** Update `queue_service/.env`: `STAGE3_SCHEDULE_INTERVAL=*/5 * * * * *`

### Issue: "Email webhook not receiving events"
**Solution:** 
1. Check Nylas webhook is configured: `POST /webhooks/nylas/message-created`
2. Verify `NYLAS_WEBHOOK_SECRET` matches Nylas dashboard
3. Check FastAPI logs for webhook received messages

### Issue: "CSV catalogue rejected in email"
**Solution:** Filename must contain: "catalogue", "catalog", "product", or "inventory"

---

## 📊 Processing Times

| Stage | Time | Description |
|-------|------|-------------|
| Stage 1 | Instant | User submission (chatbot/email) |
| Stage 2 | 2-5s | Document download + PDF conversion + CSV processing |
| Stage 3 | 5s | Scheduler triggers batching |
| Stage 4 | 30-60s | OpenAI Vision API extraction (per batch of 10) |
| **Total** | **~1-2 min** | Complete end-to-end processing |

---

## 🎯 Important Notes for Frontend Team

1. **Session Management:** Store `session_id` on frontend - required for all subsequent API calls

2. **File Upload:** Use `FormData` for document uploads, not JSON

3. **Progress Tracking:** Use `documents_status` object to show upload progress UI

4. **Error Handling:** All endpoints return 4xx/5xx with `detail` field for error messages

5. **Catalogue CSV Format:**
   - Required columns: Model Name, Years, Vehicle Type, Description
   - Optional columns: Submodels, Image URL, Page URL
   - UTF-8 or Latin-1 encoding

6. **Document Naming:** For email registration, files must contain keywords:
   - Aadhaar: "aadhar" or "aadhaar"
   - PAN: "pan"
   - GST: "gst"
   - Catalogue: "catalogue", "catalog", "product", or "inventory"

7. **Rate Limits:** OpenAI Vision API has 500 RPM limit (handled automatically by queue)

8. **Webhook Security:** Nylas webhooks are signature-verified automatically

---

## 🚀 Production Checklist

- [ ] MongoDB Atlas cluster is running and accessible
- [ ] Redis server is running on localhost:6379
- [ ] FastAPI backend running on port 8001 (4 workers)
- [ ] Queue service running on port 3000 with scheduler
- [ ] Stage 3 scheduler worker running (separate terminal)
- [ ] Async worker running (50 concurrency)
- [ ] Nylas webhook is configured and verified
- [ ] OpenAI API key is valid with sufficient credits
- [ ] `.env` files are configured correctly
- [ ] Firewall allows incoming requests on port 8001
- [ ] `backend/vendors/` directory exists and is writable

---

## 📞 Support

For issues or questions, check the logs:

**Backend Logs:**
```powershell
cd backend
uvicorn main:app --host 0.0.0.0 --port 8001 --workers 4 --log-level info
```

**Queue Service Logs:**
```powershell
cd queue_service
node index.js
```

**Stage 3 Scheduler Worker Logs:**
```powershell
cd queue_service
node workers/stage3_scheduler_worker.js
```

**Async Worker Logs:**
```powershell
cd queue_service
node workers/async_extraction_worker.js
```

---

**🎉 System is now production-ready for vendor registration!**
