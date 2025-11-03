# 🚀 Vendor Registration System

AI-powered vendor registration system with chatbot interface, email webhooks, and intelligent document processing.

## ✨ Features

- **🤖 Conversational Chatbot**: Step-by-step vendor registration via REST APIs
- **📧 Email Integration**: Automated processing via Nylas webhooks
- **📄 Document OCR**: AI-powered extraction from Aadhaar, PAN, GST, and Catalogues
- **⚡ Queue Processing**: Redis + BullMQ for parallel document processing (50 concurrent jobs)
- **🗄️ MongoDB Atlas**: Scalable cloud database with vendor workspaces
- **🐳 Docker Support**: Production-ready containerized deployment

## 🏗️ Tech Stack

### Backend (Python)
- **FastAPI** - High-performance async web framework
- **Python 3.10+** - Modern Python with type hints
- **OpenAI GPT-4 Vision** - Document extraction AI
- **Pandas** - CSV catalogue processing
- **Tesseract OCR** - Fallback OCR engine
- **PyMuPDF + Poppler** - PDF to image conversion

### Queue Service (Node.js)
- **Express.js** - Web server
- **BullMQ + Redis** - Job queue system
- **Bull Board** - Queue monitoring dashboard
- **MongoDB** - Database operations

## 📦 Quick Start

### Option 1: Docker Deployment (Recommended)

```bash
# Clone repository
git clone https://github.com/ankitkr9911/vendor-processing.git
cd vendor-processing

# Configure environment
cp .env.example .env
nano .env  # Add your credentials

# Start all services
docker-compose up -d

# View logs
docker-compose logs -f
```

**Access Points:**
- API Documentation: http://localhost:8001/docs
- Queue Dashboard: http://localhost:3000/admin/queues
- Health Check: http://localhost:8001/health

📖 **Full Docker Guide:** See [DOCKER_DEPLOYMENT_GUIDE.md](DOCKER_DEPLOYMENT_GUIDE.md)

---

### Option 2: Manual Setup

---

### Option 2: Manual Setup

#### Prerequisites
- Python 3.10+
- Node.js 20+
- Redis 5.0+
- MongoDB Atlas account
- OpenAI API key
- Nylas developer account

#### Installation Steps

1. **Clone the repository**
```bash
git clone https://github.com/ankitkr9911/vendor-processing.git
cd vendor-processing
```

2. **Backend Setup (Python)**
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
cd backend
pip install -r requirements.txt

# Configure environment
cp .env.example .env
nano .env  # Add your credentials
```

3. **Queue Service Setup (Node.js)**
```bash
cd queue_service
npm install

# Configure environment
cp .env.example .env
nano .env  # Add your credentials
```

4. **Start Services**

Terminal 1 - Backend:
```bash
cd backend
uvicorn main:app --host 0.0.0.0 --port 8001 --workers 4
```

Terminal 2 - Queue Service:
```bash
cd queue_service
node index.js
```

Terminal 3 - Async Worker:
```bash
cd queue_service
node workers/async_extraction_worker.js
```

📖 **Full Setup Guide:** See [PRODUCTION_SETUP_GUIDE.md](PRODUCTION_SETUP_GUIDE.md)

---

## 📡 API Endpoints

### Chatbot Registration APIs
- `POST /api/v1/chat/start` - Initialize session
- `POST /api/v1/chat/message/{session_id}` - Send message
- `POST /api/v1/chat/upload-document/{session_id}` - Upload document
- `GET /api/v1/chat/confirmation-summary/{session_id}` - Review data
- `POST /api/v1/chat/confirm-and-submit` - Final submission
- `GET /api/v1/chat/history/{session_id}` - Chat history

### Email Webhook
- `POST /webhooks/nylas/message-created` - Nylas webhook endpoint
- `GET /webhooks/nylas/health` - Webhook health check

### Queue Management
- `GET /admin/queues` - Bull Board dashboard
- `GET /api/queue/stats` - Queue statistics

**Interactive Docs:** http://localhost:8001/docs

---

## 🐳 Docker Commands

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Restart service
docker-compose restart backend

# Stop all services
docker-compose down

# Clean restart
docker-compose down && docker-compose build && docker-compose up -d

# Scale workers
docker-compose up -d --scale async_worker=3
```

---

## 📊 Monitoring

### Health Checks
```bash
# Backend
curl http://localhost:8001/health

# Queue Service
curl http://localhost:3000/health

# Redis
redis-cli ping
```

