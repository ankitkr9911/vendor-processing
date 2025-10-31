# Vendor Backend System

A comprehensive vendor management system with intelligent chatbot, document processing, and email integration.

## Features

- **Conversational AI Chatbot**: Admin interface powered by OpenAI GPT-4o for natural language vendor queries
- **Hybrid Agentic System**: Combines pre-defined optimized functions with dynamic MongoDB query generation
- **Email Webhook Integration**: Nylas API for automated vendor registration via email
- **Document OCR Processing**: Automated extraction from Aadhar, PAN, and GST documents
- **Queue-based Processing**: Redis + Bull queues for background document processing
- **MongoDB Atlas**: Scalable database with comprehensive vendor data management

## Tech Stack

### Backend (Python)
- FastAPI framework
- Python 3.10+
- OpenAI GPT-4o
- MongoDB with Motor (async driver)
- Nylas API for email webhooks
- JWT authentication

### Queue Service (Node.js)
- Express.js
- Bull queues with Redis
- Document processing workers
- Batch scheduling system

## Setup

### Prerequisites
- Python 3.10+
- Node.js 20+
- MongoDB Atlas account
- OpenAI API key
- Nylas developer account
- Redis server

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/ankitkr9911/vendor_backend.git
cd vendor_backend
```

2. **Backend Setup**
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r backend/requirements.txt

# Create .env file in backend/ directory
cp backend/.env.example backend/.env
# Edit .env with your credentials
```

3. **Queue Service Setup**
```bash
cd queue_service
npm install
```

4. **Environment Configuration**

Create `backend/.env` with:
```env
# Server
HOST=0.0.0.0
PORT=8001
SERVER_URL=http://your-server-ip:8001

# Database
MONGO_URI=mongodb+srv://username:password@cluster.mongodb.net/database

# OpenAI
OPENAI_API_KEY=sk-...

# Nylas
NYLAS_CLIENT_ID=your_client_id
NYLAS_CLIENT_SECRET=your_secret
NYLAS_REDIRECT_URI=http://your-server-ip:8001/api/v1/admin/nylas/callback

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# Security
JWT_SECRET_KEY=your-secret-key
ADMIN_PASSWORD=your-admin-password
```

### Running the Application

**Development:**
```bash
# Terminal 1 - Backend
cd backend
uvicorn main:app --reload --port 8001

# Terminal 2 - Queue Service
cd queue_service
node index.js
```

**Production:**
```bash
# Backend
cd backend
gunicorn main:app -c gunicorn_config.py

# Queue Service
cd queue_service
node index.js &
```

## API Endpoints

### Admin Chatbot
- `POST /api/v1/admin/chatbot/query` - Natural language queries
- `GET /api/v1/admin/chatbot/history` - Chat history

### Vendor Management
- `GET /api/v1/admin/vendors` - List all vendors
- `GET /api/v1/admin/vendors/{id}` - Get vendor details
- `PATCH /api/v1/admin/vendors/{id}` - Update vendor
- `DELETE /api/v1/admin/vendors/{id}` - Delete vendor

### Document Processing
- `POST /api/v1/ocr/extract` - Extract data from document
- `GET /api/v1/admin/documents` - List documents
- `GET /api/v1/queue/status` - Queue status

### Webhooks
- `POST /webhook/nylas` - Nylas email webhook handler

## Chatbot Examples

```
"Show me all pending vendors"
"Find vendors whose age is greater than 30"
"Update John Doe's mobile number to 9876543210"
"List vendors from Mumbai registered in last 7 days"
"Search for vendors whose name is Rana Pratap"
```

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   FastAPI   │────▶│   MongoDB    │     │   Redis     │
│   Backend   │     │   Atlas      │     │   Queue     │
└──────┬──────┘     └──────────────┘     └──────┬──────┘
       │                                          │
       │            ┌──────────────┐             │
       └───────────▶│   OpenAI     │             │
                    │   GPT-4o     │             │
                    └──────────────┘             │
                                                  │
┌─────────────┐                          ┌───────▼──────┐
│   Nylas     │                          │   Node.js    │
│   Webhooks  │─────────────────────────▶│   Workers    │
└─────────────┘                          └──────────────┘
```

## Deployment

See `.env.server` for production configuration requirements.

**Key Production Changes:**
- Set `HOST=0.0.0.0` for external access
- Update `SERVER_URL` and `NYLAS_REDIRECT_URI` with public IP/domain
- Use strong `JWT_SECRET_KEY` and `ADMIN_PASSWORD`
- Enable HTTPS in production
- Configure firewall rules for ports 8001, 3000

## License

MIT

## Contact

For questions or support, contact: ankitkr1801@gmail.com
