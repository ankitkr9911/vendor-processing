import os
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from models import VendorDraftModel, DocumentModel, ChatMessage
from pymongo import MongoClient

class JSONDatabase:
    """Simple JSON file-based database for development with MongoDB access"""
    
    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        
        # Initialize files
        self.vendor_drafts_file = os.path.join(data_dir, "vendor_drafts.json")
        self.documents_file = os.path.join(data_dir, "documents.json")
        self.chat_messages_file = os.path.join(data_dir, "chat_messages.json")
        
        # Create empty files if they don't exist
        for file_path in [self.vendor_drafts_file, self.documents_file, self.chat_messages_file]:
            if not os.path.exists(file_path):
                with open(file_path, 'w') as f:
                    json.dump({}, f)
        
        # MongoDB connection for vendor records (production)
        mongo_uri = os.getenv("MONGO_URI")
        if mongo_uri:
            print(f"🔗 Connecting to MongoDB...")
            print(f"   URI: {mongo_uri[:30]}...{mongo_uri[-20:]}")
            self.mongo_client = MongoClient(mongo_uri)
            self.mongo_db = self.mongo_client.get_database()
            print(f"✅ MongoDB connected!")
            print(f"   Database: {self.mongo_db.name}")
            print(f"   Collections: {self.mongo_db.list_collection_names()}")
        else:
            self.mongo_client = None
            self.mongo_db = None
            print("⚠️ Warning: MONGO_URI not set. MongoDB features disabled.")
    
    def _load_json(self, file_path: str) -> Dict[str, Any]:
        """Load JSON data from file"""
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
    
    def _save_json(self, file_path: str, data: Dict[str, Any]):
        """Save JSON data to file"""
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2, default=str)
    
    # Vendor Draft operations
    def create_vendor_draft(self, vendor_draft: VendorDraftModel) -> str:
        """Create a new vendor draft"""
        data = self._load_json(self.vendor_drafts_file)
        data[vendor_draft.id] = vendor_draft.dict()
        self._save_json(self.vendor_drafts_file, data)
        return vendor_draft.id
    
    def get_vendor_draft(self, draft_id: str) -> Optional[VendorDraftModel]:
        """Get vendor draft by ID"""
        data = self._load_json(self.vendor_drafts_file)
        if draft_id in data:
            return VendorDraftModel(**data[draft_id])
        return None
    
    def get_vendor_draft_by_session(self, session_id: str) -> Optional[VendorDraftModel]:
        """Get vendor draft by session ID"""
        data = self._load_json(self.vendor_drafts_file)
        for draft_data in data.values():
            if draft_data.get('session_id') == session_id:
                return VendorDraftModel(**draft_data)
        return None
    
    def update_vendor_draft(self, draft_id: str, updates: Dict[str, Any]) -> bool:
        """Update vendor draft"""
        data = self._load_json(self.vendor_drafts_file)
        if draft_id in data:
            data[draft_id].update(updates)
            data[draft_id]['updated_at'] = datetime.now().isoformat()
            self._save_json(self.vendor_drafts_file, data)
            return True
        return False
    
    # Document operations
    def create_document(self, document: DocumentModel) -> str:
        """Create a new document"""
        data = self._load_json(self.documents_file)
        data[document.id] = document.dict()
        self._save_json(self.documents_file, data)
        return document.id
    
    def get_document(self, document_id: str) -> Optional[DocumentModel]:
        """Get document by ID"""
        data = self._load_json(self.documents_file)
        if document_id in data:
            return DocumentModel(**data[document_id])
        return None
    
    def update_document(self, document_id: str, updates: Dict[str, Any]) -> bool:
        """Update document"""
        data = self._load_json(self.documents_file)
        if document_id in data:
            data[document_id].update(updates)
            data[document_id]['updated_at'] = datetime.now().isoformat()
            self._save_json(self.documents_file, data)
            return True
        return False
    
    def get_documents_by_session(self, session_id: str) -> List[DocumentModel]:
        """Get all documents for a session"""
        data = self._load_json(self.documents_file)
        documents = []
        for doc_data in data.values():
            if doc_data.get('session_id') == session_id:
                documents.append(DocumentModel(**doc_data))
        return documents
    
    # Chat message operations
    def save_chat_message(self, message: ChatMessage) -> str:
        """Save a chat message"""
        data = self._load_json(self.chat_messages_file)
        message_id = f"{message.session_id}_{len(data)}"
        message_data = message.dict()
        message_data['id'] = message_id
        data[message_id] = message_data
        self._save_json(self.chat_messages_file, data)
        return message_id
    
    def get_chat_history(self, session_id: str, limit: int = 50) -> List[ChatMessage]:
        """Get chat history for a session"""
        data = self._load_json(self.chat_messages_file)
        messages = []
        for msg_data in data.values():
            if msg_data.get('session_id') == session_id:
                messages.append(ChatMessage(**msg_data))
        
        # Sort by timestamp and limit
        messages.sort(key=lambda x: x.timestamp)
        return messages[-limit:]
    
    # Utility methods
    def get_extracted_vendor_data(self, session_id: str) -> Dict[str, Any]:
        """Get all extracted vendor data for a session"""
        vendor_draft = self.get_vendor_draft_by_session(session_id)
        if not vendor_draft:
            return {}
        
        result = {
            "session_id": session_id,
            "basic_details": vendor_draft.basic_details.dict() if vendor_draft.basic_details else None,  # Add this
            "aadhaar_data": vendor_draft.aadhaar_data.dict() if vendor_draft.aadhaar_data else None,
            "pan_data": vendor_draft.pan_data.dict() if vendor_draft.pan_data else None,
            "gst_data": vendor_draft.gst_data.dict() if vendor_draft.gst_data else None,
            "documents": vendor_draft.documents,
            "is_completed": vendor_draft.is_completed,
            "created_at": vendor_draft.created_at.isoformat(),
            "updated_at": vendor_draft.updated_at.isoformat()
        }
        
        return result
    
    def get_vendors_collection(self):
        """Get MongoDB vendors collection for chatbot registration"""
        if self.mongo_db is None:  # ✅ Correct way to check MongoDB database object
            raise Exception("MongoDB not configured. Set MONGO_URI environment variable.")
        return self.mongo_db["vendors"]

# Global database instance
db = JSONDatabase()