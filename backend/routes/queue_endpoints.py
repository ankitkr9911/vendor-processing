"""
Queue Processing Endpoints
Main FastAPI endpoints to trigger and monitor Stage 3 & 4
Communicates with Node.js BullMQ service
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import requests
import os

router = APIRouter(prefix="/api/queue", tags=["Queue Processing"])

# Node.js Queue Service URL
QUEUE_SERVICE_URL = os.getenv("QUEUE_SERVICE_URL", "http://localhost:3000")


class Stage3TriggerResponse(BaseModel):
    success: bool
    stage: int
    message: str
    total_vendors: int
    total_documents: int
    batches_created: int
    batches_by_type: Dict[str, int]
    jobs_queued: int


class QueueStatsResponse(BaseModel):
    queue: str
    counts: Dict[str, int]
    workers: int
    timestamp: str


@router.post("/trigger-stage3", response_model=Stage3TriggerResponse)
async def trigger_stage3_batching():
    """
    Trigger Stage 3: Create batches from vendors ready for extraction
    
    This endpoint:
    1. Finds all vendors with status "ready_for_extraction"
    2. Groups their documents by type (aadhar, pan, gst)
    3. Creates batches of 10 documents each
    4. Adds batches to BullMQ queue for Stage 4 processing
    
    Returns:
        Processing summary with batch counts
    """
    try:
        response = requests.post(
            f"{QUEUE_SERVICE_URL}/api/stage3/create-batches",
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            return Stage3TriggerResponse(**data)
        else:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Queue service error: {response.text}"
            )
            
    except requests.exceptions.ConnectionError:
        raise HTTPException(
            status_code=503,
            detail=f"Cannot connect to queue service at {QUEUE_SERVICE_URL}. Is the Node.js service running?"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats", response_model=QueueStatsResponse)
async def get_queue_statistics():
    """
    Get real-time queue statistics
    
    Returns:
        Queue status including job counts and worker information
    """
    try:
        response = requests.get(
            f"{QUEUE_SERVICE_URL}/api/queue/stats",
            timeout=10
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Queue service error: {response.text}"
            )
            
    except requests.exceptions.ConnectionError:
        raise HTTPException(
            status_code=503,
            detail=f"Cannot connect to queue service at {QUEUE_SERVICE_URL}"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/batches")
async def get_batches(
    status: Optional[str] = None,
    document_type: Optional[str] = None,
    limit: int = 50,
    skip: int = 0
):
    """
    Get list of batches with optional filters
    
    Args:
        status: Filter by status (pending, processing, completed, failed)
        document_type: Filter by document type (aadhar, pan, gst)
        limit: Number of results per page
        skip: Number of results to skip (for pagination)
        
    Returns:
        List of batches with pagination info
    """
    try:
        params = {
            "limit": limit,
            "skip": skip
        }
        
        if status:
            params["status"] = status
        if document_type:
            params["document_type"] = document_type
        
        response = requests.get(
            f"{QUEUE_SERVICE_URL}/api/batches",
            params=params,
            timeout=10
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Queue service error: {response.text}"
            )
            
    except requests.exceptions.ConnectionError:
        raise HTTPException(
            status_code=503,
            detail=f"Cannot connect to queue service at {QUEUE_SERVICE_URL}"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/batches/{batch_id}")
async def get_batch_details(batch_id: str):
    """
    Get detailed information about a specific batch
    
    Args:
        batch_id: Batch identifier
        
    Returns:
        Batch details including progress and results
    """
    try:
        response = requests.get(
            f"{QUEUE_SERVICE_URL}/api/batches/{batch_id}",
            timeout=10
        )
        
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            raise HTTPException(status_code=404, detail="Batch not found")
        else:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Queue service error: {response.text}"
            )
            
    except requests.exceptions.ConnectionError:
        raise HTTPException(
            status_code=503,
            detail=f"Cannot connect to queue service at {QUEUE_SERVICE_URL}"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batches/{batch_id}/retry")
async def retry_failed_batch(batch_id: str):
    """
    Retry a failed batch
    
    Args:
        batch_id: Batch identifier
        
    Returns:
        Retry confirmation
    """
    try:
        response = requests.post(
            f"{QUEUE_SERVICE_URL}/api/batches/{batch_id}/retry",
            timeout=10
        )
        
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            raise HTTPException(status_code=404, detail="Batch not found")
        else:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Queue service error: {response.text}"
            )
            
    except requests.exceptions.ConnectionError:
        raise HTTPException(
            status_code=503,
            detail=f"Cannot connect to queue service at {QUEUE_SERVICE_URL}"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/processing-stats")
async def get_processing_statistics():
    """
    Get overall processing statistics
    
    Returns:
        Statistics about batches and vendors
    """
    try:
        response = requests.get(
            f"{QUEUE_SERVICE_URL}/api/stats",
            timeout=10
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Queue service error: {response.text}"
            )
            
    except requests.exceptions.ConnectionError:
        raise HTTPException(
            status_code=503,
            detail=f"Cannot connect to queue service at {QUEUE_SERVICE_URL}"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def queue_health_check():
    """Check if queue service is reachable"""
    try:
        response = requests.get(
            f"{QUEUE_SERVICE_URL}/health",
            timeout=5
        )
        
        if response.status_code == 200:
            return {
                "status": "healthy",
                "queue_service": "reachable",
                "queue_service_url": QUEUE_SERVICE_URL,
                **response.json()
            }
        else:
            return {
                "status": "degraded",
                "queue_service": "error",
                "detail": response.text
            }
            
    except requests.exceptions.ConnectionError:
        return {
            "status": "unhealthy",
            "queue_service": "unreachable",
            "queue_service_url": QUEUE_SERVICE_URL
        }
    except Exception as e:
        return {
            "status": "error",
            "detail": str(e)
        }
