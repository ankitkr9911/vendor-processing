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
    
    def get_vendor_draft_by_email(self, email: str) -> Optional[VendorDraftModel]:
        """Get vendor draft by email from basic_details"""
        data = self._load_json(self.vendor_drafts_file)
        for draft_data in data.values():
            basic_details = draft_data.get('basic_details', {})
            if basic_details and basic_details.get('email_id') == email:
                return VendorDraftModel(**draft_data)
        return None
    
    def get_vendor_draft_by_vendor_id(self, vendor_id: str) -> Optional[VendorDraftModel]:
        """Get vendor draft by vendor_id - checks MongoDB only"""
        if self.mongo_db is not None:
            vendors_collection = self.get_vendors_collection()
            mongo_vendor = vendors_collection.find_one({"vendor_id": vendor_id})
            
            if mongo_vendor:
                # Convert MongoDB vendor to VendorDraftModel format
                from models import BasicDetailsData, ChatStage
                
                basic_info = mongo_vendor.get('basic_info', {})
                
                # Get session_id from top level first, fallback to email_metadata
                session_id = mongo_vendor.get('session_id') or mongo_vendor.get('email_metadata', {}).get('email_id', 'completed_session')
                
                draft_model = VendorDraftModel(
                    session_id=session_id,
                    vendor_id=vendor_id,
                    chat_stage=ChatStage.CONFIRMED,
                    basic_details=BasicDetailsData(
                        company_name=mongo_vendor.get('company_name'),
                        business_category=basic_info.get('business_category'),
                        industry_segment=basic_info.get('industry_segment'),
                        city=basic_info.get('city'),
                        country=basic_info.get('country'),
                        contact_person=basic_info.get('name'),
                        age=basic_info.get('age'),
                        gender=basic_info.get('gender'),
                        designation=basic_info.get('designation'),
                        mobile_number=basic_info.get('mobile'),
                        email_id=basic_info.get('email')
                    ),
                    is_completed=True
                )
                return draft_model
        
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
    
    def get_catalogues_collection(self):
        """Get MongoDB catalogues collection for AI-processed catalogue data"""
        if self.mongo_db is None:
            raise Exception("MongoDB not configured. Set MONGO_URI environment variable.")
        return self.mongo_db["catalogues"]
    
    def get_products_collection(self):
        """Get MongoDB products collection for individual product data"""
        if self.mongo_db is None:
            raise Exception("MongoDB not configured. Set MONGO_URI environment variable.")
        return self.mongo_db["products"]
    
    def save_catalogue_to_mongodb(self, catalogue_data: dict):
        """
        Save catalogue data to MongoDB catalogues collection
        
        Schema:
        {
            "catalogue_id": "CAT_VENDOR_0001_20240101",
            "vendor_id": "VENDOR_0001",
            "company_name": "Company Name",
            "ai_summary": "AI-generated summary...",
            "pages": [
                {"page_number": 1, "items": ["PROD_001", "PROD_002"], "item_count": 50}
            ],
            "total_products": 100,
            "total_pages": 2,
            "processed_at": "2024-01-01T12:00:00",
            "csv_filename": "catalogue.csv"
        }
        """
        try:
            catalogues_collection = self.get_catalogues_collection()
            
            # Remove products array (stored separately)
            products = catalogue_data.pop('products', [])
            
            # Insert catalogue metadata
            result = catalogues_collection.insert_one(catalogue_data)
            print(f"✅ Catalogue saved to MongoDB: {catalogue_data['catalogue_id']}")
            
            # Save products separately
            if products:
                self.save_products_to_mongodb(products)
            
            return result.inserted_id
            
        except Exception as e:
            print(f"❌ Failed to save catalogue to MongoDB: {e}")
            raise
    
    def save_products_to_mongodb(self, products: list):
        """
        Save product data to MongoDB products collection
        
        Schema for each product:
        {
            "product_id": "PROD_VENDOR_0001_0001",
            "vendor_id": "VENDOR_0001",
            "catalogue_id": "CAT_VENDOR_0001_20240101",
            "name": "Product Name",
            "category": "Category",
            "price": "1000",
            "unit": "piece",
            "specifications": {...},
            "description": "Product description",
            "raw_data": {...}
        }
        """
        try:
            if not products:
                return
            
            products_collection = self.get_products_collection()
            
            # Bulk insert products
            result = products_collection.insert_many(products)
            print(f"✅ {len(products)} products saved to MongoDB")
            
            return result.inserted_ids
            
        except Exception as e:
            print(f"❌ Failed to save products to MongoDB: {e}")
            raise

# Global database instance
db = JSONDatabase()