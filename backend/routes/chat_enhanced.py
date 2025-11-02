"""
Enhanced Chat Routes with Confirmation Stage and MongoDB Integration
Matches email registration pipeline exactly
"""
from fastapi import APIRouter, HTTPException, UploadFile, File, BackgroundTasks
from typing import Dict, Any, List
import uuid
import os
import json
import shutil
from datetime import datetime
from pathlib import Path

from models import (
    ChatResponse, ChatMessage, VendorDraftModel, 
    ChatStage, DocumentType, AadhaarData, PANData, GSTData,
    BasicDetailsData, APIResponse, SessionStatus, ChatHistoryResponse, TTSResponse,
    MessageRequest, TTSRequest, ConfirmationSummary, VendorConfirmationRequest,
    VendorCreationResponse
)
from database import db
from services.tts_service import TTSService
from utils.pdf_converter import pdf_converter
from utils.catalogue_processor import catalogue_processor
from openai import OpenAI

router = APIRouter(prefix="/api/v1/chat", tags=["Chat Management - Enhanced"])
tts_service = TTSService()

# Temp uploads directory (before confirmation)
TEMP_UPLOAD_DIR = "temp_uploads"
os.makedirs(TEMP_UPLOAD_DIR, exist_ok=True)

# Vendor base path (after confirmation - matches email registration)
VENDORS_BASE_PATH = "vendors"
os.makedirs(VENDORS_BASE_PATH, exist_ok=True)


class ChatHandler:
    """Handles chat flow with confirmation stage"""
    
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    async def extract_basic_detail_with_llm(self, message: str, current_details: Dict[str, Any]) -> Dict[str, Any]:
        """Use LLM to intelligently extract and update basic details with PROPER formatting"""
        
        # Find what's missing
        required_fields = ['full_name', 'company_name', 'designation', 'age', 'gender', 'mobile_number', 'email_id']
        missing_fields = [f for f in required_fields if not current_details.get(f)]
        
        extraction_prompt = f"""
You are a data extraction AI. Extract ONLY the raw values from user input. Normalization will be handled separately.

Current data: {json.dumps(current_details, indent=2)}
Missing fields: {missing_fields}

User message: "{message}"

EXTRACTION RULES:
1. full_name: Extract proper name (e.g., "Hi I am ankit kumar" → "Ankit Kumar")
2. designation: Extract job title (e.g., "founder" → "founder", "I work as manager" → "manager")
3. age: Extract number only (e.g., "25 years old" → 25)
4. gender: Extract AS-IS (e.g., "m" → "m", "male" → "male", "M" → "M") - normalization handled separately
5. mobile_number: Extract 10 digits (e.g., "9876543210" → "9876543210")
6. email_id: Extract email address (e.g., "ankit@gmail.com" → "ankit@gmail.com")

IMPORTANT FOR GENDER:
- Just extract whatever the user said: "m", "M", "male", "female", "f", etc.
- Do NOT try to convert it yourself
- If user says "m", extract "m" (not "Male")

Return JSON with extracted values:
{{
  "updates": {{
    "field_name": "raw_extracted_value"
  }},
  "is_correction": true/false
}}

Examples:
- "Hi I am ankit kumar" → {{"updates": {{"full_name": "Ankit Kumar"}}, "is_correction": false}}
- "male" → {{"updates": {{"gender": "male"}}, "is_correction": false}}
- "m" → {{"updates": {{"gender": "m"}}, "is_correction": false}}
- "founder" → {{"updates": {{"designation": "founder"}}, "is_correction": false}}
- "25" → {{"updates": {{"age": 25}}, "is_correction": false}}
"""

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": extraction_prompt}],
                max_tokens=200,
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            print(f"DEBUG: LLM extraction result: {result}")
            return result
            
        except Exception as e:
            print(f"LLM extraction error: {e}")
            return {"updates": {}, "is_correction": False}
        
    async def get_conversational_response(self, 
        stage: ChatStage, 
        messages: List[Dict], 
        extracted_data: Dict = None,
        missing_field: str = None
    ) -> str:
        """Get conversational AI response using proper system prompt"""
        
        # Build context based on stage - using ORIGINAL chat.py system prompts
        if stage == ChatStage.COLLECTING_BASIC_DETAILS:
            system_content = """You are an intelligent vendor registration assistant collecting details step by step.

CRITICAL INSTRUCTIONS:
1. From user messages, extract ONLY the relevant data value, not the entire sentence
2. Handle corrections and updates when users want to change information
3. Be smart - extract meaningful info from conversational responses
4. Keep responses SHORT, warm, and conversational

EXTRACTION RULES:
- Name: Extract proper name format (e.g., "Hi I am ankit kumar" → "Ankit Kumar")  
- Age: Extract just the number (e.g., "I am 25 years old" → 25)
- Designation: Extract job title (e.g., "I work as a manager" → "Manager")
- Gender: Extract and normalize to "Male" or "Female" EXACTLY
- Mobile: Extract 10-digit number only
- Email: Extract valid email address only

Ask for ONE missing field at a time conversationally. Be friendly and professional."""
            
            if missing_field:
                system_content += f"\n\nNext field to collect: {missing_field}"
            
            if extracted_data:
                system_content += f"\n\nAlready collected: {json.dumps(extracted_data, indent=2)}"
        
        elif stage == ChatStage.AADHAAR_REQUEST:
            return "Great! Now please upload your **Aadhaar card**. You can upload it as JPG, PNG, or PDF (multi-page supported)."
        
        elif stage == ChatStage.PAN_REQUEST:
            return "Perfect! Aadhaar received. Now please upload your **PAN card** (JPG, PNG, or PDF)."
        
        elif stage == ChatStage.GST_REQUEST:
            return "Excellent! PAN card uploaded successfully. Finally, please upload your **GST certificate** (JPG, PNG, or PDF)."
        
        elif stage == ChatStage.AWAITING_CONFIRMATION:
            return "All documents received! Please review your information in the confirmation summary, then type CONFIRM to submit."
        
        else:
            return "Thank you! How can I assist you further?"
        
        # Generate conversational response for basic details
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "system", "content": system_content}] + messages,
                max_tokens=150,
                temperature=0.7
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"OpenAI error: {e}")
            return "I'm having trouble processing your request. Please try again."


