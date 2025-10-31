"""
OCR Processing Endpoints
Exposes OCR service functionality via REST API
Used by Node.js BullMQ workers for Stage 4 processing
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any
import os

from services.ocr_service import OCRService

router = APIRouter(prefix="/api/ocr", tags=["OCR"])

# Initialize OCR service
ocr_service = OCRService()


class DocumentProcessRequest(BaseModel):
    document_path: str


class DocumentProcessResponse(BaseModel):
    success: bool
    extracted_data: Dict[str, Any]
    confidence: float
    error: str | None = None


@router.post("/process-aadhar", response_model=DocumentProcessResponse)
async def process_aadhar_document(request: DocumentProcessRequest):
    """
    Process Aadhaar card document and extract information
    Called by Node.js BullMQ workers
    """
    try:
        document_path = request.document_path
        
        # Validate file exists
        if not os.path.exists(document_path):
            raise HTTPException(status_code=404, detail=f"Document not found: {document_path}")
        
        # Process the document
        extracted_data, confidence = await ocr_service.process_aadhaar_card(document_path)
        
        return DocumentProcessResponse(
            success=True,
            extracted_data=extracted_data,
            confidence=confidence,
            error=None
        )
        
    except Exception as e:
        print(f"Error processing Aadhar document: {str(e)}")
        return DocumentProcessResponse(
            success=False,
            extracted_data={},
            confidence=0.0,
            error=str(e)
        )


@router.post("/process-pan", response_model=DocumentProcessResponse)
async def process_pan_document(request: DocumentProcessRequest):
    """
    Process PAN card document and extract information
    Called by Node.js BullMQ workers
    """
    try:
        document_path = request.document_path
        
        # Validate file exists
        if not os.path.exists(document_path):
            raise HTTPException(status_code=404, detail=f"Document not found: {document_path}")
        
        # Process the document
        extracted_data, confidence = await ocr_service.process_pan_card(document_path)
        
        return DocumentProcessResponse(
            success=True,
            extracted_data=extracted_data,
            confidence=confidence,
            error=None
        )
        
    except Exception as e:
        print(f"Error processing PAN document: {str(e)}")
        return DocumentProcessResponse(
            success=False,
            extracted_data={},
            confidence=0.0,
            error=str(e)
        )


@router.post("/process-gst", response_model=DocumentProcessResponse)
async def process_gst_document(request: DocumentProcessRequest):
    """
    Process GST certificate document and extract information
    Called by Node.js BullMQ workers
    """
    try:
        document_path = request.document_path
        
        # Validate file exists
        if not os.path.exists(document_path):
            raise HTTPException(status_code=404, detail=f"Document not found: {document_path}")
        
        # Process the document
        extracted_data, confidence = await ocr_service.process_gst_certificate(document_path)
        
        return DocumentProcessResponse(
            success=True,
            extracted_data=extracted_data,
            confidence=confidence,
            error=None
        )
        
    except Exception as e:
        print(f"Error processing GST document: {str(e)}")
        return DocumentProcessResponse(
            success=False,
            extracted_data={},
            confidence=0.0,
            error=str(e)
        )


@router.get("/health")
async def ocr_health_check():
    """Health check endpoint for OCR service"""
    return {
        "status": "healthy",
        "service": "ocr_processing",
        "openai_configured": bool(os.getenv("OPENAI_API_KEY"))
    }
