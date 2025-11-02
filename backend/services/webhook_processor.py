"""
Nylas Webhook Processor Service
Real-time email processing triggered by Nylas webhooks
Production-ready implementation with signature verification
"""
import os
import hmac
import hashlib
import json
import re
from typing import Dict, Any, Optional
from datetime import datetime
from pymongo import MongoClient
from services.nylas_service import NylasService
from utils.catalogue_processor import catalogue_processor
import asyncio
import concurrent.futures
from html import unescape
from html.parser import HTMLParser


class WebhookProcessor:
    """Process vendor registration emails in real-time via webhooks"""
    
    def __init__(self):
        # Initialize Nylas service
        self.nylas = NylasService()
        
        # MongoDB connection
        mongo_uri = os.getenv("MONGO_URI")
        if not mongo_uri:
            raise ValueError("Missing MONGO_URI configuration")
        
        self.mongo_client = MongoClient(mongo_uri)
        self.db = self.mongo_client.get_database()
        
        # Collections
        self.processed_emails = self.db["processed_emails"]
        self.vendors = self.db["vendors"]
        self.rejected_emails = self.db["rejected_emails"]
        self.webhook_logs = self.db["webhook_logs"]  # Track all webhook calls
        
        # Nylas webhook secret for signature verification
        self.webhook_secret = os.getenv("NYLAS_WEBHOOK_SECRET", "")
        
        # Vendor storage base path
        self.vendors_base_path = "vendors"
        os.makedirs(self.vendors_base_path, exist_ok=True)
        
        # Import validation logic from vendor_email_service
        from services.vendor_email_service import VendorEmailService
        self.email_service = VendorEmailService()
    
    def html_to_plain_text(self, html_content: str) -> str:
        """
        Convert HTML email body to plain text
        Strips all HTML tags and normalizes whitespace
        """
        if not html_content:
            return ""
        
        # Decode HTML entities
        text = unescape(html_content)
        
        # Replace common HTML tags with newlines
        text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</p>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</div>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</tr>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</li>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</h[1-6]>', '\n', text, flags=re.IGNORECASE)
        
        # Remove all remaining HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        
        # Replace HTML entities
        text = text.replace('&nbsp;', ' ')
        text = text.replace('&amp;', '&')
        text = text.replace('&lt;', '<')
        text = text.replace('&gt;', '>')
        text = text.replace('&quot;', '"')
        
        # Normalize whitespace
        text = re.sub(r'[ \t]+', ' ', text)  # Multiple spaces to single space
        text = re.sub(r'\n\s*\n', '\n\n', text)  # Multiple newlines to double newline
        text = text.strip()
        
        return text
    
    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """
        Verify Nylas webhook signature for security
        Prevents unauthorized webhook calls
        
        Args:
            payload: Raw request body (bytes)
            signature: X-Nylas-Signature header value
            
        Returns:
            True if signature is valid, False otherwise
        """
        if not self.webhook_secret:
            # If no secret configured, skip verification (development only)
            print("WARNING: NYLAS_WEBHOOK_SECRET not set - skipping signature verification")
            return True
        
        try:
            # Calculate expected signature
            expected_signature = hmac.new(
                self.webhook_secret.encode('utf-8'),
                payload,
                hashlib.sha256
            ).hexdigest()
            
            # Compare signatures (timing-safe comparison)
            return hmac.compare_digest(expected_signature, signature)
            
        except Exception as e:
            print(f"Error verifying webhook signature: {str(e)}")
            return False
    
    def log_webhook_call(self, webhook_data: Dict[str, Any], status: str, error: Optional[str] = None):
        """
        Log all webhook calls for auditing and debugging
        
        Args:
            webhook_data: The webhook payload
            status: Processing status (success, duplicate, rejected, error)
            error: Error message if any
        """
        try:
            log_entry = {
                "webhook_id": webhook_data.get("id"),
                "trigger_type": webhook_data.get("trigger"),
                "email_id": webhook_data.get("data", {}).get("id"),
                "status": status,
                "error": error,
                "received_at": datetime.now(),
                "raw_data": webhook_data
            }
            
            self.webhook_logs.insert_one(log_entry)
            
        except Exception as e:
            print(f"Error logging webhook: {str(e)}")
    
    async def process_webhook(self, webhook_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main webhook processing function
        Called when Nylas sends a message.created webhook
        
        Args:
            webhook_data: The complete webhook payload from Nylas
            
        Returns:
            Processing result
        """
        start_time = datetime.now()
        
        try:
            # Extract email data from webhook (Nylas v3 structure)
            # Email data is in webhook_data["data"]["object"]
            data_wrapper = webhook_data.get("data", {})
            email_data = data_wrapper.get("object", {})
            email_id = email_data.get("id")
            
            print(f"🔍 Webhook structure - Type: {webhook_data.get('type')}, Email ID: {email_id}")
            
            if not email_id:
                error_msg = "No email_id in webhook data"
                self.log_webhook_call(webhook_data, "error", error_msg)
                return {"status": "error", "message": error_msg}
            
            print(f"Processing webhook for email: {email_id}")
            
            # Step 1: Check if already processed (idempotency - webhooks can retry)
            existing = self.processed_emails.find_one({"email_id": email_id})
            if existing:
                print(f"Email {email_id} already processed, skipping")
                self.log_webhook_call(webhook_data, "duplicate")
                return {
                    "status": "already_processed",
                    "email_id": email_id,
                    "vendor_id": existing.get("vendor_id")
                }
            
            # Step 2: Quick subject validation (before fetching full email)
            subject = email_data.get("subject", "")
            is_valid_subject, company_name_from_subject = self.email_service.validate_subject(subject)
            
            if not is_valid_subject:
                print(f"Email {email_id} - invalid subject: {subject}")
                
                # Store in rejected_emails
                self.rejected_emails.insert_one({
                    "email_id": email_id,
                    "reason": "invalid_subject",
                    "subject": subject,
                    "sender": email_data.get("from", [{}])[0].get("email", ""),
                    "rejected_at": datetime.now(),
                    "webhook_received_at": datetime.now()
                })
                
                self.log_webhook_call(webhook_data, "rejected", "Invalid subject line")
                
                return {
                    "status": "rejected",
                    "reason": "invalid_subject",
                    "email_id": email_id
                }
            
            # Step 3: Fetch full email details from Nylas
            print(f"Fetching full email details for {email_id}...")
            email_details = self.nylas.get_email_details(email_id)
            
            if not email_details:
                error_msg = "Failed to fetch email details from Nylas"
                self.log_webhook_call(webhook_data, "error", error_msg)
                return {"status": "error", "message": error_msg}
            
            # Step 4: Validate attachments
            # For webhook, attachments are already in email_data
            attachments = email_data.get("attachments", [])
            
            # If attachments list is empty, try fetching from full email details
            if not attachments and email_details:
                attachments = email_details.get("attachments", [])
            
            print(f"📎 Found {len(attachments)} attachments")
            
            # DEBUG: Log attachment details
            for att in attachments:
                print(f"   📌 Attachment: {att.get('filename')} | ID: {att.get('id')} | Grant: {att.get('grant_id')}")
            
            is_valid_attachments, issues = self.email_service.validate_attachments(attachments)
            
            if not is_valid_attachments:
                print(f"Email {email_id} - invalid attachments: {issues}")
                
                self.rejected_emails.insert_one({
                    "email_id": email_id,
                    "reason": "missing_or_invalid_attachments",
                    "issues": issues,
                    "subject": subject,
                    "sender": email_data.get("from", [{}])[0].get("email", ""),
                    "rejected_at": datetime.now()
                })
                
                self.log_webhook_call(webhook_data, "rejected", f"Invalid attachments: {issues}")
                
                return {
                    "status": "rejected",
                    "reason": "invalid_attachments",
                    "issues": issues,
                    "email_id": email_id
                }
            
            # Step 5: Extract basic info from email body
            body = email_details.get("body", "")
            
            # Convert HTML to plain text before extraction
            plain_text_body = self.html_to_plain_text(body)
            print(f"📝 Converted HTML body to plain text ({len(plain_text_body)} chars)")
            print(f"📄 Plain text preview:\n{plain_text_body[:500]}")  # Show first 500 chars for debugging
            
            basic_info = self.email_service.extract_basic_info(plain_text_body)
            vendor_email = basic_info.get("email", "")
            
            # Extract company name from email BODY (not subject)
            company_name = basic_info.get("company", company_name_from_subject if company_name_from_subject != "Unknown" else "Unknown")
            print(f"📊 Company name extracted from body: {company_name}")
            
            # Step 6: Deduplication check by vendor email
            if vendor_email and self.email_service.check_duplicate(email_id, vendor_email):
                print(f"Email {email_id} - duplicate vendor email: {vendor_email}")
                self.log_webhook_call(webhook_data, "duplicate")
                return {
                    "status": "duplicate",
                    "email_id": email_id,
                    "vendor_email": vendor_email
                }
            
            # Step 7: Mark as processing in DB (prevent race conditions)
            self.processed_emails.insert_one({
                "email_id": email_id,
                "status": "processing",
                "started_at": datetime.now()
            })
            
            # Step 8: Create vendor and download documents
            result = await self._create_vendor_and_download(
                email_id=email_id,
                company_name=company_name,
                basic_info=basic_info,
                attachments=attachments,
                email_details=email_details
            )
            
            processing_time = (datetime.now() - start_time).total_seconds()
            
            # Update processed_emails status
            self.processed_emails.update_one(
                {"email_id": email_id},
                {
                    "$set": {
                        "status": "completed",
                        "vendor_id": result["vendor_id"],
                        "completed_at": datetime.now(),
                        "processing_time_seconds": processing_time
                    }
                }
            )
            
            self.log_webhook_call(webhook_data, "success")
            
            print(f"Successfully processed email {email_id} → Vendor {result['vendor_id']} in {processing_time:.2f}s")
            
            return {
                "status": "success",
                "email_id": email_id,
                "vendor_id": result["vendor_id"],
                "documents_downloaded": result["documents_count"],
                "processing_time_seconds": processing_time
            }
            
        except Exception as e:
            error_msg = str(e)
            print(f"Error processing webhook: {error_msg}")
            
            # Update processed_emails with error
            if email_id:
                self.processed_emails.update_one(
                    {"email_id": email_id},
                    {
                        "$set": {
                            "status": "failed",
                            "error": error_msg,
                            "failed_at": datetime.now()
                        }
                    },
                    upsert=True
                )
            
            self.log_webhook_call(webhook_data, "error", error_msg)
            
            return {
                "status": "error",
                "message": error_msg,
                "email_id": email_id if email_id else None
            }
    
    async def _create_vendor_and_download(
        self,
        email_id: str,
        company_name: str,
        basic_info: Dict[str, Any],
        attachments: list,
        email_details: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create vendor record and download documents
        (Extracted from VendorEmailService.stage2_download_and_store)
        """
        # Extract grant_id from attachments (webhook provides it) or use default from env
        grant_id = None
        if attachments and len(attachments) > 0:
            grant_id = attachments[0].get("grant_id")
        
        if not grant_id:
            grant_id = email_details.get("grant_id")
        
        if not grant_id:
            grant_id = os.getenv("NYLAS_GRANT_ID")
        
        print(f"🔑 Using grant_id: {grant_id}")
        print(f"🔑 Attachment[0] grant_id: {attachments[0].get('grant_id') if attachments else 'N/A'}")
        print(f"🔑 Email details grant_id: {email_details.get('grant_id')}")
        print(f"🔑 ENV grant_id: {os.getenv('NYLAS_GRANT_ID')}")
        
        # Generate vendor_id
        vendor_email = basic_info.get("email", f"unknown_{email_id}")
        
        # Get count for unique ID
        vendor_count = self.vendors.count_documents({}) + 1
        vendor_id = f"VENDOR_{vendor_count:04d}_{vendor_email.replace('@', '_').replace('.', '_')}"
        
        # Create vendor workspace
        paths = self.email_service.create_vendor_workspace(vendor_id)
        
        # Save metadata
        metadata = {
            "vendor_id": vendor_id,
            "company_name": company_name,
            "basic_info": basic_info,
            "email_metadata": {
                "subject": email_details.get("subject"),
                "sender": email_details.get("from", [{}])[0].get("email", ""),
                "received_at": email_details.get("date")
            },
            "created_at": datetime.now().isoformat(),
            "source": "webhook"  # Mark as webhook-processed
        }
        
        with open(paths["metadata"], 'w') as f:
            json.dump(metadata, f, indent=2)
        
        # Save raw email data
        with open(paths["email_raw"], 'w') as f:
            json.dump({
                "email_id": email_id,
                "subject": email_details.get("subject"),
                "sender": email_details.get("from", [{}])[0].get("email", ""),
                "body": email_details.get("body"),
                "received_at": email_details.get("date")
            }, f, indent=2)
        
        # Download attachments in parallel
        downloaded_docs = await self.email_service.download_attachments_parallel(
            vendor_id,
            email_id,
            attachments,
            paths["documents"],
            grant_id  # Pass grant_id for proper API access
        )
        
        # ========== IMMEDIATE CATALOGUE PROCESSING (Stage 2) ==========
        # Process catalogue CSV immediately if present (no batching/LLM needed)
        catalogue_result = None
        for doc in downloaded_docs:
            if doc.get("type") == "catalogue":
                catalogue_path = os.path.join(paths["documents"], doc["filename"])
                if os.path.exists(catalogue_path):
                    print(f"📊 Processing catalogue for {vendor_id}...")
                    catalogue_result = catalogue_processor.process_csv(catalogue_path, vendor_id)
                    catalogue_processor.save_to_extracted_folder(catalogue_result, vendor_id, paths["base"])
                    print(f"✅ Catalogue processing complete: {catalogue_result['row_count']} products")
                break
        
        # Create MongoDB vendor record
        vendor_record = {
            "vendor_id": vendor_id,
            "company_name": company_name,
            "basic_info": basic_info,
            "email_metadata": {
                "email_id": email_id,
                "subject": email_details.get("subject"),
                "sender": email_details.get("from", [{}])[0].get("email", ""),
                "received_at": email_details.get("date")
            },
            "documents": downloaded_docs,
            "workspace_path": paths["base"],
            "status": "ready_for_extraction",
            "source": "webhook",  # Track webhook vs polling
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        }
        
        # Add catalogue to extracted_data if processed
        if catalogue_result and catalogue_result.get("success"):
            vendor_record["extracted_data"] = {
                "catalogue": {
                    "data": {
                        "products": catalogue_result["products"],
                        "row_count": catalogue_result["row_count"],
                        "columns": catalogue_result.get("columns", [])
                    },
                    "confidence": catalogue_result["confidence"],
                    "processed_at": catalogue_result["processed_at"],
                    "validation_errors": catalogue_result.get("validation_errors", [])
                }
            }
            print(f"✅ Catalogue added to vendor record: {catalogue_result['row_count']} products")
        
        self.vendors.insert_one(vendor_record)
        
        return {
            "vendor_id": vendor_id,
            "documents_count": len(downloaded_docs)
        }
    
    def get_webhook_statistics(self) -> Dict[str, Any]:
        """Get webhook processing statistics"""
        try:
            # Count by status
            total_received = self.webhook_logs.count_documents({})
            successful = self.webhook_logs.count_documents({"status": "success"})
            duplicates = self.webhook_logs.count_documents({"status": "duplicate"})
            rejected = self.webhook_logs.count_documents({"status": "rejected"})
            errors = self.webhook_logs.count_documents({"status": "error"})
            
            # Recent webhooks
            recent = list(self.webhook_logs.find(
                {},
                {"_id": 0, "raw_data": 0}
            ).sort("received_at", -1).limit(10))
            
            # Convert datetime to string
            for item in recent:
                if "received_at" in item:
                    item["received_at"] = item["received_at"].isoformat()
            
            return {
                "total_webhooks_received": total_received,
                "successful": successful,
                "duplicates": duplicates,
                "rejected": rejected,
                "errors": errors,
                "success_rate": (successful / total_received * 100) if total_received > 0 else 0,
                "recent_webhooks": recent
            }
            
        except Exception as e:
            print(f"Error getting webhook statistics: {str(e)}")
            return {"error": str(e)}
