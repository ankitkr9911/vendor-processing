"""
Async OCR Processing Endpoints with Callback Pattern
Accepts requests immediately (202), processes in background, calls back when done
"""
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
import httpx
import os
from typing import Optional

from services.ocr_service import OCRService

router = APIRouter(prefix="/api/ocr/async", tags=["OCR Async"])

# Initialize OCR service
ocr_service = OCRService()


class AsyncDocumentRequest(BaseModel):
    document_path: str
    task_id: str
    callback_url: str


class TaskAcceptedResponse(BaseModel):
    task_id: str
    status: str  # "accepted"
    message: str


async def send_callback(callback_url: str, payload: dict, max_retries: int = 3):
    """
    Send callback to Node.js service with retry logic
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        for attempt in range(max_retries):
            try:
                response = await client.post(callback_url, json=payload)
                if response.status_code == 200:
                    print(f"✅ Callback sent successfully for task {payload.get('task_id')}")
                    return
                else:
                    print(f"⚠️ Callback failed (attempt {attempt + 1}): {response.status_code}")
            except Exception as e:
                print(f"❌ Callback error (attempt {attempt + 1}): {str(e)}")
                if attempt == max_retries - 1:
                    print(f"💥 Failed to send callback after {max_retries} attempts")


async def process_document_async(
    document_type: str,
    document_path: str,
    task_id: str,
    callback_url: str
):
    """
    Background task that processes document and sends callback
    """
    try:
        print(f"🔄 Background processing started: {task_id} | {document_type}")
        
        # Validate file exists
        if not os.path.exists(document_path):
            raise FileNotFoundError(f"Document not found: {document_path}")
        
        # Process based on document type
        if document_type == "aadhar":
            extracted_data, confidence = await ocr_service.process_aadhaar_card(document_path)
        elif document_type == "pan":
            extracted_data, confidence = await ocr_service.process_pan_card(document_path)
        elif document_type == "gst":
            extracted_data, confidence = await ocr_service.process_gst_certificate(document_path)
        else:
            raise ValueError(f"Unknown document type: {document_type}")
        
        # Send success callback
        callback_payload = {
            "task_id": task_id,
            "status": "success",
            "extracted_data": extracted_data,
            "confidence": confidence,
            "error": None
        }
        
        await send_callback(callback_url, callback_payload)
        print(f"✅ Task completed successfully: {task_id}")
        
    except Exception as e:
        error_message = str(e)
        print(f"❌ Task failed: {task_id} | Error: {error_message}")
        
        # Send error callback
        callback_payload = {
            "task_id": task_id,
            "status": "error",
            "extracted_data": None,
            "confidence": 0.0,
            "error": error_message
        }
        
        await send_callback(callback_url, callback_payload)


@router.post("/process-aadhar", response_model=TaskAcceptedResponse, status_code=202)
async def process_aadhar_async(request: AsyncDocumentRequest, background_tasks: BackgroundTasks):
    """
    Accept Aadhar processing request, return immediately, process in background
    """
    try:
        # Add background task
        background_tasks.add_task(
            process_document_async,
            "aadhar",
            request.document_path,
            request.task_id,
            request.callback_url
        )
        
        return TaskAcceptedResponse(
            task_id=request.task_id,
            status="accepted",
            message="Aadhar processing task accepted and queued"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to accept task: {str(e)}")


@router.post("/process-pan", response_model=TaskAcceptedResponse, status_code=202)
async def process_pan_async(request: AsyncDocumentRequest, background_tasks: BackgroundTasks):
    """
    Accept PAN processing request, return immediately, process in background
    """
    try:
        # Add background task
        background_tasks.add_task(
            process_document_async,
            "pan",
            request.document_path,
            request.task_id,
            request.callback_url
        )
        
        return TaskAcceptedResponse(
            task_id=request.task_id,
            status="accepted",
            message="PAN processing task accepted and queued"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to accept task: {str(e)}")


@router.post("/process-gst", response_model=TaskAcceptedResponse, status_code=202)
async def process_gst_async(request: AsyncDocumentRequest, background_tasks: BackgroundTasks):
    """
    Accept GST processing request, return immediately, process in background
    """
    try:
        # Add background task
        background_tasks.add_task(
            process_document_async,
            "gst",
            request.document_path,
            request.task_id,
            request.callback_url
        )
        
        return TaskAcceptedResponse(
            task_id=request.task_id,
            status="accepted",
            message="GST processing task accepted and queued"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to accept task: {str(e)}")


@router.get("/health")
async def async_ocr_health():
    """Health check for async OCR endpoints"""
    return {
        "status": "healthy",
        "service": "async_ocr_processing",
        "callback_enabled": True
    }
