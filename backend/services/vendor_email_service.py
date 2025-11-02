"""
Vendor Email Processing Service
Implements Stage 1 & 2 of the vendor registration pipeline
"""
import os
import re
import json
import uuid
import asyncio
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from pymongo import MongoClient
from services.nylas_service import NylasService
import concurrent.futures
from utils.pdf_converter import pdf_converter


class VendorEmailService:
    """Service for processing vendor registration emails"""
    
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
        self.job_status = {}  # In-memory job status tracking
        
        # Vendor storage base path
        self.vendors_base_path = "vendors"
        os.makedirs(self.vendors_base_path, exist_ok=True)
        
        # Advanced regex patterns for email body parsing - flexible and case-insensitive
        self.patterns = {
            # Name: looks for variations like "name:", "full name:", "vendor name:", etc.
            "name": r"(?:vendor\s+)?(?:full\s+)?name[\s:]+([A-Za-z\s.]+?)(?:\n|age|role|gender|mobile|phone|email|$)",
            
            # Age: looks for "age:" followed by 1-3 digits
            "age": r"age[\s:]+(\d{1,3})",
            
            # Role: looks for "role:", "designation:", "type:", "category:" followed by text
            "role": r"(?:role|designation|type|category|business\s+type)[\s:]+([A-Za-z\s/\-]+?)(?:\n|gender|mobile|phone|email|$)",
            
            # Gender: looks for "gender:", "sex:" followed by Male/Female/Other variations
            "gender": r"(?:gender|sex)[\s:]+([A-Za-z]+)",
            
            # Mobile: looks for "mobile:", "phone:", "contact:", "number:" followed by phone number
            # Handles formats like: +91-9876543210, 9876543210, [+91-9876543210], (+91) 9876543210, etc.
            "mobile": r"(?:mobile|phone|contact|number|cell)[\s:]+[\[\(]?([0-9+\s\-()]+?)[\]\)]?(?:\n|registered|address|attachments|$)",
            
            # Email: comprehensive email pattern
            "email": r"(?:email|e-mail|mail)[\s:]+([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})",
            
            # Company Name: looks for "company:", "company name:", "business name:", "organization:", etc.
            "company": r"(?:company(?:\s+name)?|business(?:\s+name)?|organization|firm|enterprise)[\s:]+([A-Za-z0-9\s.&,-]+?)(?:\n|official|email|mobile|phone|registered|$)",
            
            # Address: looks for "address:", "location:", etc. (multi-line support)
            "address": r"(?:address|location|office\s+address)[\s:]+(.+?)(?:\n\n|\nname|\nage|\nrole|$)",
        }
    
    def validate_subject(self, subject: str) -> Tuple[bool, Optional[str]]:
        """
        Advanced subject validation - case-insensitive, flexible matching
        
        Must contain "VENDOR" AND "REGISTRATION" (in any case, any order, with any separators)
        Examples that will match:
        - "VENDOR REGISTRATION - Company Name"
        - "arav_vendor_REGISTRATION"
        - "Application for Vendor Registration"
        - "vendor_registration_request"
        - "Registration for Vendor - ABC Corp"
        
        Returns:
            (is_valid, company_name)
        """
        if not subject:
            return False, None
        
        subject_upper = subject.upper()
        
        # Check if both "VENDOR" and "REGISTRATION" are present (case-insensitive)
        has_vendor = "VENDOR" in subject_upper
        has_registration = "REGISTRATION" in subject_upper
        
        if not (has_vendor and has_registration):
            return False, None
        
        # Try to extract company name from various patterns
        company_name = "Unknown"
        
        # Pattern 1: "VENDOR REGISTRATION - Company Name"
        dash_pattern = r"vendor\s*registration\s*[-:]\s*(.+?)$"
        match = re.search(dash_pattern, subject, re.IGNORECASE)
        if match:
            company_name = match.group(1).strip()
        
        # Pattern 2: "Company Name - VENDOR REGISTRATION"
        elif re.search(r"(.+?)\s*[-:]\s*vendor\s*registration", subject, re.IGNORECASE):
            match = re.search(r"(.+?)\s*[-:]\s*vendor\s*registration", subject, re.IGNORECASE)
            company_name = match.group(1).strip()
        
        # Pattern 3: Extract from filename-like patterns "companyname_vendor_registration"
        elif "_" in subject or "-" in subject:
            # Remove "vendor" and "registration" words and clean up
            cleaned = re.sub(r"(vendor|registration)", "", subject, flags=re.IGNORECASE)
            cleaned = re.sub(r"[_\-]+", " ", cleaned).strip()
            if cleaned:
                company_name = cleaned
        
        return True, company_name
    
    def validate_attachments(self, attachments: List[Dict[str, Any]]) -> Tuple[bool, List[str]]:
        """
        Advanced attachment validation - case-insensitive, flexible matching
        
        Required documents (MUST contain these words in filename):
        - "aadhar" or "aadhaar" (both spellings) - PDF/Image
        - "pan" - PDF/Image
        - "gst" - PDF/Image
        
        Optional document:
        - "catalogue" or "catalog" - CSV only
        
        Examples that will match:
        - "aadhar_of_ankit.pdf"
        - "ankit_PAN.jpg"
        - "gst_of_COMPANY.pdf"
        - "catalogue_products.csv"
        - "AADHAAR_CARD_RAJESH.png"
        - "company_GST_certificate.pdf"
        
        Returns:
            (is_valid, issues_list)
        """
        valid_extensions_pdf_image = [".pdf", ".jpg", ".jpeg", ".png"]
        valid_extensions_csv = [".csv"]
        
        issues = []
        found_types = set()
        
        for att in attachments:
            filename = att.get("filename", "")
            filename_lower = filename.lower()
            
            # Check for catalogue first (CSV only)
            if re.search(r"catalog(?:ue)?|product|inventory", filename_lower):
                has_csv = any(filename_lower.endswith(ext) for ext in valid_extensions_csv)
                if has_csv:
                    found_types.add("catalogue")
                    continue  # Valid catalogue, skip further checks
                else:
                    # Catalogue must be CSV
                    issues.append(f"Invalid extension for catalogue: {filename} (must be .csv)")
                    continue
            
            # Check extension for other documents (PDF/Image)
            has_valid_ext = any(filename_lower.endswith(ext) for ext in valid_extensions_pdf_image)
            if not has_valid_ext:
                issues.append(f"Invalid extension: {filename} (must be .pdf, .jpg, .jpeg, .png, or .csv for catalogue)")
                continue
            
            # Check if filename contains required keywords (case-insensitive, simple substring match)
            # Check for aadhar/aadhaar (both spellings)
            if re.search(r"aadh[a]?ar", filename_lower):
                found_types.add("aadhar")
            
            # Check for PAN (simple substring)
            if "pan" in filename_lower:
                found_types.add("pan")
            
            # Check for GST (simple substring)
            if "gst" in filename_lower:
                found_types.add("gst")
        
        # Check if all required types present (catalogue is optional)
        required_types = {"aadhar", "pan", "gst"}
        missing = required_types - found_types
        if missing:
            missing_list = [k.upper() for k in missing]
            issues.append(f"Missing documents: {', '.join(missing_list)}")
        
        is_valid = len(issues) == 0
        return is_valid, issues
    
    def extract_basic_info(self, email_body: str) -> Dict[str, Any]:
        """
        Advanced extraction of vendor information using comprehensive regex patterns
        Handles various formats and missing fields gracefully
        
        Returns:
            Dictionary with extracted fields
        """
        info = {}
        
        # Extract each field using advanced regex (case-insensitive, multi-line)
        for field, pattern in self.patterns.items():
            match = re.search(pattern, email_body, re.IGNORECASE | re.MULTILINE | re.DOTALL)
            if match:
                value = match.group(1).strip()
                # Clean up extra whitespace
                value = re.sub(r'\s+', ' ', value)
                info[field] = value
        
        # Post-processing and validation
        validation_status = "complete"
        validation_issues = []
        
        # Validate and clean mobile number
        if "mobile" in info:
            # Extract only digits
            digits = re.sub(r"[^\d]", "", info["mobile"])
            if len(digits) < 10 or len(digits) > 15:
                validation_issues.append(f"Invalid mobile length: {len(digits)} digits")
                validation_status = "needs_manual_review"
            else:
                # Store cleaned mobile number
                info["mobile_cleaned"] = digits
        
        # Validate email format
        if "email" in info:
            email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
            if not re.match(email_pattern, info["email"]):
                validation_issues.append("Invalid email format")
                validation_status = "needs_manual_review"
        
        # Validate age if present
        if "age" in info:
            try:
                age_val = int(info["age"])
                if age_val < 18 or age_val > 100:
                    validation_issues.append(f"Age out of range: {age_val}")
                    validation_status = "needs_manual_review"
            except ValueError:
                validation_issues.append("Invalid age format")
                validation_status = "needs_manual_review"
        
        # Check completeness - mandatory fields
        required_fields = ["name", "mobile", "email"]
        missing = [f for f in required_fields if f not in info or not info[f]]
        
        # Optional but recommended fields
        optional_fields = ["age", "role", "gender", "company"]
        missing_optional = [f for f in optional_fields if f not in info or not info[f]]
        
        if missing:
            validation_status = "needs_manual_review"
            validation_issues.append(f"Missing required fields: {', '.join(missing)}")
            info["missing_required_fields"] = missing
        
        if missing_optional:
            info["missing_optional_fields"] = missing_optional
        
        info["validation_status"] = validation_status
        if validation_issues:
            info["validation_issues"] = validation_issues
        
        return info
    
    def check_duplicate(self, email_id: str, vendor_email: str) -> bool:
        """
        Check if email has already been processed using MongoDB (production-ready)
        No reliance on local storage
        
        Returns:
            True if duplicate, False otherwise
        """
        try:
            # Check by Nylas email_id in processed_emails collection
            if self.processed_emails.find_one({"email_id": email_id}):
                print(f"Duplicate found: Email ID {email_id} already processed")
                return True
            
            # Check by vendor email address in vendors collection
            if vendor_email:
                existing_vendor = self.vendors.find_one({"basic_info.email": vendor_email})
                if existing_vendor:
                    print(f"Duplicate found: Vendor email {vendor_email} already exists")
                    return True
            
            return False
            
        except Exception as e:
            print(f"Error checking duplicate: {str(e)}")
            # In case of DB error, return False to allow processing (fail-safe)
            return False
    
    async def stage1_validate_and_extract(self, emails: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        STAGE 1: Email Ingestion, Validation & Basic Info Extraction
        
        Returns:
            Processing summary
        """
        summary = {
            "total": len(emails),
            "valid": 0,
            "invalid_subject": 0,
            "missing_attachments": 0,
            "already_processed": 0,
            "needs_review": 0,
            "valid_emails": []
        }
        
        for email in emails:
            try:
                email_id = email.get("id")
                subject = email.get("subject", "")
                sender = email.get("from", [{}])[0].get("email", "")
                received_at = email.get("date")
                
                # Step 1.1: Subject validation
                is_valid_subject, company_name = self.validate_subject(subject)
                if not is_valid_subject:
                    summary["invalid_subject"] += 1
                    self.rejected_emails.insert_one({
                        "email_id": email_id,
                        "reason": "invalid_subject",
                        "subject": subject,
                        "sender": sender,
                        "rejected_at": datetime.now()
                    })
                    continue
                
                # Get email body and attachments
                email_details = self.nylas.get_email_details(email_id)
                if not email_details:
                    continue
                
                body = email_details.get("body", "")
                attachments = email_details.get("attachments", [])
                
                # Step 1.2: Attachment validation
                is_valid_attachments, issues = self.validate_attachments(attachments)
                if not is_valid_attachments:
                    summary["missing_attachments"] += 1
                    self.rejected_emails.insert_one({
                        "email_id": email_id,
                        "reason": "missing_or_invalid_attachments",
                        "issues": issues,
                        "subject": subject,
                        "sender": sender,
                        "rejected_at": datetime.now()
                    })
                    continue
                
                # Step 1.3: Extract basic info from email body
                basic_info = self.extract_basic_info(body)
                vendor_email = basic_info.get("email", "")
                
                # Step 1.4: Deduplication check
                if self.check_duplicate(email_id, vendor_email):
                    summary["already_processed"] += 1
                    continue
                
                # Flag for manual review if needed
                if basic_info.get("validation_status") == "needs_manual_review":
                    summary["needs_review"] += 1
                
                # Mark as valid
                summary["valid"] += 1
                summary["valid_emails"].append({
                    "email_id": email_id,
                    "company_name": company_name,
                    "basic_info": basic_info,
                    "attachments": attachments,
                    "sender": sender,
                    "subject": subject,
                    "body": body,
                    "received_at": received_at
                })
                
                # Store in processed_emails
                self.processed_emails.insert_one({
                    "email_id": email_id,
                    "status": "validated",
                    "processed_at": datetime.now()
                })
                
            except Exception as e:
                print(f"Error processing email {email.get('id')}: {str(e)}")
                continue
        
        return summary
    
    def generate_vendor_id(self, email: str, index: int) -> str:
        """Generate unique vendor ID"""
        return f"VENDOR_{index:04d}_{email.replace('@', '_').replace('.', '_')}"
    
    def create_vendor_workspace(self, vendor_id: str) -> Dict[str, str]:
        """
        Create isolated directory structure for vendor
        
        Returns:
            Dictionary with paths
        """
        base_path = os.path.join(self.vendors_base_path, vendor_id)
        
        paths = {
            "base": base_path,
            "documents": os.path.join(base_path, "documents"),
            "extracted": os.path.join(base_path, "extracted"),
            "metadata": os.path.join(base_path, "metadata.json"),
            "email_raw": os.path.join(base_path, "email_raw.json")
        }
        
        # Create directories
        os.makedirs(paths["documents"], exist_ok=True)
        os.makedirs(paths["extracted"], exist_ok=True)
        
        return paths
    
    def classify_document_type(self, filename: str) -> Optional[str]:
        """
        Advanced document classification - checks if keywords exist ANYWHERE in filename
        Case-insensitive matching
        
        Examples:
        - "aadhar_of_ankit.pdf" -> "aadhar"
        - "ankit_PAN.jpg" -> "pan"  
        - "gst_of_COMPANY.pdf" -> "gst"
        - "AADHAAR_CARD.png" -> "aadhar"
        - "product_catalogue.csv" -> "catalogue"
        """
        filename_lower = filename.lower()
        
        # Check for catalogue (must be CSV)
        if filename_lower.endswith('.csv') and ('catalogue' in filename_lower or 'catalog' in filename_lower or 
                                                  'product' in filename_lower or 'inventory' in filename_lower):
            return "catalogue"
        
        # Check for aadhar/aadhaar (both spellings)
        elif re.search(r"aadh[a]?ar", filename_lower):
            return "aadhar"
        
        # Check for PAN (as whole word or part of compound words)
        elif "pan" in filename_lower:
            return "pan"
        
        # Check for GST (as whole word or part of compound words)
        elif "gst" in filename_lower:
            return "gst"
        
        return None
    
    async def download_attachments_parallel(self, vendor_id: str, email_id: str, 
                                           attachments: List[Dict[str, Any]], 
                                           documents_path: str, grant_id: str = None) -> List[Dict[str, Any]]:
        """
        Download attachments in parallel
        
        Args:
            vendor_id: Vendor identifier
            email_id: Message ID
            attachments: List of attachment dictionaries
            documents_path: Path to save documents
            grant_id: Nylas grant ID (optional, uses default if not provided)
        
        Returns:
            List of downloaded document info
        """
        downloaded_docs = []
        
        # Use grant_id from parameter or environment
        gid = grant_id or os.getenv("NYLAS_GRANT_ID")
        
        # Use ThreadPoolExecutor for parallel downloads
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = []
            
            for att in attachments:
                att_id = att.get("id")
                filename = att.get("filename")
                doc_type = self.classify_document_type(filename)
                
                if not doc_type:
                    print(f"⏭️ Skipping {filename} (not aadhar/pan/gst)")
                    continue
                
                print(f"📤 Submitting download: {filename} (ID: {att_id})")
                
                # Submit download task with new signature
                future = executor.submit(
                    self.nylas.download_attachment,
                    gid,
                    email_id,
                    att_id,
                    documents_path
                )
                futures.append((future, att, doc_type, filename))
            
            # Collect results
            for future, att, doc_type, filename in futures:
                try:
                    file_path = future.result(timeout=30)
                    
                    if file_path and os.path.exists(file_path):
                        file_size = os.path.getsize(file_path)
                        
                        # Check if file is a PDF - convert to images
                        if pdf_converter.is_pdf(file_path):
                            print(f"📄 PDF detected: {filename}, converting to images...")
                            try:
                                # Convert PDF to image(s) - returns list of converted images
                                converted_images = pdf_converter.convert_pdf_to_images(
                                    file_path, 
                                    output_format="png"
                                )
                                
                                # Add each converted image to downloaded_docs
                                for img_info in converted_images:
                                    img_filename = os.path.basename(img_info["path"])
                                    downloaded_docs.append({
                                        "type": doc_type,  # Same doc type for all pages
                                        "filename": img_filename,
                                        "path": img_info["path"],
                                        "size": img_info["size"],
                                        "downloaded_at": datetime.now().isoformat(),
                                        "converted_from_pdf": True,
                                        "pdf_page": img_info["page"]
                                    })
                                    print(f"✅ Converted page {img_info['page']}: {img_filename}")
                                
                            except Exception as pdf_error:
                                print(f"⚠️ PDF conversion failed for {filename}: {pdf_error}")
                                # Fallback: keep original PDF if conversion fails
                                downloaded_docs.append({
                                    "type": doc_type,
                                    "filename": filename,
                                    "path": file_path,
                                    "size": file_size,
                                    "downloaded_at": datetime.now().isoformat()
                                })
                        else:
                            # Regular image file - add as-is
                            downloaded_docs.append({
                                "type": doc_type,
                                "filename": filename,
                                "path": file_path,
                                "size": file_size,
                                "downloaded_at": datetime.now().isoformat()
                            })
                            print(f"✅ Successfully downloaded: {filename}")
                    else:
                        print(f"❌ Failed to download: {filename}")
                        
                except Exception as e:
                    print(f"❌ Error downloading {filename}: {str(e)}")
        
        return downloaded_docs
    
    async def stage2_download_and_store(self, valid_emails: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        STAGE 2: Document Download & Vendor-Isolated Storage
        
        Returns:
            Processing summary
        """
        summary = {
            "total_vendors": len(valid_emails),
            "successful": 0,
            "failed": 0,
            "total_documents": 0,
            "vendors": []
        }
        
        for idx, email_data in enumerate(valid_emails, start=1):
            try:
                # Step 2.1: Generate vendor ID
                vendor_email = email_data["basic_info"].get("email", f"unknown_{idx}")
                vendor_id = self.generate_vendor_id(vendor_email, idx)
                
                # Step 2.2: Create vendor workspace
                paths = self.create_vendor_workspace(vendor_id)
                
                # Save metadata
                metadata = {
                    "vendor_id": vendor_id,
                    "company_name": email_data["company_name"],
                    "basic_info": email_data["basic_info"],
                    "email_metadata": {
                        "subject": email_data["subject"],
                        "sender": email_data["sender"],
                        "received_at": email_data["received_at"]
                    },
                    "created_at": datetime.now().isoformat()
                }
                
                with open(paths["metadata"], 'w') as f:
                    json.dump(metadata, f, indent=2)
                
                # Save raw email data
                with open(paths["email_raw"], 'w') as f:
                    json.dump({
                        "email_id": email_data["email_id"],
                        "subject": email_data["subject"],
                        "sender": email_data["sender"],
                        "body": email_data["body"],
                        "received_at": email_data["received_at"]
                    }, f, indent=2)
                
                # Step 2.3 & 2.4: Download attachments in parallel
                downloaded_docs = await self.download_attachments_parallel(
                    vendor_id,
                    email_data["email_id"],
                    email_data["attachments"],
                    paths["documents"]
                )
                
                summary["total_documents"] += len(downloaded_docs)
                
                # Step 2.5: Create MongoDB vendor record
                vendor_record = {
                    "vendor_id": vendor_id,
                    "company_name": email_data["company_name"],
                    "basic_info": email_data["basic_info"],
                    "email_metadata": {
                        "email_id": email_data["email_id"],
                        "subject": email_data["subject"],
                        "sender": email_data["sender"],
                        "received_at": email_data["received_at"]
                    },
                    "documents": downloaded_docs,
                    "workspace_path": paths["base"],
                    "status": "ready_for_extraction",
                    "created_at": datetime.now(),
                    "updated_at": datetime.now()
                }
                
                self.vendors.insert_one(vendor_record)
                
                summary["successful"] += 1
                summary["vendors"].append({
                    "vendor_id": vendor_id,
                    "email": vendor_email,
                    "documents_count": len(downloaded_docs)
                })
                
                # Update processed_emails status
                self.processed_emails.update_one(
                    {"email_id": email_data["email_id"]},
                    {"$set": {"status": "completed", "vendor_id": vendor_id}}
                )
                
            except Exception as e:
                print(f"Error in stage 2 for email {email_data.get('email_id')}: {str(e)}")
                summary["failed"] += 1
        
        return summary
    
    async def process_emails(self, limit: int = 1000) -> Dict[str, Any]:
        """
        Main processing function - Executes Stage 1 & 2
        
        Returns:
            Complete processing summary
        """
        start_time = datetime.now()
        
        try:
            # Fetch emails from Nylas
            print(f"Fetching up to {limit} emails from Nylas...")
            emails = self.nylas.fetch_emails(limit=limit)
            
            if not emails:
                return {
                    "success": True,
                    "message": "No emails found",
                    "stage1": {"total": 0},
                    "stage2": {"total_vendors": 0}
                }
            
            # STAGE 1: Validation & Basic Extraction
            print("Starting Stage 1: Validation & Basic Extraction...")
            stage1_result = await self.stage1_validate_and_extract(emails)
            
            # STAGE 2: Document Download & Storage
            print("Starting Stage 2: Document Download & Storage...")
            stage2_result = await self.stage2_download_and_store(stage1_result["valid_emails"])
            
            end_time = datetime.now()
            processing_time = (end_time - start_time).total_seconds()
            
            return {
                "success": True,
                "message": "Email processing completed",
                "stage1": {
                    "total": stage1_result["total"],
                    "valid": stage1_result["valid"],
                    "invalid_subject": stage1_result["invalid_subject"],
                    "missing_attachments": stage1_result["missing_attachments"],
                    "already_processed": stage1_result["already_processed"],
                    "needs_review": stage1_result["needs_review"]
                },
                "stage2": {
                    "total_vendors": stage2_result["total_vendors"],
                    "successful": stage2_result["successful"],
                    "failed": stage2_result["failed"],
                    "total_documents": stage2_result["total_documents"]
                },
                "processing_time_seconds": processing_time,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            print(f"Error in process_emails: {str(e)}")
            raise
    
    def start_background_processing(self, limit: int = 1000) -> str:
        """
        Start email processing in background
        
        Returns:
            Job ID for tracking
        """
        job_id = str(uuid.uuid4())
        
        self.job_status[job_id] = {
            "status": "processing",
            "started_at": datetime.now().isoformat(),
            "progress": {}
        }
        
        # In a real implementation, use background task queue like Celery or BullMQ
        # For now, we'll simulate with asyncio
        asyncio.create_task(self._background_process(job_id, limit))
        
        return job_id
    
    async def _background_process(self, job_id: str, limit: int):
        """Background processing task"""
        try:
            result = await self.process_emails(limit=limit)
            
            self.job_status[job_id] = {
                "status": "completed",
                "started_at": self.job_status[job_id]["started_at"],
                "completed_at": datetime.now().isoformat(),
                "results": result
            }
        except Exception as e:
            self.job_status[job_id] = {
                "status": "failed",
                "started_at": self.job_status[job_id]["started_at"],
                "failed_at": datetime.now().isoformat(),
                "error": str(e)
            }
    
    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get background job status"""
        return self.job_status.get(job_id)
    
    def get_vendor_by_id(self, vendor_id: str) -> Optional[Dict[str, Any]]:
        """Get vendor details from MongoDB"""
        vendor = self.vendors.find_one({"vendor_id": vendor_id}, {"_id": 0})
        
        if vendor:
            # Convert datetime objects to strings
            if "created_at" in vendor:
                vendor["created_at"] = vendor["created_at"].isoformat()
            if "updated_at" in vendor:
                vendor["updated_at"] = vendor["updated_at"].isoformat()
        
        return vendor
    
    def list_vendors(self, status: Optional[str] = None, limit: int = 100, skip: int = 0) -> List[Dict[str, Any]]:
        """List vendors with optional filtering"""
        query = {}
        if status:
            query["status"] = status
        
        vendors = list(self.vendors.find(query, {"_id": 0}).skip(skip).limit(limit))
        
        # Convert datetime objects
        for vendor in vendors:
            if "created_at" in vendor:
                vendor["created_at"] = vendor["created_at"].isoformat()
            if "updated_at" in vendor:
                vendor["updated_at"] = vendor["updated_at"].isoformat()
        
        return vendors
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get overall processing statistics"""
        total_processed = self.processed_emails.count_documents({})
        total_vendors = self.vendors.count_documents({})
        total_rejected = self.rejected_emails.count_documents({})
        
        # Status distribution
        status_distribution = {}
        for status in ["pending_extraction", "downloading_documents", "ready_for_extraction"]:
            count = self.vendors.count_documents({"status": status})
            status_distribution[status] = count
        
        return {
            "total_emails_processed": total_processed,
            "total_vendors_created": total_vendors,
            "total_rejected": total_rejected,
            "status_distribution": status_distribution,
            "last_updated": datetime.now().isoformat()
        }
