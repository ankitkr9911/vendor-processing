"""
Vendor Email Processing Route
Handles automated vendor registration via Nylas email integration
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime
from services.vendor_email_service import VendorEmailService

router = APIRouter(prefix="/api/v1/vendors", tags=["Vendor Processing"])

# Initialize service
vendor_service = VendorEmailService()


class ProcessEmailsRequest(BaseModel):
    """Request model for processing vendor emails"""
    limit: Optional[int] = 1000
    background: Optional[bool] = True


class ProcessEmailsResponse(BaseModel):
    """Response model for email processing"""
    success: bool
    message: str
    job_id: Optional[str] = None
    summary: Optional[Dict[str, Any]] = None
    timestamp: datetime


@router.post("/process-emails", response_model=ProcessEmailsResponse)
async def process_vendor_emails(
    request: ProcessEmailsRequest,
    background_tasks: BackgroundTasks
):
    """
    Process vendor registration emails from Nylas
    
    **STAGE 1 & 2 Implementation:**
    - Fetches emails from Nylas with subject "VENDOR REGISTRATION"
    - Validates email structure and attachments
    - Extracts basic information from email body
    - Downloads attachments and stores in vendor-isolated folders
    - Saves data to MongoDB
    
    **Query Parameters:**
    - limit: Maximum number of emails to fetch (default: 1000)
    - background: Process in background (default: true)
    
    **Returns:**
    - job_id: Background job ID for tracking
    - summary: Processing summary (if synchronous)
    """
    try:
        if request.background:
            # Process in background
            job_id = vendor_service.start_background_processing(
                limit=request.limit
            )
            
            return ProcessEmailsResponse(
                success=True,
                message=f"Email processing started in background. Job ID: {job_id}",
                job_id=job_id,
                timestamp=datetime.now()
            )
        else:
            # Process synchronously
            result = await vendor_service.process_emails(limit=request.limit)
            
            return ProcessEmailsResponse(
                success=True,
                message="Email processing completed successfully",
                summary=result,
                timestamp=datetime.now()
            )
            
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing vendor emails: {str(e)}"
        )


@router.get("/processing-status/{job_id}")
async def get_processing_status(job_id: str):
    """
    Get status of background email processing job
    
    **Parameters:**
    - job_id: Background job identifier
    
    **Returns:**
    - status: Job status (processing, completed, failed)
    - progress: Processing progress details
    - results: Final results if completed
    """
    try:
        status = vendor_service.get_job_status(job_id)
        
        if not status:
            raise HTTPException(
                status_code=404,
                detail=f"Job {job_id} not found"
            )
        
        return {
            "success": True,
            "job_id": job_id,
            "status": status["status"],
            "progress": status.get("progress", {}),
            "results": status.get("results"),
            "timestamp": datetime.now()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching job status: {str(e)}"
        )


@router.get("/vendor/{vendor_id}")
async def get_vendor_details(vendor_id: str):
    """
    Get vendor details by vendor_id
    
    **Parameters:**
    - vendor_id: Unique vendor identifier
    
    **Returns:**
    - Vendor complete information including:
      - Basic info from email
      - Document paths
      - Processing status
      - Metadata
    """
    try:
        vendor = vendor_service.get_vendor_by_id(vendor_id)
        
        if not vendor:
            raise HTTPException(
                status_code=404,
                detail=f"Vendor {vendor_id} not found"
            )
        
        return {
            "success": True,
            "vendor": vendor,
            "timestamp": datetime.now()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching vendor details: {str(e)}"
        )


@router.get("/vendors/list")
async def list_vendors(
    status: Optional[str] = None,
    limit: int = 100,
    skip: int = 0
):
    """
    List all processed vendors with optional filtering
    
    **Query Parameters:**
    - status: Filter by status (pending_extraction, downloading_documents, ready_for_extraction, etc.)
    - limit: Number of results (default: 100)
    - skip: Number of results to skip (pagination)
    
    **Returns:**
    - List of vendors with basic information
    """
    try:
        vendors = vendor_service.list_vendors(
            status=status,
            limit=limit,
            skip=skip
        )
        
        return {
            "success": True,
            "vendors": vendors,
            "count": len(vendors),
            "timestamp": datetime.now()
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error listing vendors: {str(e)}"
        )


@router.get("/statistics")
async def get_processing_statistics():
    """
    Get overall vendor processing statistics
    
    **Returns:**
    - Total emails processed
    - Valid/Invalid/Rejected counts
    - Status distribution
    - Recent activity
    """
    try:
        stats = vendor_service.get_statistics()
        
        return {
            "success": True,
            "statistics": stats,
            "timestamp": datetime.now()
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching statistics: {str(e)}"
        )
