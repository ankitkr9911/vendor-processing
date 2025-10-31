from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from enum import Enum

class DocumentType(str, Enum):
    AADHAAR = "aadhaar"
    PAN = "pan"
    GST = "gst"

class BasicDetailsData(BaseModel):
    full_name: Optional[str] = None
    designation: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    mobile_number: Optional[str] = None
    email_id: Optional[str] = None

class ParseStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class ChatStage(str, Enum):
    WELCOME = "welcome"
    COLLECTING_BASIC_DETAILS = "collecting_basic_details"  # Add this
    AADHAAR_REQUEST = "aadhaar_request"
    AADHAAR_PROCESSING = "aadhaar_processing"
    PAN_REQUEST = "pan_request"
    PAN_PROCESSING = "pan_processing"
    GST_REQUEST = "gst_request"
    GST_PROCESSING = "gst_processing"
    COMPLETED = "completed"

class AadhaarData(BaseModel):
    name: Optional[str] = None
    aadhaar_number: Optional[str] = None
    father_name: Optional[str] = None
    dob: Optional[str] = None
    gender: Optional[str] = None
    address: Optional[str] = None
    confidence: Optional[float] = None

class PANData(BaseModel):
    name: Optional[str] = None
    pan_number: Optional[str] = None
    father_name: Optional[str] = None
    dob: Optional[str] = None
    confidence: Optional[float] = None

class GSTData(BaseModel):
    gstin: Optional[str] = None
    business_name: Optional[str] = None
    trade_name: Optional[str] = None
    address: Optional[str] = None
    state_code: Optional[str] = None
    state: Optional[str] = None
    registration_type: Optional[str] = None
    date_of_registration: Optional[str] = None
    constitution_of_business: Optional[str] = None
    taxpayer_type: Optional[str] = None
    confidence: Optional[float] = None

class DocumentModel(BaseModel):
    id: str = Field(default_factory=lambda: str(datetime.now().timestamp()))
    session_id: str
    document_type: DocumentType
    filename: str
    s3_key: Optional[str] = None
    parse_status: ParseStatus = ParseStatus.PENDING
    parsed_data: Optional[Dict[str, Any]] = None
    parse_confidence: Optional[float] = None
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

class VendorDraftModel(BaseModel):
    id: str = Field(default_factory=lambda: str(datetime.now().timestamp()))
    session_id: str
    chat_stage: ChatStage = ChatStage.WELCOME
    basic_details: Optional[BasicDetailsData] = None  # Add this line
    aadhaar_data: Optional[AadhaarData] = None
    pan_data: Optional[PANData] = None
    gst_data: Optional[GSTData] = None
    documents: List[str] = Field(default_factory=list)
    is_completed: bool = False
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

class ChatMessage(BaseModel):
    session_id: str
    message: str
    sender: str  # "user" or "bot"
    timestamp: datetime = Field(default_factory=datetime.now)
    metadata: Optional[Dict[str, Any]] = None

class ChatResponse(BaseModel):
    message: str
    stage: ChatStage
    requires_document: bool = False
    document_type: Optional[DocumentType] = None
    session_id: str
    extracted_data: Optional[Dict[str, Any]] = None

# Additional API Response Models for Frontend Integration
class APIResponse(BaseModel):
    """Standard API response wrapper"""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)

class SessionStatus(BaseModel):
    """Session status response"""
    session_id: str
    current_stage: ChatStage
    is_completed: bool
    progress_percentage: float = Field(description="Registration completion percentage")
    extracted_data: Dict[str, Any]

class DocumentUploadResponse(BaseModel):
    """Document upload response"""
    document_id: str
    session_id: str
    document_type: DocumentType
    filename: str
    status: ParseStatus
    message: str

class ExtractedDataResponse(BaseModel):
    """Extracted data response"""
    session_id: str
    basic_details: Optional[BasicDetailsData] = None
    aadhaar_data: Optional[AadhaarData] = None
    pan_data: Optional[PANData] = None
    gst_data: Optional[GSTData] = None
    completion_status: Dict[str, bool] = Field(description="Which sections are completed")

class ChatHistoryResponse(BaseModel):
    """Chat history response"""
    session_id: str
    messages: List[Dict[str, Any]]
    total_messages: int

class TTSResponse(BaseModel):
    """Text-to-speech response"""
    audio: str = Field(description="Base64 encoded audio data")
    voice: str
    text_length: int

class MessageRequest(BaseModel):
    """Message request model"""
    message: str = Field(..., description="User message text", min_length=1)
    
class TTSRequest(BaseModel):
    """Text-to-speech request model"""
    text: str = Field(..., description="Text to convert to speech", min_length=1)
    voice: Optional[str] = Field("nova", description="Voice to use for TTS")