"""
Async OCR Processing Endpoints with Callback Pattern
Accepts requests immediately (202), processes in background, calls back when done
"""
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
import httpx
import os
from typing import Optional, Dict, Any

from services.ocr_service import OCRService
from services.ai_catalogue_service import AICatalogueService

router = APIRouter(prefix="/api/ocr/async", tags=["OCR Async"])

# Initialize services
ocr_service = OCRService()
ai_catalogue_service = AICatalogueService()


class AsyncDocumentRequest(BaseModel):
    document_path: str
    task_id: str
    callback_url: str


class AsyncCatalogueRequest(BaseModel):
    document_path: str  # CSV file path
    task_id: str
    callback_url: str
    vendor_id: str
    vendor_info: Optional[Dict[str, Any]] = None  # Company name, etc.


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


@router.post("/process-catalogue", response_model=TaskAcceptedResponse, status_code=202)
async def process_catalogue_async(request: AsyncCatalogueRequest, background_tasks: BackgroundTasks):
    """
    Accept Catalogue CSV processing request, return immediately, process with AI in background
    """
    try:
        # Add background task
        background_tasks.add_task(
            process_catalogue_async_task,
            request.document_path,
            request.task_id,
            request.callback_url,
            request.vendor_id,
            request.vendor_info or {}
        )
        
        return TaskAcceptedResponse(
            task_id=request.task_id,
            status="accepted",
            message="Catalogue processing task accepted and queued (AI processing)"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to accept task: {str(e)}")


async def process_catalogue_async_task(
    csv_path: str,
    task_id: str,
    callback_url: str,
    vendor_id: str,
    vendor_info: Dict[str, Any]
):
    """
    Background task that processes catalogue CSV with AI and sends callback
    """
    try:
        print(f"🔄 Background catalogue processing started: {task_id} | Vendor: {vendor_id}")
        
        # Validate file exists
        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"CSV file not found: {csv_path}")
        
        # Process catalogue with AI
        processed_data, confidence = await ai_catalogue_service.process_catalogue_with_ai(
            csv_path,
            vendor_id,
            vendor_info
        )
        
        # Send success callback with processed data
        callback_payload = {
            "task_id": task_id,
            "status": "success",
            "extracted_data": processed_data,
            "confidence": confidence,
            "error": None
        }
        
        await send_callback(callback_url, callback_payload)
        print(f"✅ Catalogue task completed successfully: {task_id}")
        
    except Exception as e:
        error_message = str(e)
        print(f"❌ Catalogue task failed: {task_id} | Error: {error_message}")
        
        # Send error callback
        callback_payload = {
            "task_id": task_id,
            "status": "error",
            "extracted_data": None,
            "confidence": 0.0,
            "error": error_message
        }
        
        await send_callback(callback_url, callback_payload)


@router.get("/health")
async def async_ocr_health():
    """Health check for async OCR endpoints"""
    return {
        "status": "healthy",
        "service": "async_ocr_processing",
        "callback_enabled": True,
        "catalogue_ai_enabled": True  # ✅ Catalogue AI processing enabled
    }
