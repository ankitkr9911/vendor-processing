from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from typing import Dict, Any
import os
import uuid
import asyncio
from datetime import datetime

from models import (
    DocumentModel, DocumentType, ParseStatus, 
    VendorDraftModel, ChatStage, AadhaarData, PANData, GSTData,
    DocumentUploadResponse, ExtractedDataResponse, APIResponse
)
from database import db
from services.ocr_service import OCRService
from utils.validators import verify_vendor_info_with_documents

router = APIRouter(prefix="/api/v1/documents", tags=["Document Processing"])
ocr_service = OCRService()

# Create uploads directory
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

async def process_document_background(document_id: str, file_path: str, document_type: DocumentType, session_id: str):
    """Background task to process uploaded document"""
    try:
        # Update status to processing
        db.update_document(document_id, {
            "parse_status": ParseStatus.PROCESSING
        })
        
        # Process based on document type
        if document_type == DocumentType.AADHAAR:
            parsed_data, confidence = await ocr_service.process_aadhaar_card(file_path)
        elif document_type == DocumentType.PAN:
            parsed_data, confidence = await ocr_service.process_pan_card(file_path)
        elif document_type == DocumentType.GST:
            parsed_data, confidence = await ocr_service.process_gst_certificate(file_path)
        else:
            raise ValueError(f"Unsupported document type: {document_type}")
        
        # Update document with parsed data
        db.update_document(document_id, {
            "parse_status": ParseStatus.COMPLETED,
            "parsed_data": parsed_data,
            "parse_confidence": confidence
        })
        
        # Update vendor draft with extracted data
        vendor_draft = db.get_vendor_draft_by_session(session_id)
        if vendor_draft:
            updates = {}
            
            if document_type == DocumentType.AADHAAR:
                aadhaar_data = AadhaarData(**parsed_data, confidence=confidence)
                updates["aadhaar_data"] = aadhaar_data.dict()
                updates["chat_stage"] = ChatStage.PAN_REQUEST
            elif document_type == DocumentType.PAN:
                pan_data = PANData(**parsed_data, confidence=confidence)
                updates["pan_data"] = pan_data.dict()
                updates["chat_stage"] = ChatStage.GST_REQUEST
            elif document_type == DocumentType.GST:
                gst_data = GSTData(**parsed_data, confidence=confidence)
                updates["gst_data"] = gst_data.dict()
                updates["chat_stage"] = ChatStage.COMPLETED
                updates["is_completed"] = True
                
                # Automatically verify vendor info after all documents are processed
                try:
                    vendor_drafts_file = os.path.join("data", "vendor_drafts.json")
                    is_verified = verify_vendor_info_with_documents(vendor_drafts_file, vendor_draft.id)
                    print(f"Vendor verification completed for {vendor_draft.id}: {is_verified}")
                except Exception as e:
                    print(f"Error during automatic verification for {vendor_draft.id}: {e}")
                    # Continue with registration completion even if verification fails
            
            # Add document ID to the documents list
            current_docs = vendor_draft.documents or []
            if document_id not in current_docs:
                current_docs.append(document_id)
                updates["documents"] = current_docs
            
            db.update_vendor_draft(vendor_draft.id, updates)
        
        print(f"Successfully processed document {document_id}")
        
    except Exception as e:
        print(f"Error processing document {document_id}: {e}")
        # Update status to failed
        db.update_document(document_id, {
            "parse_status": ParseStatus.FAILED,
            "error_message": str(e)
        })

