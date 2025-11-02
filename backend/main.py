from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import routes
from routes.chat import router as chat_router
from routes.chat_enhanced import router as chat_enhanced_router  # NEW: Enhanced chat with confirmation
from routes.documents import router as documents_router
from routes.vendor_processing import router as vendor_processing_router
from routes.webhook_endpoints import router as webhook_router
from routes.ocr_endpoints import router as ocr_router
from routes.ocr_async_endpoints import router as ocr_async_router
from routes.queue_endpoints import router as queue_router
from routes.chatbot_endpoints import router as chatbot_router

# Create FastAPI app
app = FastAPI(
    title="Vendor Portal API",
    description="""
    AI-powered vendor registration system with document processing capabilities.
    
    ## Features
    - **Chat-based Registration**: Step-by-step vendor information collection
    - **Document Processing**: AI-powered OCR for Aadhaar, PAN, and GST documents
    - **Text-to-Speech**: Voice interaction capabilities
    - **Real-time Updates**: Session-based progress tracking
    
    ## Authentication
    No authentication required for demo purposes.
    
    ## Rate Limiting
    No rate limiting currently implemented.
    """,
    version="2.0.0",
    contact={
        "name": "Vendor Portal API Team",
        "email": "support@vendorportal.com",
    },
    license_info={
        "name": "MIT",
    },
)

# Add CORS middleware - Allow all origins for API consumption
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow any frontend to consume this API
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Mount static files
if os.path.exists("uploads"):
    app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# Include routers
# app.include_router(chat_router)  # OLD: Disabled in favor of chat_enhanced
app.include_router(chat_enhanced_router)  # NEW: Enhanced chat with confirmation and normalization
app.include_router(documents_router)
app.include_router(vendor_processing_router)
app.include_router(webhook_router)
app.include_router(ocr_router)
app.include_router(ocr_async_router)
app.include_router(queue_router)
app.include_router(chatbot_router)

@app.get("/", tags=["Root"])
async def root():
    """
    API Information Endpoint
    
    Provides basic information about the Vendor Portal API including available endpoints,
    version information, and integration guidance.
    """
    return {
        "message": "Vendor Portal API - Ready for Integration",
        "version": "2.0.0",
        "status": "operational",
        "api_documentation": "/docs",
        "redoc_documentation": "/redoc",
        "endpoints": {
            "chat_management": {
                "base_path": "/api/v1/chat",
                "description": "Handle vendor registration chat flow",
                "endpoints": [
                    "POST /start - Start new registration session",
                    "POST /message/{session_id} - Send message in chat",
                    "GET /history/{session_id} - Get chat history",
                    "GET /status/{session_id} - Get session status",
                    "POST /tts - Text-to-speech conversion"
                ]
            },
            "document_processing": {
                "base_path": "/api/v1/documents", 
                "description": "Handle document upload and processing",
                "endpoints": [
                    "POST /upload/{session_id} - Upload document for processing",
                    "GET /session/{session_id} - Get session documents",
                    "GET /parsed/{session_id} - Get extracted data"
                ]
            },
            "vendor_processing": {
                "base_path": "/api/v1/vendors",
                "description": "Vendor email processing (Legacy polling method)",
                "endpoints": [
                    "POST /process-emails - Process vendor emails (polling)",
                    "GET /vendor/{vendor_id} - Get vendor details",
                    "GET /vendors/list - List all vendors",
                    "GET /statistics - Get processing statistics"
                ]
            },
            "webhooks": {
                "base_path": "/webhooks/nylas",
                "description": "Real-time email processing via webhooks (RECOMMENDED)",
                "endpoints": [
                    "POST /message-created - Nylas webhook endpoint (called automatically)",
                    "GET /statistics - Webhook processing statistics",
                    "POST /test - Test webhook endpoint",
                    "GET /health - Webhook health check"
                ]
            }
        },
        "integration_notes": {
            "cors": "Enabled for all origins",
            "authentication": "Not required (demo mode)",
            "content_type": "application/json",
            "file_uploads": "multipart/form-data for document uploads"
        }
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    required_env_vars = ["OPENAI_API_KEY"]
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    
    if missing_vars:
        raise HTTPException(
            status_code=500, 
            detail=f"Missing environment variables: {', '.join(missing_vars)}"
        )
    
    return {
        "status": "healthy",
        "environment": {
            "openai_configured": bool(os.getenv("OPENAI_API_KEY")),
            "uploads_dir": os.path.exists("uploads"),
            "data_dir": os.path.exists("data")
        }
    }

if __name__ == "__main__":
    import uvicorn
    # Run with multiple workers for better concurrency
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        workers=1  # Keep 1 for development (reload doesn't work with >1)
        # For production: workers=4
    )