### Bull Board Dashboard
Monitor job queues and processing statistics:
- **URL:** http://localhost:3000/admin/queues
- **Features:** Real-time queue stats, failed job inspection, job retry

---

## 🔧 Configuration

### Required Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `MONGO_URI` | MongoDB connection string | `mongodb+srv://...` |
| `OPENAI_API_KEY` | OpenAI API key | `sk-proj-...` |
| `NYLAS_API_KEY` | Nylas email API key | `nyk_v0_...` |
| `NYLAS_CLIENT_ID` | Nylas OAuth client ID | `uuid` |
| `NYLAS_GRANT_ID` | Nylas email grant ID | `uuid` |
| `JWT_SECRET_KEY` | JWT signing secret | `random-string` |
| `ADMIN_EMAIL` | Admin login email | `admin@example.com` |
| `ADMIN_PASSWORD` | Admin login password | `secure-password` |

📄 **Full Configuration:** See [.env.example](.env.example)

---

## 📁 Project Structure

```
vendor-processing/
├── backend/                    # FastAPI Python backend
│   ├── routes/                 # API endpoints
│   ├── services/               # Business logic
│   ├── utils/                  # Utilities (PDF, CSV, OCR)
│   ├── vendors/                # Vendor workspaces
│   ├── Dockerfile              # Backend container
│   └── requirements.txt        # Python dependencies
│
├── queue_service/              # Node.js queue service
│   ├── queues/                 # BullMQ definitions
│   ├── services/               # Queue logic
│   ├── workers/                # Background workers
│   ├── Dockerfile              # Queue container
│   ├── Dockerfile.worker       # Worker container
│   └── package.json            # Node dependencies
│
├── docker-compose.yml          # Multi-container orchestration
├── .env.example                # Environment template
├── DOCKER_DEPLOYMENT_GUIDE.md  # Docker deployment docs
├── PRODUCTION_SETUP_GUIDE.md   # Production setup docs
└── README.md                   # This file
```

---

## 🚢 Deployment for Monika (DevOps Team)

All containerization is complete and ready for deployment:

✅ **Dockerfile** for Backend (Python)  
✅ **Dockerfile** for Queue Service (Node.js)  
✅ **Dockerfile.worker** for Async Workers  
✅ **docker-compose.yml** for full stack  
✅ **DOCKER_DEPLOYMENT_GUIDE.md** - Complete deployment instructions  
✅ **DEPLOYMENT_HANDOVER.md** - Handover document for DevOps

### Quick Deployment Steps:
1. Fork/clone repository: https://github.com/ankitkr9911/vendor-processing
2. Configure `.env` with production credentials
3. Run: `docker-compose up -d`
4. Verify: `docker-compose ps` and health checks

📧 **Deployment Document:** [DEPLOYMENT_HANDOVER.md](DEPLOYMENT_HANDOVER.md)

---

## 📚 Documentation

- [DOCKER_DEPLOYMENT_GUIDE.md](DOCKER_DEPLOYMENT_GUIDE.md) - Complete Docker deployment guide
- [PRODUCTION_SETUP_GUIDE.md](PRODUCTION_SETUP_GUIDE.md) - API documentation and production setup
- [DEPLOYMENT_HANDOVER.md](DEPLOYMENT_HANDOVER.md) - DevOps deployment handover document
- [.env.example](.env.example) - Environment variable template

---

## 🤝 Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📞 Support

**Developer:** Ankit Kumar  
**Organization:** EvolveonAI  
**Email:** ankitkr1801@gmail.com  
**GitHub:** https://github.com/ankitkr9911  
**Repository:** https://github.com/ankitkr9911/vendor-processing

For issues and feature requests, please use [GitHub Issues](https://github.com/ankitkr9911/vendor-processing/issues).

---

## 📄 License

MIT License - See [LICENSE](LICENSE) file for details

---

## 🎯 System Highlights

- ✅ **Production-Ready**: Docker containers with health checks and monitoring
- ✅ **Scalable**: Horizontal scaling for async workers (50+ concurrent jobs)
- ✅ **Monitored**: Bull Board dashboard for real-time queue monitoring
- ✅ **Secure**: JWT authentication, webhook signature verification
- ✅ **Reliable**: Redis persistence, MongoDB Atlas replication
- ✅ **Fast**: Parallel document processing with OpenAI Vision API
- ✅ **Flexible**: Dual registration methods (Chatbot + Email webhooks)
- ✅ **Intelligent**: AI-powered document extraction and validation

---
