from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List
import uuid
from datetime import datetime
import os
from openai import OpenAI
import json

from models import (
    ChatResponse, ChatMessage, VendorDraftModel, 
    ChatStage, DocumentType, AadhaarData, PANData, GSTData,
    BasicDetailsData, APIResponse, SessionStatus, ChatHistoryResponse, TTSResponse,
    MessageRequest, TTSRequest
)
from database import db
from services.tts_service import TTSService

router = APIRouter(prefix="/api/v1/chat", tags=["Chat Management"])
tts_service = TTSService()

class ChatHandler:
    """Handles chat flow and responses using OpenAI"""
    
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.stage_contexts = {
            ChatStage.WELCOME: {
                "requires_document": False,
                "context": "You are a helpful vendor registration assistant. Greet the vendor warmly and let them know you'll collect some basic details first before proceeding with document verification."
            },
            ChatStage.COLLECTING_BASIC_DETAILS: {
                "requires_document": False,
                "context": """You are an intelligent data extraction assistant collecting vendor registration details step by step.

CRITICAL INSTRUCTIONS:
1. From user messages, extract ONLY the relevant data value, not the entire sentence
2. Handle corrections and updates when users want to change information
3. Be smart - extract meaningful info from conversational responses

EXTRACTION RULES:
- Name: Extract proper name format (e.g., "Hi I am ankit kumar" → "Ankit Kumar")  
- Age: Extract just the number (e.g., "I am 25 years old" → 25)
- Designation: Extract job title (e.g., "I work as a manager" → "Manager")
- Gender: Extract M/F/Male/Female (normalize to standard format)
- Mobile: Extract 10-digit number only
- Email: Extract valid email address only

CORRECTION HANDLING:
- If user says "change name to X" or "update my age to Y", extract the new value
- Always acknowledge corrections: "I've updated your [field] to [new_value]"

Ask for missing information in a conversational way. Once all 6 fields are complete, proceed to document verification."""
            },
            ChatStage.AADHAAR_REQUEST: {
                "requires_document": True,
                "document_type": DocumentType.AADHAAR,
                "context": "Ask for the Aadhaar card if not provided. Be polite and explain that you need a clear image."
            },
            ChatStage.AADHAAR_PROCESSING: {
                "requires_document": False,
                "context": "Inform that you're processing their Aadhaar card and ask them to wait."
            },
            ChatStage.PAN_REQUEST: {
                "requires_document": True,
                "document_type": DocumentType.PAN,
                "context": "Thank them for the Aadhaar card and ask for their PAN card."
            },
            ChatStage.PAN_PROCESSING: {
                "requires_document": False,
                "context": "Inform that you're processing their PAN card and ask them to wait."
            },
            ChatStage.GST_REQUEST: {
                "requires_document": True,
                "document_type": DocumentType.GST,
                "context": "Thank them for the PAN card and ask for their GST certificate."
            },
            ChatStage.GST_PROCESSING: {
                "requires_document": False,
                "context": "Inform that you're processing their GST certificate and ask them to wait."
            },
            ChatStage.COMPLETED: {
                "requires_document": False,
                "context": "Thank them and provide a summary of the extracted information. Mention that their registration is complete."
            }
        }
    
    async def get_chat_completion(self, 
        messages: List[Dict[str, str]], 
        context: str,
        extracted_data: Dict[str, Any] = None,
        allow_correction: bool = True
    ) -> Dict[str, Any]:
        """Get chat completion from OpenAI with correction capability"""
        
        data_summary = ""
        if extracted_data:
            data_summary = "\n\nCurrent stored data:\n"
            if extracted_data.get('basic_details'):
                data_summary += f"Basic Details: {json.dumps(extracted_data['basic_details'], indent=2)}\n"
            if extracted_data.get('aadhaar_data'):
                data_summary += f"Aadhaar Data: {json.dumps(extracted_data['aadhaar_data'], indent=2)}\n"
            if extracted_data.get('pan_data'):
                data_summary += f"PAN Data: {json.dumps(extracted_data['pan_data'], indent=2)}\n"
            if extracted_data.get('gst_data'):
                data_summary += f"GST Data: {json.dumps(extracted_data['gst_data'], indent=2)}\n"
        
        correction_instructions = ""
        if allow_correction:
            correction_instructions = """
CRITICAL DATA HANDLING INSTRUCTIONS:

1. DATA EXTRACTION: Always extract clean, properly formatted values:
   - Names: Proper case (e.g., "Ankit Kumar" not "HI I am ankit kumar")
   - Ages: Numbers only (e.g., 25 not "25 years")
   - Mobile: 10 digits only (e.g., "9876543210")
   - Email: Valid email format only

2. CORRECTIONS: If user wants to update information:
   - Detect phrases like: "change to", "update to", "correct to", "should be"
   - Extract the NEW clean value from their message
   - Return JSON with correction:
   {
     "message": "I've updated your [field] to [new_clean_value].",
     "correction": {
       "category": "basic_details|aadhaar_data|pan_data|gst_data",
       "field": "field_name", 
       "new_value": "properly_formatted_new_value"
     }
   }

3. NORMAL DATA COLLECTION: When collecting new info, extract clean values and return:
   {
     "message": "conversational response asking for next field or acknowledging current"
   }

Examples:
- User: "change name to Ankit Kumar" → new_value: "Ankit Kumar" (proper case)
- User: "Hi I am john doe" → extract: "John Doe" (proper case)
- User: "I am 25 years old" → extract: 25 (number only)
"""
        
        system_message = {
            "role": "system",
            "content": f"""You are a helpful vendor registration assistant. {context}
{data_summary}
{correction_instructions}

Keep responses concise, professional, and focused on the registration task.
Be attentive to correction requests and handle them accurately.
"""
        }

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[system_message] + messages,
                max_tokens=300,
                temperature=0.7,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            return result
            
        except Exception as e:
            print(f"OpenAI API error: {e}")
            return {
                "message": "I apologize, but I'm having trouble processing your request. Please try again."
            }
        
    async def get_response(self, 
        stage: ChatStage, 
        message_history: List[ChatMessage] = None, 
        extracted_data: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Get appropriate response based on current stage"""
        stage_info = self.stage_contexts[stage].copy()
        
        # Convert ALL message history to OpenAI format (no limit)
        messages = []
        if message_history:
            messages = [
                {"role": "user" if msg.sender == "user" else "assistant", "content": msg.message}
                for msg in message_history
            ]
        
        # Get AI response with full context
        ai_response = await self.get_chat_completion(
            messages=messages,
            context=stage_info["context"],
            extracted_data=extracted_data,
            allow_correction=True
        )
        
        stage_info["message"] = ai_response.get("message", "")
        stage_info["correction"] = ai_response.get("correction")
        
        return stage_info
    
    async def extract_basic_detail_with_llm(self, message: str, current_details: Dict[str, Any]) -> Dict[str, Any]:
        """Use LLM to intelligently extract and update basic details"""
        
        # Find what's missing
        required_fields = ['full_name', 'designation', 'age', 'gender', 'mobile_number', 'email_id']
        missing_fields = [f for f in required_fields if not current_details.get(f)]
        
        extraction_prompt = f"""
You are a data extraction AI. Extract relevant information from the user message.

Current data: {json.dumps(current_details, indent=2)}
Missing fields: {missing_fields}

User message: "{message}"

EXTRACTION RULES:
- If user is providing new information for missing fields, extract it cleanly
- If user is correcting existing information, identify what to update
- Format names in proper case (e.g., "Ankit Kumar" not "ankit kumar")
- Extract ages as numbers only
- Extract mobile numbers as 10-digit strings
- Normalize gender to "Male"/"Female"
- Extract email addresses in lowercase

Return JSON with extracted/updated fields:
{{
  "updates": {{
    "field_name": "clean_extracted_value"
  }},
  "is_correction": true/false
}}

Examples:
- "Hi I am ankit kumar" → {{"updates": {{"full_name": "Ankit Kumar"}}, "is_correction": false}}
- "Change my name to John Smith" → {{"updates": {{"full_name": "John Smith"}}, "is_correction": true}}
- "I am 25 years old" → {{"updates": {{"age": 25}}, "is_correction": false}}
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
            return result
            
        except Exception as e:
            print(f"LLM extraction error: {e}")
            return {"updates": {}, "is_correction": False}

chat_handler = ChatHandler()

@router.post("/start", response_model=ChatResponse)
async def start_chat():
    """
    Start New Registration Session
    
    Creates a new vendor registration session and returns the session ID along with
    the initial greeting message from the AI assistant.
    
    Returns:
        ChatResponse: Contains welcome message, session ID, and initial stage info
    """
    session_id = str(uuid.uuid4())
    
    # Create initial vendor draft with basic details stage
    vendor_draft = VendorDraftModel(
        session_id=session_id,
        chat_stage=ChatStage.COLLECTING_BASIC_DETAILS,
        basic_details=BasicDetailsData()
    )
    db.create_vendor_draft(vendor_draft)
    
    # Get AI response for welcome message
    response_data = await chat_handler.get_response(ChatStage.COLLECTING_BASIC_DETAILS)
    
    # Save welcome message
    bot_message = ChatMessage(
        session_id=session_id,
        message=response_data["message"],
        sender="bot"
    )
    db.save_chat_message(bot_message)
    
    return ChatResponse(
        message=response_data["message"],
        stage=ChatStage.COLLECTING_BASIC_DETAILS,
        requires_document=False,
        session_id=session_id
    )

@router.post("/message/{session_id}", response_model=ChatResponse)
async def send_message(session_id: str, message_data: MessageRequest):
    """
    Send Message in Chat Flow
    
    Send a user message in the registration chat flow. The API will process the message
    based on the current stage (basic info collection, document requests, etc.) and
    return appropriate responses.
    
    Args:
        session_id: Unique session identifier from /start endpoint
        message_data: JSON object containing the user's message
        
    Returns:
        ChatResponse: AI response with updated stage and document requirements
    """
    user_message = message_data.message.strip()
    
    vendor_draft = db.get_vendor_draft_by_session(session_id)
    if not vendor_draft:
        raise HTTPException(status_code=404, detail="Chat session not found")
    
    # Get FULL chat history (no limit)
    chat_history = db.get_chat_history(session_id)
    
    # Save user message
    user_chat_message = ChatMessage(
        session_id=session_id,
        message=user_message,
        sender="user"
    )
    db.save_chat_message(user_chat_message)
    chat_history.append(user_chat_message)
    
    # Get extracted data for full context
    extracted_data = db.get_extracted_vendor_data(session_id)
    
    # Check for data retrieval requests
    show_data_keywords = ['show', 'display', 'information', 'data', 'details', 'collected', 'summary']
    if any(keyword in user_message.lower() for keyword in show_data_keywords):
        # Handle data display request
        summary_message = "Here's the information I have collected so far:\n\n"
        
        if extracted_data.get('basic_details'):
            basic = extracted_data['basic_details']
            summary_message += "**Basic Details:**\n"
            if basic.get('full_name'): summary_message += f"• Name: {basic['full_name']}\n"
            if basic.get('designation'): summary_message += f"• Designation: {basic['designation']}\n"
            if basic.get('age'): summary_message += f"• Age: {basic['age']}\n"
            if basic.get('gender'): summary_message += f"• Gender: {basic['gender']}\n"
            if basic.get('mobile_number'): summary_message += f"• Mobile: {basic['mobile_number']}\n"
            if basic.get('email_id'): summary_message += f"• Email: {basic['email_id']}\n"
        
        if extracted_data.get('aadhaar_data'):
            aadhaar = extracted_data['aadhaar_data']
            summary_message += "\n**Aadhaar Details:**\n"
            if aadhaar.get('name'): summary_message += f"• Name: {aadhaar['name']}\n"
            if aadhaar.get('aadhaar_number'): summary_message += f"• Aadhaar: ****{aadhaar['aadhaar_number'][-4:]}\n"
        
        if extracted_data.get('pan_data'):
            pan = extracted_data['pan_data']
            summary_message += "\n**PAN Details:**\n"
            if pan.get('name'): summary_message += f"• Name: {pan['name']}\n"
            if pan.get('pan_number'): summary_message += f"• PAN: {pan['pan_number']}\n"
        
        if extracted_data.get('gst_data'):
            gst = extracted_data['gst_data']
            summary_message += "\n**GST Details:**\n"
            if gst.get('business_name'): summary_message += f"• Business: {gst['business_name']}\n"
            if gst.get('gstin'): summary_message += f"• GSTIN: {gst['gstin']}\n"
        
        response_data = {
            "message": summary_message,
            "requires_document": vendor_draft.chat_stage in [ChatStage.AADHAAR_REQUEST, ChatStage.PAN_REQUEST, ChatStage.GST_REQUEST],
            "document_type": chat_handler.stage_contexts.get(vendor_draft.chat_stage, {}).get("document_type")
        }
    else:
        # Get AI response with full context
        response_data = await chat_handler.get_response(
            stage=vendor_draft.chat_stage,
            message_history=chat_history,
            extracted_data=extracted_data
        )
    
    # Handle corrections if detected
    if response_data.get("correction"):
        correction = response_data["correction"]
        category = correction.get("category")
        field = correction.get("field")
        new_value = correction.get("new_value")
        
        if category and field and new_value is not None:
            # Update the appropriate data category
            if category == "basic_details":
                current_details = vendor_draft.basic_details.dict() if vendor_draft.basic_details else {}
                current_details[field] = new_value
                db.update_vendor_draft(vendor_draft.id, {"basic_details": current_details})
            elif category == "aadhaar_data" and vendor_draft.aadhaar_data:
                aadhaar_dict = vendor_draft.aadhaar_data.dict()
                aadhaar_dict[field] = new_value
                db.update_vendor_draft(vendor_draft.id, {"aadhaar_data": aadhaar_dict})
            elif category == "pan_data" and vendor_draft.pan_data:
                pan_dict = vendor_draft.pan_data.dict()
                pan_dict[field] = new_value
                db.update_vendor_draft(vendor_draft.id, {"pan_data": pan_dict})
            elif category == "gst_data" and vendor_draft.gst_data:
                gst_dict = vendor_draft.gst_data.dict()
                gst_dict[field] = new_value
                db.update_vendor_draft(vendor_draft.id, {"gst_data": gst_dict})
    
    # Handle basic details collection with intelligent LLM extraction
    if vendor_draft.chat_stage == ChatStage.COLLECTING_BASIC_DETAILS and not response_data.get("correction"):
        current_details = vendor_draft.basic_details.dict() if vendor_draft.basic_details else {}
        print(f"DEBUG: Current details before extraction: {current_details}")
        
        # Use LLM for intelligent extraction
        extraction_result = await chat_handler.extract_basic_detail_with_llm(user_message, current_details)
        print(f"DEBUG: LLM extraction result: {extraction_result}")
        
        # Apply updates from LLM extraction
        updates = extraction_result.get("updates", {})
        if updates:
            current_details.update(updates)
            db.update_vendor_draft(vendor_draft.id, {"basic_details": current_details})
            print(f"DEBUG: Updated details: {current_details}")
        
        # Check if all details are collected
        required_fields = ['full_name', 'designation', 'age', 'gender', 'mobile_number', 'email_id']
        all_collected = all(current_details.get(f) is not None and current_details.get(f) != '' for f in required_fields)
        print(f"DEBUG: All collected check: {all_collected}")
        print(f"DEBUG: Required fields status: {[(f, current_details.get(f)) for f in required_fields]}")
        
        if all_collected:
            print("DEBUG: All details collected, moving to AADHAAR_REQUEST")
            # Move to document collection
            db.update_vendor_draft(vendor_draft.id, {"chat_stage": ChatStage.AADHAAR_REQUEST})
            vendor_draft.chat_stage = ChatStage.AADHAAR_REQUEST
            # Get new response for Aadhaar request stage
            response_data = await chat_handler.get_response(
                stage=ChatStage.AADHAAR_REQUEST,
                message_history=chat_history,
                extracted_data=extracted_data
            )
            print("DEBUG: Got new response for AADHAAR_REQUEST")
    
    # Save bot response
    bot_message = ChatMessage(
        session_id=session_id,
        message=response_data["message"],
        sender="bot"
    )
    db.save_chat_message(bot_message)
    
    return ChatResponse(
        message=response_data["message"],
        stage=vendor_draft.chat_stage,
        requires_document=response_data["requires_document"],
        document_type=response_data.get("document_type"),
        session_id=session_id
    )

@router.get("/history/{session_id}", response_model=Dict[str, Any])
async def get_chat_history(session_id: str):
    """
    Get Chat History
    
    Retrieve the complete conversation history for a registration session.
    
    Args:
        session_id: Unique session identifier
        
    Returns:
        Dict containing array of all chat messages with timestamps and senders
    """
    try:
        history = db.get_chat_history(session_id)
        return {
            "session_id": session_id,
            "messages": [msg.dict() for msg in history],
            "total_messages": len(history)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get chat history: {str(e)}")

@router.get("/status/{session_id}", response_model=Dict[str, Any])
async def get_chat_status(session_id: str):
    """
    Get Session Status
    
    Get current registration progress, stage information, and all extracted data
    for a session.
    
    Args:
        session_id: Unique session identifier
        
    Returns:
        Dict containing session status, current stage, and extracted data
    """
    try:
        vendor_draft = db.get_vendor_draft_by_session(session_id)
        if not vendor_draft:
            raise HTTPException(status_code=404, detail="Chat session not found")
        
        extracted_data = db.get_extracted_vendor_data(session_id)
        
        # Calculate progress percentage
        stages_completed = 0
        total_stages = 8  # basic_details + 3 documents + processing stages
        
        if extracted_data.get('basic_details'):
            basic = extracted_data['basic_details']
            required_fields = ['full_name', 'designation', 'age', 'gender', 'mobile_number', 'email_id']
            if all(basic.get(f) for f in required_fields):
                stages_completed += 2
                
        if extracted_data.get('aadhaar_data'):
            stages_completed += 2
        if extracted_data.get('pan_data'):
            stages_completed += 2  
        if extracted_data.get('gst_data'):
            stages_completed += 2
            
        progress_percentage = (stages_completed / total_stages) * 100
        
        return {
            "session_id": session_id,
            "current_stage": vendor_draft.chat_stage,
            "is_completed": vendor_draft.is_completed,
            "progress_percentage": round(progress_percentage, 1),
            "extracted_data": extracted_data
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get chat status: {str(e)}")

@router.post("/tts", response_model=TTSResponse)
async def text_to_speech(tts_request: TTSRequest):
    """
    Text-to-Speech Conversion
    
    Convert text to speech audio using OpenAI's TTS API. Returns base64 encoded
    audio data that can be played directly in the browser.
    
    Args:
        text_data: JSON object with 'text' and optional 'voice' parameter
        
    Returns:
        Dict containing base64 encoded audio data and metadata
    """
    try:
        audio_base64 = tts_service.text_to_speech(tts_request.text, tts_request.voice)
        return TTSResponse(
            audio=audio_base64,
            voice=tts_request.voice,
            text_length=len(tts_request.text)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to convert text to speech: {str(e)}")