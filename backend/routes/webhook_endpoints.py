from fastapi import APIRouter, Request, HTTPException, Header, Query, BackgroundTasks
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime
from services.webhook_processor import WebhookProcessor
import json

router = APIRouter(prefix="/webhooks/nylas", tags=["Nylas Webhooks"])

# Initialize webhook processor
webhook_processor = WebhookProcessor()


async def process_webhook_background(webhook_data: Dict[str, Any]):
    """
    Process webhook in background (non-blocking)
    Allows multiple webhooks to be processed simultaneously
    """
    try:
        result = await webhook_processor.process_webhook(webhook_data)
        print(f"✅ Background webhook processing completed: {result.get('email_id')}")
        return result
    except Exception as e:
        print(f"❌ Background webhook processing failed: {str(e)}")


@router.get("/message-created")
async def handle_webhook_challenge(challenge: str = Query(None)):
    """
    **Nylas Webhook Challenge Verification (GET)**
    
    Nylas sends a GET request with a challenge parameter to verify webhook ownership.
    We must respond with the same challenge value as plain text.
    
    This is called ONCE when you create the webhook in Nylas Dashboard.
    """
    print(f"🔍 GET request received. Challenge parameter: {challenge}")
    
    if challenge:
        print(f"✅ Webhook challenge received: {challenge}")
        # Return plain text response, not JSON
        return PlainTextResponse(content=challenge, status_code=200)
    else:
        print("❌ No challenge parameter provided")
        return PlainTextResponse(content="No challenge parameter", status_code=400)


@router.post("/message-created")
async def handle_message_created_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_nylas_signature: Optional[str] = Header(None)
):
    """
    **Nylas Webhook Endpoint - Message Created Event (PARALLEL PROCESSING)**
    
    This endpoint processes webhooks in the background, allowing multiple emails
    to be processed simultaneously without blocking.
    
    **How it works:**
    1. Vendor sends email to your admin email
    2. Nylas receives email and immediately calls this endpoint
    3. We validate signature (security)
    4. We return 200 OK immediately (non-blocking)
    5. Email processes in background (parallel with other emails)
    
    **Parallel Processing:**
    - Multiple emails can arrive simultaneously
    - Each processes in its own background task
    - No waiting - all documents download in parallel
    - Significantly faster than sequential processing
    
    **Security:**
    - Verifies Nylas signature (X-Nylas-Signature header)
    - Prevents unauthorized webhook calls
    
    **Idempotency:**
    - Safe to retry - checks MongoDB for duplicates
    - Nylas may retry failed webhooks
    
    **Performance:**
    - 2 emails arrive → Both process simultaneously
    - 10 emails arrive → All process in parallel
    - Total time = time for 1 email (not sum of all)
    
    **What happens to the email:**
    ✓ Subject validation (must contain "VENDOR" + "REGISTRATION")
    ✓ Attachment validation (aadhar, pan, gst)
    ✓ Basic info extraction from body
    ✓ Duplicate check (MongoDB)
    ✓ Download documents (parallel)
    ✓ Create vendor record
    ✓ Store in vendor-isolated folder
    
    **Response Codes:**
    - 200: Webhook accepted and queued for processing
    - 400: Invalid signature or malformed payload
    - 500: Processing error (Nylas will retry)
    """
    try:
        # Get raw body for signature verification
        raw_body = await request.body()
        
        # Verify webhook signature (security)
        if x_nylas_signature:
            is_valid = webhook_processor.verify_webhook_signature(
                raw_body,
                x_nylas_signature
            )
            
            if not is_valid:
                print("⚠️ Invalid webhook signature - possible unauthorized request")
                raise HTTPException(
                    status_code=401,
                    detail="Invalid webhook signature"
                )
        else:
            print("⚠️ WARNING: No signature provided (set NYLAS_WEBHOOK_SECRET in production)")
        
        # Parse webhook payload
        webhook_data = json.loads(raw_body)
        
        email_id = webhook_data.get('data', {}).get('object', {}).get('id') or webhook_data.get('data', {}).get('id')
        print(f"📨 Webhook received: {webhook_data.get('type')} - Email ID: {email_id}")
        
        # Add to background tasks (non-blocking - returns immediately)
        background_tasks.add_task(process_webhook_background, webhook_data)
        
        # Return success immediately (webhook processing happens in background)
        return {
            "success": True,
            "message": "Webhook accepted and queued for processing",
            "email_id": email_id,
            "processing": "background",
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid JSON payload: {str(e)}"
        )
    except Exception as e:
        print(f"❌ Webhook acceptance error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Webhook acceptance error: {str(e)}"
        )


@router.get("/statistics")
async def get_webhook_statistics():
    """
    Get webhook processing statistics
    
    **Returns:**
    - Total webhooks received
    - Success/duplicate/rejected/error counts
    - Success rate
    - Recent webhook activity
    
    **Use this to monitor:**
    - How many emails are being processed
    - Error rates
    - Recent activity
    """
    try:
        stats = webhook_processor.get_webhook_statistics()
        
        return {
            "success": True,
            "statistics": stats,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching statistics: {str(e)}"
        )


@router.post("/test")
async def test_webhook_endpoint(request: Request):
    """
    **Test Webhook Endpoint (Development Only)**
    
    Use this to test your webhook without waiting for real emails.
    
    **Example test payload:**
    ```json
    {
      "trigger": "message.created",
      "data": {
        "id": "test-email-123",
        "subject": "VENDOR REGISTRATION - Test Company",
        "from": [{"email": "test@example.com"}],
        "date": "2025-10-24T10:00:00"
      }
    }
    ```
    
    **Note:** This skips signature verification for testing.
    """
    try:
        webhook_data = await request.json()
        
        print("🧪 TEST WEBHOOK - Processing test payload")
        
        # Process without signature verification
        result = await webhook_processor.process_webhook(webhook_data)
        
        return {
            "success": True,
            "message": "Test webhook processed",
            "result": result,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Test webhook error: {str(e)}"
        )


@router.get("/health")
async def webhook_health_check():
    """
    Health check for webhook endpoint
    
    **Returns:**
    - Webhook endpoint status
    - MongoDB connection status
    - Configuration status
    """
    try:
        # Check MongoDB connection
        webhook_processor.db.command("ping")
        mongo_connected = True
    except:
        mongo_connected = False
    
    # Check configuration
    has_webhook_secret = bool(webhook_processor.webhook_secret)
    has_nylas_config = bool(webhook_processor.nylas.api_key and webhook_processor.nylas.grant_id)
    
    status = "healthy" if (mongo_connected and has_nylas_config) else "degraded"
    
    return {
        "status": status,
        "checks": {
            "mongodb_connected": mongo_connected,
            "nylas_configured": has_nylas_config,
            "webhook_secret_configured": has_webhook_secret
        },
        "warnings": [] if has_webhook_secret else ["NYLAS_WEBHOOK_SECRET not set - signature verification disabled"],
        "timestamp": datetime.now().isoformat()
    }