@router.post("/upload/{session_id}")
async def upload_document(
    session_id: str, 
    background_tasks: BackgroundTasks,
    document_type: str,
    file: UploadFile = File(...)
):
    """
    Upload and Process Document
    
    Upload a document (Aadhaar, PAN, or GST) for processing. The document will be
    processed using AI-powered OCR to extract relevant information.
    
    Args:
        session_id: Session identifier from chat flow
        document_type: Type of document ('aadhaar', 'pan', or 'gst')
        file: Document image file (JPG, PNG, PDF)
        
    Returns:
        Document upload confirmation with processing status
    """
    
    # Add debug logging
    print(f"DEBUG: Upload request - session_id: {session_id}, document_type: {document_type}")
    
    # Validate document type
    try:
        doc_type = DocumentType(document_type.lower())
        print(f"DEBUG: Valid document type: {doc_type}")
    except ValueError:
        print(f"DEBUG: Invalid document type: {document_type}. Valid types: aadhaar, pan, gst")
        raise HTTPException(status_code=400, detail=f"Invalid document type '{document_type}'. Valid types: aadhaar, pan, gst")
    
    # Validate file type
    allowed_extensions = {'.jpg', '.jpeg', '.png', '.pdf'}
    file_extension = os.path.splitext(file.filename)[1].lower()
    if file_extension not in allowed_extensions:
        raise HTTPException(status_code=400, detail="File type not supported. Please upload JPG, PNG, or PDF files.")
    
    # Check if vendor draft exists
    vendor_draft = db.get_vendor_draft_by_session(session_id)
    if not vendor_draft:
        print(f"DEBUG: Session not found: {session_id}")
        raise HTTPException(status_code=404, detail="Chat session not found")
    
    print(f"DEBUG: Found session. Current stage: {vendor_draft.chat_stage}")
    
    # Check if document type is expected based on current stage
    current_stage = vendor_draft.chat_stage
    
    # More flexible stage validation - allow document upload in appropriate stages
    if doc_type == DocumentType.AADHAAR:
        if current_stage not in [ChatStage.AADHAAR_REQUEST, ChatStage.AADHAAR_PROCESSING]:
            # Allow Aadhaar upload if basic details are complete or we're already in later stages
            if current_stage == ChatStage.COLLECTING_BASIC_DETAILS:
                raise HTTPException(status_code=400, detail="Please complete basic information first before uploading documents")
    elif doc_type == DocumentType.PAN:
        if current_stage not in [ChatStage.PAN_REQUEST, ChatStage.PAN_PROCESSING]:
            if current_stage in [ChatStage.WELCOME, ChatStage.COLLECTING_BASIC_DETAILS, ChatStage.AADHAAR_REQUEST]:
                raise HTTPException(status_code=400, detail="Please upload Aadhaar card first")
    elif doc_type == DocumentType.GST:
        if current_stage not in [ChatStage.GST_REQUEST, ChatStage.GST_PROCESSING]:
            if current_stage in [ChatStage.WELCOME, ChatStage.COLLECTING_BASIC_DETAILS, ChatStage.AADHAAR_REQUEST, ChatStage.PAN_REQUEST]:
                raise HTTPException(status_code=400, detail="Please upload Aadhaar and PAN cards first")
    
    try:
        # Generate unique filename
        file_id = str(uuid.uuid4())
        filename = f"{file_id}_{file.filename}"
        file_path = os.path.join(UPLOAD_DIR, filename)
        
        # Save uploaded file
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        # Create document record
        document = DocumentModel(
            session_id=session_id,
            document_type=doc_type,
            filename=file.filename,
            s3_key=file_path,  # Using local path for now
            parse_status=ParseStatus.PENDING
        )
        
        document_id = db.create_document(document)
        
        # Update vendor draft stage to processing
        if doc_type == DocumentType.AADHAAR:
            db.update_vendor_draft(vendor_draft.id, {"chat_stage": ChatStage.AADHAAR_PROCESSING})
        elif doc_type == DocumentType.PAN:
            db.update_vendor_draft(vendor_draft.id, {"chat_stage": ChatStage.PAN_PROCESSING})
        elif doc_type == DocumentType.GST:
            db.update_vendor_draft(vendor_draft.id, {"chat_stage": ChatStage.GST_PROCESSING})
        
        # Start background processing
        background_tasks.add_task(
            process_document_background, 
            document_id, 
            file_path, 
            doc_type, 
            session_id
        )
        
        return {
            "message": "Document uploaded successfully",
            "document_id": document_id,
            "status": "processing",
            "filename": file.filename
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload document: {str(e)}")

@router.get("/status/{document_id}")
async def get_document_status(document_id: str):
    """Get document processing status"""
    document = db.get_document(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return {
        "document_id": document_id,
        "filename": document.filename,
        "document_type": document.document_type,
        "status": document.parse_status,
        "confidence": document.parse_confidence,
        "parsed_data": document.parsed_data,
        "error_message": document.error_message,
        "created_at": document.created_at,
        "updated_at": document.updated_at
    }

@router.get("/session/{session_id}")
async def get_session_documents(session_id: str):
    """Get all documents for a session"""
    documents = db.get_documents_by_session(session_id)
    
    return {
        "session_id": session_id,
        "documents": [
            {
                "document_id": doc.id,
                "filename": doc.filename,
                "document_type": doc.document_type,
                "status": doc.parse_status,
                "confidence": doc.parse_confidence,
                "created_at": doc.created_at
            }
            for doc in documents
        ]
    }

@router.get("/parsed-data/{session_id}")
async def get_parsed_data(session_id: str):
    """Get all parsed data for a session"""
    vendor_data = db.get_extracted_vendor_data(session_id)
    
    if not vendor_data:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return {
        "session_id": session_id,
        "vendor_data": vendor_data,
        "summary": {
            "aadhaar_processed": vendor_data.get("aadhaar_data") is not None,
            "pan_processed": vendor_data.get("pan_data") is not None,
            "gst_processed": vendor_data.get("gst_data") is not None,
            "is_completed": vendor_data.get("is_completed", False)
        }
    }