chat_handler = ChatHandler()


@router.post("/upload-document/{session_id}")
async def upload_document_to_temp(
    session_id: str,
    document_type: str,
    file: UploadFile = File(...)
):
    """
    Upload document to temporary storage (before confirmation)
    Supports PDF multi-page conversion identical to email registration
    """
    
    # Normalize document type (handle common variations)
    doc_type_normalized = document_type.lower().strip()
    
    # Map common variations to standard types (must match DocumentType enum!)
    type_mapping = {
        "aadhar": "aadhaar",      # Map to enum value: "aadhaar"
        "aadhaar": "aadhaar",     # Standard spelling
        "adhaar": "aadhaar",      # Common misspelling
        "adhar": "aadhaar",       # Another variation
        "pan": "pan",
        "gst": "gst",
        "gstin": "gst",
        "catalogue": "catalogue",
        "catalog": "catalogue",
        "product_list": "catalogue",
        "products": "catalogue"
    }
    
    if doc_type_normalized not in type_mapping:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid document type '{document_type}'. Use: aadhar/aadhaar, pan, gst, or catalogue"
        )
    
    # Use standardized type (matches DocumentType enum)
    doc_type_standard = type_mapping[doc_type_normalized]
    
    try:
        doc_type = DocumentType(doc_type_standard)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid document type. Use: aadhar, pan, gst, catalogue")
    
    # Validate file extension (CSV for catalogue, images/PDF for others)
    if doc_type == DocumentType.CATALOGUE:
        allowed_extensions = {'.csv'}
    else:
        allowed_extensions = {'.jpg', '.jpeg', '.png', '.pdf'}
    
    file_extension = os.path.splitext(file.filename)[1].lower()
    if file_extension not in allowed_extensions:
        if doc_type == DocumentType.CATALOGUE:
            raise HTTPException(status_code=400, detail="Only CSV files allowed for catalogue")
        else:
            raise HTTPException(status_code=400, detail="Only JPG, PNG, PDF files allowed")
    
    # Check session exists
    vendor_draft = db.get_vendor_draft_by_session(session_id)
    if not vendor_draft:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Create temp session directory
    temp_session_dir = os.path.join(TEMP_UPLOAD_DIR, session_id)
    os.makedirs(temp_session_dir, exist_ok=True)
    
    # Save uploaded file temporarily
    temp_file_path = os.path.join(temp_session_dir, file.filename)
    with open(temp_file_path, "wb") as buffer:
        content = await file.read()
        buffer.write(content)
    
    uploaded_files = []
    
    # Handle PDF conversion (identical to email registration)
    if pdf_converter.is_pdf(temp_file_path):
        print(f"📄 PDF detected: {file.filename}, converting to images...")
        try:
            # Convert PDF to images
            converted_images = pdf_converter.convert_pdf_to_images(
                temp_file_path,
                output_format="png"
            )
            
            # Track each page
            for img_info in converted_images:
                img_filename = os.path.basename(img_info["path"])
                uploaded_files.append({
                    "type": doc_type.value,
                    "filename": img_filename,
                    "path": img_info["path"],
                    "page": img_info["page"],
                    "converted_from_pdf": True,
                    "uploaded_at": datetime.now().isoformat()
                })
            
            print(f"✅ Converted {len(converted_images)} pages from PDF")
            
        except Exception as pdf_error:
            print(f"⚠️ PDF conversion failed: {pdf_error}")
            # Fall back to keeping original PDF
            uploaded_files.append({
                "type": doc_type.value,
                "filename": file.filename,
                "path": temp_file_path,
                "uploaded_at": datetime.now().isoformat()
            })
    else:
        # Regular image file
        uploaded_files.append({
            "type": doc_type.value,
            "filename": file.filename,
            "path": temp_file_path,
            "uploaded_at": datetime.now().isoformat()
        })
    
    # Update vendor draft with temp file paths
    current_temp_docs = vendor_draft.temp_document_paths or []
    current_temp_docs.extend(uploaded_files)
    
    db.update_vendor_draft(vendor_draft.id, {
        "temp_document_paths": current_temp_docs
    })
    
    # Check which documents are uploaded
    doc_types_uploaded = set(d["type"] for d in current_temp_docs)
    
    # Determine next stage based on what's missing (use enum values: "aadhaar", "pan", "gst", "catalogue")
    has_aadhaar = "aadhaar" in doc_types_uploaded
    has_pan = "pan" in doc_types_uploaded
    has_gst = "gst" in doc_types_uploaded
    has_catalogue = "catalogue" in doc_types_uploaded
    
    print(f"DEBUG: Documents uploaded - Aadhaar: {has_aadhaar}, PAN: {has_pan}, GST: {has_gst}, Catalogue: {has_catalogue}")
    print(f"DEBUG: doc_types_uploaded set: {doc_types_uploaded}")
    
    # Update stage based on current document upload
    if not has_aadhaar:
        next_stage = ChatStage.AADHAAR_REQUEST
        next_message = "Please upload your Aadhaar card next."
    elif not has_pan:
        next_stage = ChatStage.PAN_REQUEST
        next_message = "Great! Aadhaar received. Now upload your PAN card."
    elif not has_gst:
        next_stage = ChatStage.GST_REQUEST
        next_message = "Excellent! PAN received. Now upload your GST certificate."
    elif not has_catalogue:
        next_stage = ChatStage.CATALOGUE_REQUEST
        next_message = "Perfect! GST received. Finally, upload your **product catalogue** (CSV file with your products/services)."
    else:
        # ALL FOUR documents uploaded - move to confirmation
        next_stage = ChatStage.AWAITING_CONFIRMATION
        next_message = "Perfect! All documents uploaded. Please review your information using /confirmation-summary endpoint, then call /confirm-and-submit to complete registration."
    
    db.update_vendor_draft(vendor_draft.id, {"chat_stage": next_stage})
    
    return {
        "success": True,
        "message": next_message,
        "document_uploaded": doc_type.value,
        "files_saved": len(uploaded_files),
        "pages": [f["page"] for f in uploaded_files if "page" in f] or [1],
        "documents_status": {
            "aadhaar": "✅" if has_aadhaar else "⏳",
            "pan": "✅" if has_pan else "⏳",
            "gst": "✅" if has_gst else "⏳",
            "catalogue": "✅" if has_catalogue else "⏳"
        },
        "next_stage": next_stage.value,
        "ready_for_confirmation": has_aadhaar and has_pan and has_gst
    }


@router.get("/confirmation-summary/{session_id}")
async def get_confirmation_summary(session_id: str):
    """
    Get complete data summary for vendor confirmation
    """
    vendor_draft = db.get_vendor_draft_by_session(session_id)
    if not vendor_draft:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if vendor_draft.chat_stage != ChatStage.AWAITING_CONFIRMATION:
        raise HTTPException(status_code=400, detail="Not ready for confirmation. Complete all steps first.")
    
    # Build summary
    basic_info = vendor_draft.basic_details.dict() if vendor_draft.basic_details else {}
    
    # Count documents by type (use enum values: "aadhaar", "pan", "gst")
    temp_docs = vendor_draft.temp_document_paths or []
    doc_counts = {
        "aadhaar": len([d for d in temp_docs if d["type"] == "aadhaar"]),
        "pan": len([d for d in temp_docs if d["type"] == "pan"]),
        "gst": len([d for d in temp_docs if d["type"] == "gst"])
    }
    
    summary = {
        "basic_info": basic_info,
        "documents_uploaded": doc_counts,
        "total_documents": len(temp_docs),
        "total_pages": sum(doc_counts.values())
    }
    
    return ConfirmationSummary(**summary)


@router.post("/confirm-and-submit", response_model=VendorCreationResponse)
async def confirm_and_submit_vendor(request: VendorConfirmationRequest):
    """
    STAGE 3: Vendor Record Creation (Identical to Email Registration)
    
    After vendor confirms data:
    1. Generate unique vendor_id
    2. Create vendor-isolated folder structure
    3. Move documents from temp to permanent storage
    4. Create MongoDB vendor record (status: ready_for_extraction)
    5. Trigger same batching/queue pipeline as email registration
    """
    
    if not request.confirmed:
        return VendorCreationResponse(
            success=False,
            vendor_id="",
            message="Confirmation declined. You can edit your information.",
            workspace_path="",
            documents_count=0,
            status="awaiting_confirmation"
        )
    
    # Get vendor draft
    vendor_draft = db.get_vendor_draft_by_session(request.session_id)
    if not vendor_draft:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if vendor_draft.chat_stage != ChatStage.AWAITING_CONFIRMATION:
        raise HTTPException(status_code=400, detail="Not ready for submission")
    
    # Extract email for vendor_id generation
    basic_info = vendor_draft.basic_details.dict() if vendor_draft.basic_details else {}
    vendor_email = basic_info.get("email_id", f"unknown_{request.session_id}")
    
    # Generate vendor_id (same format as email registration)
    vendor_count = db.get_vendors_collection().count_documents({}) + 1
    vendor_id = f"VENDOR_{vendor_count:04d}_{vendor_email.replace('@', '_').replace('.', '_')}"
    
    # Create vendor-isolated directory structure (IDENTICAL to email registration)
    vendor_base_path = os.path.join(VENDORS_BASE_PATH, vendor_id)
    paths = {
        "base": vendor_base_path,
        "documents": os.path.join(vendor_base_path, "documents"),
        "extracted": os.path.join(vendor_base_path, "extracted"),
        "metadata": os.path.join(vendor_base_path, "metadata.json"),
        "session_raw": os.path.join(vendor_base_path, "session_raw.json")
    }
    
    # Create directories
    os.makedirs(paths["documents"], exist_ok=True)
    os.makedirs(paths["extracted"], exist_ok=True)
    
    # Move documents from temp to permanent storage
    temp_docs = vendor_draft.temp_document_paths or []
    final_documents = []
    
    for temp_doc in temp_docs:
        temp_path = temp_doc["path"]
        if os.path.exists(temp_path):
            # Generate standard filename (matching email registration naming)
            doc_type = temp_doc["type"]
            filename = os.path.basename(temp_path)
            
            # If converted from PDF, keep page number in filename
            if temp_doc.get("converted_from_pdf"):
                final_filename = f"{doc_type}_page_{temp_doc['page']}.png"
            else:
                file_ext = os.path.splitext(filename)[1]
                final_filename = f"{doc_type}{file_ext}"
            
            final_path = os.path.join(paths["documents"], final_filename)
            
            # Move file
            shutil.move(temp_path, final_path)
            
            final_documents.append({
                "type": doc_type,
                "filename": final_filename,
                "path": final_path,
                "size": os.path.getsize(final_path),
                "downloaded_at": temp_doc["uploaded_at"],
                "converted_from_pdf": temp_doc.get("converted_from_pdf", False),
                "pdf_page": temp_doc.get("page")
            })
    
    # ========== IMMEDIATE CATALOGUE PROCESSING (Stage 2) ==========
    # Process catalogue CSV immediately (no batching/LLM needed)
    catalogue_result = None
    for doc in final_documents:
        if doc["type"] == "catalogue":
            print(f"📊 Processing catalogue for {vendor_id}...")
            catalogue_result = catalogue_processor.process_csv(doc["path"], vendor_id)
            catalogue_processor.save_to_extracted_folder(catalogue_result, vendor_id, vendor_base_path)
            print(f"✅ Catalogue processing complete: {catalogue_result['row_count']} products")
            break
    
    # Save metadata (matching email registration format)
    company_name = basic_info.get("company_name") or basic_info.get("full_name", "Unknown")
    metadata = {
        "vendor_id": vendor_id,
        "company_name": company_name,
        "basic_info": basic_info,
        "registration_source": "chatbot",
        "session_id": request.session_id,
        "created_at": datetime.now().isoformat()
    }
    
    with open(paths["metadata"], 'w') as f:
        json.dump(metadata, f, indent=2)
    
    # Save session raw data
    chat_history = db.get_chat_history(request.session_id)
    session_data = {
        "session_id": request.session_id,
        "chat_history": [
            {
                "sender": msg.sender,
                "message": msg.message,
                "timestamp": msg.timestamp.isoformat() if hasattr(msg.timestamp, 'isoformat') else str(msg.timestamp)
            }
            for msg in chat_history
        ],
        "basic_details": basic_info,
        "documents": final_documents,
        "created_at": metadata["created_at"]
    }
    
    with open(paths["session_raw"], 'w') as f:
        json.dump(session_data, f, indent=2)
    
    # Create MongoDB vendor record (IDENTICAL schema to email registration)
    vendor_record = {
        "vendor_id": vendor_id,
        "company_name": metadata["company_name"],
        "basic_info": {
            "name": basic_info.get("full_name"),
            "age": str(basic_info.get("age", "")),  # Store as string like email registration
            "gender": basic_info.get("gender"),
            "role": basic_info.get("designation"),
            "mobile": basic_info.get("mobile_number"),
            "email": basic_info.get("email_id"),
            "company_name": metadata["company_name"]
        },
        "email_metadata": {
            "email_id": request.session_id,  # Use session_id as identifier
            "subject": f"Chatbot Registration - {metadata['company_name']}",
            "sender": basic_info.get("email_id"),
            "received_at": int(datetime.now().timestamp())  # Unix timestamp
        },
        "documents": final_documents,
        "workspace_path": paths["base"],
        "status": "ready_for_extraction",  # Same status as email registration
        "registration_source": "chatbot",
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
    
    # Insert into MongoDB vendors collection
    try:
        vendors_collection = db.get_vendors_collection()
        result = vendors_collection.insert_one(vendor_record)
        print(f"✅ MongoDB Insert Successful:")
        print(f"   Inserted ID: {result.inserted_id}")
        print(f"   Vendor ID: {vendor_id}")
        print(f"   Status: {vendor_record['status']}")
        print(f"   Registration Source: {vendor_record['registration_source']}")
    except Exception as e:
        print(f"❌ MongoDB Insert Failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save vendor to MongoDB: {str(e)}")
    
    # Update vendor draft status
    db.update_vendor_draft(vendor_draft.id, {
        "chat_stage": ChatStage.CONFIRMED,
        "is_completed": True
    })
    
    # Clean up temp directory
    temp_session_dir = os.path.join(TEMP_UPLOAD_DIR, request.session_id)
    if os.path.exists(temp_session_dir):
        shutil.rmtree(temp_session_dir)
    
    # TODO: Trigger batching/queue pipeline (Stage 4)
    # This will be handled by the existing Node.js queue service
    # The vendor is now in "ready_for_extraction" status
    # Next: Node.js continuous batching picks this up (every 10 vendors or 5 min timer)
    
    return VendorCreationResponse(
        success=True,
        vendor_id=vendor_id,
        message=f"Registration complete! Your vendor ID is {vendor_id}. Documents are being processed.",
        workspace_path=paths["base"],
        documents_count=len(final_documents),
        status="ready_for_extraction"
    )


@router.post("/start", response_model=ChatResponse, operation_id="start_chat_enhanced")
async def start_chat():
    """Start new vendor registration session with proper introduction"""
    session_id = str(uuid.uuid4())
    
    vendor_draft = VendorDraftModel(
        session_id=session_id,
        chat_stage=ChatStage.WELCOME,  # Start with WELCOME, not collecting
        basic_details=BasicDetailsData(),
        temp_document_paths=[]
    )
    db.create_vendor_draft(vendor_draft)
    
    welcome_message = """Hello! 👋 Welcome to our Vendor Registration System.

I'm here to help you complete your registration. This process involves:
1. Collecting your basic information (name, contact details, etc.)
2. Uploading 3 important documents (Aadhaar, PAN, GST)
3. Reviewing and confirming all details before final submission

The whole process takes about 5-10 minutes.

**May I start with your vendor registration?** (Please type 'yes' to begin)"""
    
    bot_message = ChatMessage(
        session_id=session_id,
        message=welcome_message,
        sender="bot"
    )
    db.save_chat_message(bot_message)
    
    return ChatResponse(
        message=welcome_message,
        stage=ChatStage.WELCOME,
        requires_document=False,
        session_id=session_id
    )


def normalize_gender(raw_value: str) -> str:
    """Normalize gender input to standard 'Male' or 'Female'"""
    normalized = raw_value.lower().strip()
    
    male_variations = ['m', 'male', 'man', 'boy', 'gentleman', 'he', 'him']
    female_variations = ['f', 'female', 'woman', 'girl', 'lady', 'she', 'her']
    
    if normalized in male_variations:
        return "Male"
    elif normalized in female_variations:
        return "Female"
    else:
        return None  # Invalid input


def normalize_designation(raw_value: str) -> str:
    """Normalize designation to standard formats"""
    normalized = raw_value.lower().strip()
    
    # Mapping of common variations to standard format
    designation_map = {
        'owner': 'Owner',
        'proprietor': 'Proprietor',
        'founder': 'Founder',
        'co-founder': 'Co-Founder',
        'cofounder': 'Co-Founder',
        'ceo': 'CEO',
        'director': 'Director',
        'manager': 'Manager',
        'partner': 'Partner',
        'executive': 'Executive',
    }
    
    # Try exact match first
    if normalized in designation_map:
        return designation_map[normalized]
    
    # Try partial match
    for key, value in designation_map.items():
        if key in normalized:
            return value
    
    # Default: capitalize first letter
    return raw_value.strip().title()


@router.post("/message/{session_id}", response_model=ChatResponse, operation_id="send_message_enhanced")
async def send_message(session_id: str, message_data: MessageRequest):
    """
    SMART message handler with:
    1. Proper data extraction and normalization
    2. Retry on failure (doesn't skip fields)
    3. Only summarizes after ALL stages complete
    4. Allows editing before final submission
    """
    user_message = message_data.message.strip()
    
    vendor_draft = db.get_vendor_draft_by_session(session_id)
    if not vendor_draft:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Save user message
    user_chat_message = ChatMessage(
        session_id=session_id,
        message=user_message,
        sender="user"
    )
    db.save_chat_message(user_chat_message)
    
    current_stage = vendor_draft.chat_stage
    current_details = vendor_draft.basic_details.dict() if vendor_draft.basic_details else {}
    
    print(f"DEBUG: Current stage: {current_stage}, User message: '{user_message}'")
    
    # ============ STAGE 0: WELCOME ============
    if current_stage == ChatStage.WELCOME:
        if any(word in user_message.lower() for word in ['yes', 'yeah', 'sure', 'ok', 'okay', 'start', 'begin']):
            # User agreed, move to basic details
            db.update_vendor_draft(vendor_draft.id, {"chat_stage": ChatStage.COLLECTING_BASIC_DETAILS})
            response_message = "Excellent! Let's start with your basic information.\n\n**What is your full name?**"
        else:
            response_message = "I understand you might have questions. Please type 'yes' when you're ready to begin the registration process, or ask me any questions you have."
        
        bot_message = ChatMessage(session_id=session_id, message=response_message, sender="bot")
        db.save_chat_message(bot_message)
        
        return ChatResponse(
            message=response_message,
            stage=vendor_draft.chat_stage if current_stage == ChatStage.WELCOME else ChatStage.COLLECTING_BASIC_DETAILS,
            requires_document=False,
            session_id=session_id
        )
    
    # ============ STAGE 1: COLLECTING BASIC DETAILS ============
    if current_stage == ChatStage.COLLECTING_BASIC_DETAILS:
        # Use LLM to extract information
        extraction_result = await chat_handler.extract_basic_detail_with_llm(user_message, current_details)
        updates = extraction_result.get("updates", {})
        
        print(f"DEBUG: Extraction result: {extraction_result}")
        print(f"DEBUG: Current details BEFORE update: {current_details}")
        
        # Apply normalization AFTER extraction
        if updates:
            # Normalize gender
            if 'gender' in updates and updates['gender']:
                normalized_gender = normalize_gender(str(updates['gender']))
                if normalized_gender:
                    updates['gender'] = normalized_gender
                    print(f"DEBUG: Normalized gender '{updates.get('gender')}' → '{normalized_gender}'")
                else:
                    # Invalid gender input - remove from updates
                    print(f"DEBUG: Invalid gender input: '{updates['gender']}', will ask again")
                    del updates['gender']
            
            # Normalize designation
            if 'designation' in updates and updates['designation']:
                updates['designation'] = normalize_designation(str(updates['designation']))
                print(f"DEBUG: Normalized designation to: '{updates['designation']}'")
            
            # Update current details
            current_details.update(updates)
            # Convert to dict for JSON storage
            db.update_vendor_draft(vendor_draft.id, {"basic_details": current_details})
            print(f"DEBUG: Updated details AFTER normalization: {current_details}")
        
        # Define required fields in order
        required_fields = ['full_name', 'company_name', 'designation', 'age', 'gender', 'mobile_number', 'email_id']
        
        # Find FIRST missing field
        missing_field = None
        for field in required_fields:
            if not current_details.get(field):
                missing_field = field
                break
        
        print(f"DEBUG: Missing field: {missing_field}")
        print(f"DEBUG: All fields status: {[(f, current_details.get(f)) for f in required_fields]}")
        
        if missing_field:
            # Still missing a field - ask for it SPECIFICALLY
            field_prompts = {
                'full_name': "What is your full name?",
                'company_name': "What is your company name?",
                'designation': "What is your designation/role? (e.g., Owner, Founder, Manager)",
                'age': "What is your age?",
                'gender': "What is your gender? (Male/Female or M/F)",
                'mobile_number': "What is your mobile number? (10 digits)",
                'email_id': "What is your email address?"
            }
            
            # Check if we just tried to get this field but failed
            if updates and missing_field == 'gender' and 'gender' not in current_details:
                response_message = f"I didn't quite understand that. Could you please specify your gender as either **Male** or **Female**? (You can also type M or F)"
            else:
                response_message = field_prompts.get(missing_field, f"Please provide your {missing_field}")
            
            bot_message = ChatMessage(session_id=session_id, message=response_message, sender="bot")
            db.save_chat_message(bot_message)
            
            return ChatResponse(
                message=response_message,
                stage=ChatStage.COLLECTING_BASIC_DETAILS,
                requires_document=False,
                session_id=session_id,
                extracted_data=current_details
            )
        else:
            # ALL basic details collected! Move to document upload
            db.update_vendor_draft(vendor_draft.id, {"chat_stage": ChatStage.AADHAAR_REQUEST})
            response_message = """Perfect! ✅ I have all your basic information.

Now, let's proceed to document uploads. I'll need 4 documents from you:
1. **Aadhaar Card** (next)
2. PAN Card
3. GST Certificate
4. Product Catalogue (CSV file)

Please upload your **Aadhaar card** now. You can upload JPG, PNG, or PDF (multi-page supported)."""
            
            bot_message = ChatMessage(session_id=session_id, message=response_message, sender="bot")
            db.save_chat_message(bot_message)
            
            return ChatResponse(
                message=response_message,
                stage=ChatStage.AADHAAR_REQUEST,
                requires_document=True,
                session_id=session_id,
                extracted_data=current_details
            )
    
    # ============ STAGE 2: WAITING FOR DOCUMENTS ============
    if current_stage in [ChatStage.AADHAAR_REQUEST, ChatStage.PAN_REQUEST, ChatStage.GST_REQUEST]:
        response_message = "Please upload your document. I'm waiting for your file upload."
        
        bot_message = ChatMessage(session_id=session_id, message=response_message, sender="bot")
        db.save_chat_message(bot_message)
        
        return ChatResponse(
            message=response_message,
            stage=current_stage,
            requires_document=True,
            session_id=session_id
        )
    
    # ============ STAGE 3: AWAITING CONFIRMATION ============
    if current_stage == ChatStage.AWAITING_CONFIRMATION:
        user_msg_lower = user_message.lower()
        
        # Check if user wants to confirm
        if "confirm" in user_msg_lower and not any(word in user_msg_lower for word in ["edit", "change", "modify"]):
            response_message = """Great! Your registration is confirmed. 

Please call the **/confirm-and-submit** endpoint to finalize your registration and create your vendor account."""
        
        # SMART EDIT: Try to detect and apply edits directly
        elif any(word in user_msg_lower for word in ["edit", "change", "modify", "update"]):
            # Extract what field and new value using LLM
            edit_prompt = f"""
User wants to edit their information. Extract the field and new value.

Current data: {json.dumps(current_details, indent=2)}

User message: "{user_message}"

FIELD MAPPING:
- name/full_name → "full_name"
- designation/role/job → "designation"
- age → "age"
- gender → "gender"
- mobile/phone/number → "mobile_number"
- email/mail → "email_id"

Return JSON:
{{
  "field": "field_name or null",
  "new_value": "extracted_value or null",
  "understood": true/false
}}

Examples:
- "change email to an@gmail.com" → {{"field": "email_id", "new_value": "an@gmail.com", "understood": true}}
- "edit name" → {{"field": "full_name", "new_value": null, "understood": false}}
- "update age to 25" → {{"field": "age", "new_value": 25, "understood": true}}
- "change mobile to 1234567890" → {{"field": "mobile_number", "new_value": "1234567890", "understood": true}}
"""
            
            try:
                from openai import OpenAI
                client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
                edit_response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[{"role": "user", "content": edit_prompt}],
                    max_tokens=200,
                    temperature=0.1,
                    response_format={"type": "json_object"}
                )
                edit_result = json.loads(edit_response.choices[0].message.content)
                
                print(f"DEBUG: Edit extraction result: {edit_result}")
                
                if edit_result.get("understood") and edit_result.get("field") and edit_result.get("new_value"):
                    # Apply the edit with normalization
                    field = edit_result["field"]
                    new_value = edit_result["new_value"]
                    
                    # Apply normalization
                    if field == "gender":
                        normalized = normalize_gender(str(new_value))
                        if normalized:
                            new_value = normalized
                    elif field == "designation":
                        new_value = normalize_designation(str(new_value))
                    
                    # Update the field
                    current_details[field] = new_value
                    db.update_vendor_draft(vendor_draft.id, {"basic_details": current_details})
                    
                    field_display = {
                        "full_name": "name",
                        "designation": "designation",
                        "age": "age",
                        "gender": "gender",
                        "mobile_number": "mobile number",
                        "email_id": "email"
                    }
                    
                    response_message = f"""✅ Updated! Your {field_display.get(field, field)} has been changed to **{new_value}**.

Your updated information:
- Name: {current_details.get('full_name')}
- Designation: {current_details.get('designation')}
- Age: {current_details.get('age')}
- Gender: {current_details.get('gender')}
- Mobile: {current_details.get('mobile_number')}
- Email: {current_details.get('email_id')}

Type **CONFIRM** to submit, or make more changes."""
                
                else:
                    # Couldn't understand - ask for clarification
                    response_message = """I'm not sure what you'd like to change. Please be specific:

Examples:
- "change email to newemail@gmail.com"
- "update age to 30"
- "edit name to John Smith"
- "change mobile to 9876543210"

What would you like to edit?"""
            
            except Exception as e:
                print(f"ERROR: Edit extraction failed: {e}")
                response_message = """Sorry, I couldn't process that edit. Please try again with:
- "change [field] to [new value]"

Example: "change email to newemail@gmail.com" """
        
        else:
            response_message = """Please review your information carefully.

To proceed:
- Type **"CONFIRM"** to finalize and submit your registration
- Type **"EDIT"** if you want to change any information

You can also call:
- GET `/confirmation-summary` to see all your data
- POST `/confirm-and-submit` with `{"session_id": "...", "confirmed": true}` to complete registration"""
        
        bot_message = ChatMessage(session_id=session_id, message=response_message, sender="bot")
        db.save_chat_message(bot_message)
        
        return ChatResponse(
            message=response_message,
            stage=ChatStage.AWAITING_CONFIRMATION,
            requires_document=False,
            session_id=session_id,
            extracted_data=db.get_extracted_vendor_data(session_id)
        )
    
    # ============ DEFAULT RESPONSE ============
    response_message = "I'm not sure how to help with that. Please follow the registration flow."
    
    bot_message = ChatMessage(session_id=session_id, message=response_message, sender="bot")
    db.save_chat_message(bot_message)
    
    return ChatResponse(
        message=response_message,
        stage=current_stage,
        requires_document=False,
        session_id=session_id
    )


@router.get("/history/{session_id}")
async def get_chat_history_endpoint(session_id: str):
    """Get complete chat history"""
    history = db.get_chat_history(session_id)
    return {
        "session_id": session_id,
        "messages": [msg.dict() for msg in history],
        "total_messages": len(history)
    }
