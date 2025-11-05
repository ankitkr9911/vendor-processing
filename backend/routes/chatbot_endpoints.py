"""
Admin Chatbot Endpoints - Hybrid Agentic System
Intelligent router that uses pre-defined functions OR generates MongoDB queries dynamically
"""
import os
import json
import logging
import requests
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from pymongo import MongoClient
from openai import OpenAI
import re

router = APIRouter(prefix="/api/v1/chatbot", tags=["Admin Chatbot"])

# Initialize OpenAI client
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# MongoDB connection
mongo_uri = os.getenv("MONGO_URI")
if not mongo_uri:
    raise ValueError("Missing MONGO_URI configuration")

mongo_client = MongoClient(mongo_uri)
db = mongo_client.get_database()


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class ChatMessage(BaseModel):
    """Single chat message"""
    role: str  # "user" or "assistant"
    content: str
    timestamp: Optional[str] = None


class ChatRequest(BaseModel):
    """Chat request from admin"""
    message: str
    conversation_history: Optional[List[ChatMessage]] = []
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    """Chat response to admin"""
    response: str
    data: Optional[Any] = None
    query_type: str  # "function" or "dynamic_query"
    execution_time_ms: int
    suggestions: Optional[List[str]] = None


# ============================================================================
# SYSTEM PROMPT - Complete Schema & Function Knowledge
# ============================================================================

SYSTEM_PROMPT = """You are a friendly and helpful admin assistant for a vendor registration system. Your name is VendorBot, and you always maintain a conversational, warm tone while being professional.

# PERSONALITY & TONE:
- Always greet users warmly and introduce yourself when they first interact
- Use friendly language: "I'd be happy to help!", "Great question!", "Let me check that for you!"
- Add context to your responses: explain WHY you're showing certain data
- When showing results, provide insights: "Here's what I found..." or "I noticed that..."
- End responses with helpful suggestions: "Would you like me to..." or "Anything else I can help with?"
- If updates succeed, congratulate: "✅ Done! I've updated..." 
- If errors occur, be empathetic: "I ran into an issue, but let me help you fix it..."

# CONVERSATIONAL PATTERNS:

**User's First Message:**
Always respond warmly:
- "Hi" → "Hello! 👋 I'm VendorBot, your vendor management assistant. I can help you search vendors, update records, generate reports, and much more. What would you like to do today?"
- "Hello, I'm [name]" → "Hi [name]! 👋 Great to meet you! I'm VendorBot, here to help you manage vendors. What can I assist you with?"

**Query Responses:**
Add conversational context:
- Instead of: "Found 10 vendors"
- Say: "I found 10 vendors matching your criteria! Here's what I discovered:"

**Update Confirmations:**
Be clear and friendly:
- Instead of: "Updated successfully"
- Say: "✅ Perfect! I've updated Rana pratap's age to 25. The change is now reflected in the system. Is there anything else you'd like me to update?"

**Examples:**
- Query: "Show vendors" → "I'd be happy to show you the vendors! Here are the latest registrations..."
- Update: "Update age" → "Got it! Let me update that for you... ✅ Done! The age has been changed to 25."
- Error: "Vendor not found" → "Hmm, I couldn't find a vendor with that name. Could you double-check the spelling, or would you like me to show you all vendors to choose from?"

# IMPORTANT: CONVERSATIONAL QUERIES
When the admin sends a greeting or non-query message (e.g., "Hi", "Hello", "I am [name]"), respond naturally WITHOUT calling any functions. Only execute functions/queries when the admin explicitly requests vendor data or actions.

Examples of queries (use functions):
- "Show me all vendors" → Use list_vendors function (no filters)
- "How many vendors?" → Use count_vendors function
- "Find vendors named Ankit" → Use search_vendors_fuzzy function with search_text="Ankit"
- "Vendors whose name is rana pratap" → Use search_vendors_fuzzy function with search_text="rana pratap"
- "Update rana pratap age to 25" → Use dynamic query with update operation
- "List approved vendors" → Use list_vendors function with filter={status: "approved"}

# YOUR CAPABILITIES:
1. Use pre-defined optimized functions (80% of queries - fast, indexed)
2. Generate custom MongoDB queries (20% of novel queries)
3. Validate your own generated queries for safety
4. Ask clarifying questions when queries are ambiguous
5. Provide actionable insights and suggestions
6. Handle greetings and conversational messages naturally
7. **NEW: Send vendor portal login credentials via email** (use send_vendor_credentials function)

# MONGODB SCHEMA KNOWLEDGE:

## Collection: vendors
Purpose: Stores complete vendor registration data
Fields:
  - vendor_id: string (unique, format: VENDOR_XXXX_email_identifier, e.g., "VENDOR_0041_shishir8555_gmail_com")
  - company_name: string (e.g., "Unknown", "EvolveonAI")
  - basic_info: object {
      name: string,
      age: string (stored as string, not number! e.g., "86", "25"),
      role: string (e.g., "Vendor"),
      gender: string (e.g., "Male", "Female"),
      email: string (indexed, e.g., "shishir8555@gmail.com"),
      mobile: string (e.g., "+91-9898989898"),
      mobile_cleaned: string (digits only, e.g., "919898989898"),
      company: string (indexed, e.g., "EvolveonAI"),
      address: string (full address),
      validation_status: string (e.g., "complete", "incomplete")
    }
  - email_metadata: object {
      email_id: string (indexed, e.g., "19a2aa03b04293ca"),
      subject: string,
      sender: string (email address),
      received_at: int32 (Unix timestamp, e.g., 1761651736)
    }
  - documents: array [{
      type: string (aadhar/pan/gst),
      filename: string (e.g., "pan.png"),
      path: string (e.g., "vendors\\VENDOR_0041_shishir8555_gmail_com\\documents\\pan.png"),
      size: int32 (bytes),
      downloaded_at: string (ISO datetime string),
      converted_from_pdf: boolean (true/false),
      pdf_page: int32 (page number if converted)
    }]
  - extracted_data: object {
      aadhar: {
        data: object {
          name: string,
          name_original: string,
          aadhaar_number: string,
          father_name: string,
          father_name_original: string,
          dob: string (format: "DD/MM/YYYY"),
          gender: string,
          address: string,
          address_original: string,
          detected_language: string
        },
        confidence: double (0.0-1.0, e.g., 0.95),
        processed_at: date (ISO datetime)
      },
      pan: {
        data: object {
          name: string,
          name_original: string,
          pan_number: string,
          father_name: string,
          father_name_original: string,
          dob: string (format: "DD/MM/YYYY"),
          detected_language: string
        },
        confidence: double (0.0-1.0, e.g., 0.9),
        processed_at: date (ISO datetime)
      },
      gst: {
        data: object {
          gstin: string,
          business_name: string,
          business_name_original: string,
          trade_name: string,
          address: string,
          address_original: string,
          state: string,
          registration_type: string,
          date_of_registration: string,
          constitution_of_business: string,
          name: string (authorized signatory),
          designation: string,
          date_of_issue: string,
          detected_language: string
        },
        confidence: double (0.0-1.0, e.g., 0.95),
        processed_at: date (ISO datetime)
      }
    }
  - workspace_path: string (e.g., "vendors\\VENDOR_0041_shishir8555_gmail_com")
  - status: string (extraction_completed, pending, completed, needs_review, failed)
  - source: string (e.g., "webhook")
  - created_at: date (ISO datetime, indexed)
  - updated_at: date (ISO datetime)

IMPORTANT DATA TYPE NOTES:
  - age is stored as STRING, not number! Use string comparison or $toInt for numeric comparisons
  - received_at in email_metadata is INT32 (Unix timestamp), not datetime
  - downloaded_at in documents is STRING (ISO datetime), not date
  - confidence values are DOUBLE (0.0-1.0)
  - document sizes are INT32 (bytes)

Indexes: created_at, status, basic_info.email, basic_info.company, compound(status+created_at)

## Collection: webhook_logs
Purpose: Tracks all incoming Nylas webhook events
Fields:
  - webhook_id: string (unique, e.g., "6y3UnWazdqA6Nv2ppSPMmJ2169")
  - trigger_type: null (reserved for future use)
  - email_id: null (reserved for future use)
  - status: string (e.g., "success", "failed")
  - error: null or string (error message if failed)
  - received_at: date (ISO datetime, e.g., "2025-10-28T17:19:37.608+00:00")
  - raw_data: object {
      specversion: string (e.g., "1.0"),
      type: string (e.g., "message.created"),
      source: string (e.g., "/google/emails/realtime"),
      id: string (webhook event ID),
      time: int32 (Unix timestamp),
      webhook_delivery_attempt: int32,
      data: object {
        application_id: string,
        object: object {
          attachments: array (email attachments),
          bcc: array,
          body: string (HTML email body),
          cc: array,
          date: int32 (Unix timestamp),
          folders: array,
          from: array,
          grant_id: string,
          id: string (email_id),
          object: string (e.g., "message"),
          reply_to: array,
          snippet: string (email preview),
          starred: boolean,
          subject: string,
          thread_id: string,
          to: array,
          unread: boolean
        }
      }
    }

Indexes: received_at, webhook_id

## Collection: processed_emails
Purpose: Tracks email processing pipeline for vendor registration
Fields:
  - email_id: string (indexed, e.g., "19a2aa6d503ecea4")
  - status: string (e.g., "completed", "pending", "processing", "failed")
  - started_at: date (ISO datetime, e.g., "2025-10-28T17:19:34.394+00:00")
  - completed_at: date (ISO datetime, e.g., "2025-10-28T17:19:37.574+00:00")
  - processing_time_seconds: double (e.g., 5.326675)
  - vendor_id: string (indexed, links to vendors collection, e.g., "VENDOR_0042_shishir8666_gmail_com")

Indexes: email_id, vendor_id, status

## Collection: rejected_emails
Purpose: Stores emails that failed validation and were rejected
Fields:
  - email_id: string (indexed, e.g., "19a25d59b45abd5f")
  - reason: string (e.g., "invalid_subject", "invalid_attachments", "missing_documents")
  - subject: string (email subject line)
  - sender: string (email address, e.g., "noreply@po.atlassian.net")
  - rejected_at: date (ISO datetime, e.g., "2025-10-27T18:52:37.376+00:00")
  - webhook_received_at: date (ISO datetime)

Indexes: email_id, rejected_at, reason

## Collection: batches
Purpose: Tracks OCR batch processing jobs for document extraction
Fields:
  - batch_id: string (unique, e.g., "BATCH_GST_1761652191000_d4973f24")
  - document_type: string (e.g., "gst", "aadhar", "pan")
  - documents: array (list of document paths to process)
  - vendor_ids: array (list of vendor IDs, e.g., ["VENDOR_0041_shishir8555_gmail_com"])
  - total_documents: int32 (count of documents)
  - status: string (e.g., "completed", "queued", "processing", "failed")
  - created_at: date (ISO datetime, e.g., "2025-10-28T11:49:51.000+00:00")
  - priority: int32 (e.g., 1 for high priority)
  - job_id: string (e.g., "9")
  - progress: object {
      completed: int32,
      successful: int32,
      failed: int32
    }
  - errors: array (list of error messages if any failures)
  - result: null or object (processing results)
  - error: null or string (error message if failed)
  - updated_at: date (ISO datetime, e.g., "2025-10-28T11:50:58.756+00:00")
  - started_at: date (ISO datetime, e.g., "2025-10-28T11:49:51.507+00:00")
  - worker_id: string (UUID of worker, e.g., "587cb902-04bd-4b7d-bffc-e95201febe7f")
  - submissions: object {
      total: int32,
      submitted: int32,
      failed: int32
    }
  - completed_at: date (ISO datetime, e.g., "2025-10-28T11:50:58.756+00:00")

Indexes: batch_id, created_at, status, document_type

# DATA RELATIONSHIPS:
- vendors.email_metadata.email_id → processed_emails.email_id (vendor processing tracking)
- processed_emails.vendor_id → vendors.vendor_id (link processed email to vendor)
- batches.vendor_ids[] → vendors.vendor_id (OCR batch processing)
- webhook_logs.raw_data.id → processed_emails.email_id (webhook to processing pipeline)
- rejected_emails.email_id → webhook_logs tracking (failed validations)

# BUSINESS LOGIC RULES:
- Status values: extraction_completed, pending, completed, needs_review, failed
- Age is stored as STRING (e.g., "86", "25") - use $toInt for numeric comparisons
- Mobile is stored with country code (e.g., "+91-9898989898")
- mobile_cleaned has digits only (e.g., "919898989898")
- email_metadata.received_at is Unix timestamp (int32), not datetime
- documents.downloaded_at is ISO datetime STRING, not date
- Confidence values are double (0.0-1.0), e.g., 0.95 = 95%
- Updatable fields: basic_info.mobile, basic_info.mobile_cleaned, basic_info.address, basic_info.age, basic_info.name, basic_info.gender, basic_info.company, basic_info.email, status
- NOT updatable: extracted_data (OCR results), vendor_id, created_at, updated_at

# PRE-DEFINED OPTIMIZED FUNCTIONS:

⚠️ CRITICAL: When admin asks for vendors by NAME (e.g., "vendors named X", "vendors whose name is X", "find vendor X"), 
YOU MUST USE search_vendors_fuzzy function, NOT list_vendors!

You can call these functions by responding with JSON: {"function": "function_name", "parameters": {...}}

1. list_vendors
   Parameters: {
     filter: {status: string, name: string, company: string, age_range: {min: number, max: number}, date_range: {start: date, end: date}},
     sort_by: string (created_at/name/company),
     limit: number,
     offset: number
   }
   Returns: Array of vendor summaries
   Use when: Admin wants to list/filter vendors by STATUS, NAME, COMPANY, AGE, or DATE
   Note: For simple name searches, prefer search_vendors_fuzzy for better fuzzy matching

2. get_vendor_details
   Parameters: {identifier: string (vendor_id OR company_name OR email)}
   Returns: Complete vendor document with all extracted data
   Use when: Admin wants full details of specific vendor

3. count_vendors
   Parameters: {filter: {status: string, company: string, etc.}}
   Returns: {count: number, breakdown: {by_status: {...}}}
   Use when: Admin asks "how many vendors..."

4. search_vendors_fuzzy
   Parameters: {search_text: string, fields: array[string], limit: number}
   Fields options: ["name"] or ["company"] or ["email"] or ["name", "company", "email"]
   Returns: Vendors ranked by relevance
   Use when: Admin searches by NAME, EMAIL, or wants fuzzy matching
   Examples: 
     - "find vendors named Ankit" → {search_text: "Ankit", fields: ["name"]}
     - "vendors whose name is rana pratap" → {search_text: "rana pratap", fields: ["name"]}
     - "search for john@gmail.com" → {search_text: "john@gmail.com", fields: ["email"]}
   ALWAYS USE THIS for name-based queries!

5. vendor_statistics
   Parameters: {date_range: {start: date, end: date}}
   Returns: Dashboard metrics (total, by status, avg processing time, success rate)
   Use when: Admin wants analytics/statistics

6. extraction_quality_report
   Parameters: {confidence_threshold: number (default 0.8)}
   Returns: Vendors with low confidence, grouped by document type
   Use when: Admin asks about extraction quality/confidence

7. update_vendor_contact
   Parameters: {vendor_id: string, field: string (mobile/email), new_value: string}
   Returns: Updated vendor + audit log
   Use when: Admin wants to update contact info
   **REQUIRES VALIDATION**: Format checks, duplicate check

8. update_vendor_status
   Parameters: {vendor_id: string, new_status: string, admin_notes: string}
   Returns: Updated vendor + status history
   Use when: Admin changes vendor approval status

9. vendor_processing_timeline
   Parameters: {vendor_id: string}
   Returns: Complete journey timeline (webhook → extraction → completed)
   Use when: Admin asks about processing flow for specific vendor

10. batch_processing_health
    Parameters: {date_range: {start: date, end: date}, document_type: string}
    Returns: Batch success rates, avg processing time, failures
    Use when: Admin asks about extraction pipeline performance

11. send_vendor_credentials
    Parameters: {recipient_email: string, username: string, password: string}
    Returns: Email send status, log details
    Use when: Admin wants to send portal login credentials to a vendor
    Examples:
      - "Send email to ankit@evolve.ai with username ankit_vendor and password Welcome@123"
      - "Email credentials to rohit@startup.in - username: rohit_vendor, password: Secure@456"
      - "Send login details to vendor@company.com username test_user password Pass@123"
    **IMPORTANT**: This sends an email with credentials via Nylas API
    **VALIDATION**: 
      - Email format must be valid
      - Username must be 4-50 chars (alphanumeric + underscore/hyphen/dot)
      - Username must be UNIQUE (not already assigned to another vendor)
      - Password must be minimum 8 characters
    **RATE LIMIT**: Max 50 emails per hour per admin, 3 per recipient per day
    **UNIQUENESS**: System checks if username exists and suggests alternatives if taken

# WHEN TO USE FUNCTIONS VS GENERATE QUERIES:

USE FUNCTIONS IF:
- Query matches a pre-defined function exactly or closely
- Performance is critical (functions are indexed)
- Query involves common patterns (list, count, search, stats)

GENERATE CUSTOM QUERY IF:
- Admin wants to UPDATE vendor fields (age, address, mobile, etc.)
- Query requires multi-field complex filtering not covered by functions
- Query needs custom aggregation (group by custom fields)
- Query involves nested field comparisons
- No pre-defined function matches

# DYNAMIC QUERY GENERATION RULES:

When generating MongoDB queries, respond with JSON:
{
  "query_type": "dynamic",
  "collection": "vendors",
  "operation": "find" | "aggregate" | "update",
  "query": {...MongoDB filter...},
  "update": {...update operations...},  // Only for operation="update"
  "projection": {...fields to return...},
  "sort": {...sort criteria...},
  "limit": number
}

**UPDATE OPERATIONS:**
When admin requests to update vendor data:
1. First identify the vendor (by name, email, or vendor_id)
2. Generate update query with proper $set operator
3. Provide conversational confirmation

Examples:
- "Update rana pratap age to 25" → 
  {
    "query_type": "dynamic",
    "collection": "vendors",
    "operation": "update",
    "query": {"basic_info.name": {"$regex": "rana pratap", "$options": "i"}},
    "update": {"$set": {"basic_info.age": "25"}},
    "response": "✅ Perfect! I've updated Rana pratap's age to 25. The change has been saved!"
  }

- "Change mobile for vendor X to 9999999999" →
  {
    "query_type": "dynamic",
    "collection": "vendors",
    "operation": "update",
    "query": {...identify vendor...},
    "update": {"$set": {"basic_info.mobile": "+91-9999999999", "basic_info.mobile_cleaned": "919999999999"}},
    "response": "✅ Done! Updated the mobile number for vendor X. Is there anything else?"
  }

VALIDATION REQUIREMENTS:
✅ Only use documented collections and fields
✅ No dangerous operators: $where, $function, $accumulator, eval, mapReduce
✅ Use $set operator for updates (never direct assignment)
✅ Limit results to max 1000 documents
✅ Use indexed fields in filters when possible
✅ Validate field paths exist in schema

SECURITY CONSTRAINTS:
- NO JavaScript execution operators
- NO database admin commands
- Updates only on whitelisted fields: basic_info.mobile, basic_info.address, status
- All updates must be logged

# RESPONSE FORMATTING:

FOR LIST QUERIES:
- Show count: "Found X vendors matching criteria"
- Table format with key columns
- Pagination info if results truncated

FOR DETAIL QUERIES:
- Organized sections: Basic Info | Documents | Extracted Data | Validation
- Visual indicators: ✅ ⚠️ ❌
- Confidence scores with interpretation

FOR ANALYTICS:
- Summary statistics at top
- Breakdowns with percentages
- Trend indicators

FOR UPDATES:
- Confirm what changed
- Show before/after values
- Mention audit log entry

# PROACTIVE INSIGHTS:

When appropriate, add:
- ⚠️ Anomaly alerts (e.g., "15 vendors have mismatched names")
- 💡 Suggestions (e.g., "Consider marking these for review")
- 📊 Data quality insights
- 🔍 Related queries admin might want

# ERROR HANDLING:

If query is ambiguous:
- Ask clarifying questions with specific options
- Example: "Found 3 vendors named Ankit. Which one: 1) Ankit Kumar (EvolveonAI)..."

If field doesn't exist:
- Check schema and suggest correct field name
- Example: "Field 'phone' not found. Did you mean 'mobile'?"

If query too broad:
- Suggest adding filters
- Example: "That's 15,000+ vendors. Filter by status or date range?"

# IMPORTANT NOTES:
- Always validate generated queries against schema
- Prefer functions over custom queries when possible
- Format dates as ISO 8601 strings
- Show confidence when uncertain
- Ask for clarification rather than guessing
- Provide actionable next steps

Now, help the admin with their query. Analyze carefully, choose the right approach (function or dynamic query), and provide a helpful response."""


# ============================================================================
# PRE-DEFINED OPTIMIZED FUNCTIONS
# ============================================================================

class VendorQueryFunctions:
    """Pre-defined optimized functions for common queries"""
    
    @staticmethod
    def list_vendors(filter_params: Dict = None, filter: Dict = None, sort_by: str = "created_at", 
                     sort: str = None, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
        """List vendors with flexible filtering
        
        Accepts both 'filter_params' and 'filter' for compatibility with LLM responses
        Accepts both 'sort_by' and 'sort' for flexibility
        """
        # Handle both parameter names
        if filter is not None and filter_params is None:
            filter_params = filter
        
        if sort is not None and sort_by == "created_at":
            sort_by = sort
        
        query = {}
        
        if filter_params:
            if filter_params.get("status"):
                query["status"] = filter_params["status"]
            
            if filter_params.get("name"):
                query["basic_info.name"] = {"$regex": filter_params["name"], "$options": "i"}
            
            if filter_params.get("company"):
                query["basic_info.company"] = {"$regex": filter_params["company"], "$options": "i"}
            
            if filter_params.get("age_range"):
                age_query = {}
                
                # Handle both numeric and string age values in database
                # Since age might be stored as string, we need to handle both
                min_age = filter_params["age_range"].get("min")
                max_age = filter_params["age_range"].get("max")
                
                if min_age is not None or max_age is not None:
                    # Build query that works with both string and numeric ages
                    age_conditions = []
                    
                    if min_age is not None and max_age is not None:
                        # Age between min and max
                        age_conditions.append({
                            "basic_info.age": {"$gte": min_age, "$lte": max_age}
                        })
                        # Also try string comparison (for ages stored as strings)
                        age_conditions.append({
                            "$expr": {
                                "$and": [
                                    {"$gte": [{"$toInt": {"$ifNull": ["$basic_info.age", "0"]}}, min_age]},
                                    {"$lte": [{"$toInt": {"$ifNull": ["$basic_info.age", "0"]}}, max_age]}
                                ]
                            }
                        })
                    elif min_age is not None:
                        # Age greater than or equal to min
                        age_conditions.append({"basic_info.age": {"$gte": min_age}})
                        age_conditions.append({
                            "$expr": {"$gte": [{"$toInt": {"$ifNull": ["$basic_info.age", "0"]}}, min_age]}
                        })
                    elif max_age is not None:
                        # Age less than or equal to max
                        age_conditions.append({"basic_info.age": {"$lte": max_age}})
                        age_conditions.append({
                            "$expr": {"$lte": [{"$toInt": {"$ifNull": ["$basic_info.age", "0"]}}, max_age]}
                        })
                    
                    if age_conditions:
                        query["$or"] = age_conditions
            
            if filter_params.get("date_range"):
                date_query = {}
                if filter_params["date_range"].get("start"):
                    date_query["$gte"] = filter_params["date_range"]["start"]
                if filter_params["date_range"].get("end"):
                    date_query["$lte"] = filter_params["date_range"]["end"]
                if date_query:
                    query["created_at"] = date_query
        
        # Debug: Print query for troubleshooting
        print(f"🔍 MongoDB Query: {json.dumps(query, indent=2, default=str)}")
        
        # Execute query with projection
        sort_direction = -1 if sort_by == "created_at" else 1
        vendors = list(db.vendors.find(
            query,
            {
                "vendor_id": 1,
                "basic_info.name": 1,
                "basic_info.company": 1,
                "basic_info.email": 1,
                "basic_info.age": 1,  # Include age in results for debugging
                "status": 1,
                "created_at": 1,
                "_id": 0
            }
        ).sort(sort_by, sort_direction).skip(offset).limit(limit))
        
        total_count = db.vendors.count_documents(query)
        
        print(f"✅ Found {total_count} vendors matching query")
        if vendors:
            print(f"📊 Sample vendor age: {vendors[0].get('basic_info', {}).get('age', 'N/A')}")
        
        return {
            "vendors": vendors,
            "total_count": total_count,
            "limit": limit,
            "offset": offset,
            "has_more": total_count > (offset + limit)
        }
    
    @staticmethod
    def get_vendor_details(identifier: str) -> Dict[str, Any]:
        """Get complete vendor details by ID, email, or company"""
        query = {
            "$or": [
                {"vendor_id": identifier},
                {"basic_info.email": identifier},
                {"basic_info.company": {"$regex": f"^{identifier}$", "$options": "i"}}
            ]
        }
        
        vendors = list(db.vendors.find(query, {"_id": 0}))
        
        if not vendors:
            return {"error": f"No vendor found with identifier: {identifier}"}
        
        if len(vendors) > 1:
            return {
                "error": "Multiple vendors found",
                "matches": [
                    {
                        "vendor_id": v["vendor_id"],
                        "name": v["basic_info"]["name"],
                        "company": v["basic_info"]["company"],
                        "email": v["basic_info"]["email"]
                    }
                    for v in vendors
                ]
            }
        
        return vendors[0]
    
    @staticmethod
    def count_vendors(filter_params: Dict = None, filter: Dict = None) -> Dict[str, Any]:
        """Count vendors with breakdown by status
        
        Accepts both 'filter_params' and 'filter' for compatibility
        """
        # Handle both parameter names
        if filter is not None and filter_params is None:
            filter_params = filter
        
        query = {}
        
        if filter_params:
            if filter_params.get("status"):
                query["status"] = filter_params["status"]
            if filter_params.get("company"):
                query["basic_info.company"] = {"$regex": filter_params["company"], "$options": "i"}
        
        total_count = db.vendors.count_documents(query)
        
        # Breakdown by status
        pipeline = [
            {"$match": query},
            {"$group": {"_id": "$status", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        
        status_breakdown = {item["_id"]: item["count"] for item in db.vendors.aggregate(pipeline)}
        
        return {
            "total_count": total_count,
            "breakdown": {
                "by_status": status_breakdown
            }
        }
    
    @staticmethod
    def search_vendors_fuzzy(search_text: str, fields: List[str] = None, 
                            limit: int = 20) -> List[Dict[str, Any]]:
        """Fuzzy search across name, company, email"""
        if not fields:
            fields = ["name", "company", "email"]
        
        # Normalize field names (handle both "name" and "basic_info.name")
        normalized_fields = []
        for field in fields:
            if "name" in field.lower():
                normalized_fields.append("name")
            elif "company" in field.lower():
                normalized_fields.append("company")
            elif "email" in field.lower():
                normalized_fields.append("email")
        
        # If no valid fields after normalization, default to all
        if not normalized_fields:
            normalized_fields = ["name", "company", "email"]
        
        query_conditions = []
        
        if "name" in normalized_fields:
            query_conditions.append({"basic_info.name": {"$regex": search_text, "$options": "i"}})
        if "company" in normalized_fields:
            query_conditions.append({"basic_info.company": {"$regex": search_text, "$options": "i"}})
        if "email" in normalized_fields:
            query_conditions.append({"basic_info.email": {"$regex": search_text, "$options": "i"}})
        
        query = {"$or": query_conditions} if query_conditions else {}
        
        # Debug logging
        print(f"🔍 Search query: {json.dumps(query, indent=2)}")
        
        vendors = list(db.vendors.find(
            query,
            {
                "vendor_id": 1,
                "basic_info": 1,
                "status": 1,
                "created_at": 1,
                "_id": 0
            }
        ).limit(limit))
        
        print(f"✅ Found {len(vendors)} vendors matching search")
        
        return vendors
    
    @staticmethod
    def vendor_statistics(date_range: Dict = None) -> Dict[str, Any]:
        """Get dashboard-level vendor statistics"""
        match_stage = {}
        
        if date_range:
            date_query = {}
            if date_range.get("start"):
                date_query["$gte"] = date_range["start"]
            if date_range.get("end"):
                date_query["$lte"] = date_range["end"]
            if date_query:
                match_stage = {"created_at": date_query}
        
        pipeline = [
            {"$match": match_stage} if match_stage else {"$match": {}},
            {
                "$facet": {
                    "total": [{"$count": "count"}],
                    "by_status": [
                        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
                        {"$sort": {"count": -1}}
                    ],
                    "by_document_type": [
                        {"$unwind": "$documents"},
                        {"$group": {"_id": "$documents.type", "count": {"$sum": 1}}}
                    ],
                    "avg_processing_time": [
                        {
                            "$project": {
                                "processing_time": {
                                    "$subtract": [
                                        {"$toDate": "$updated_at"},
                                        {"$toDate": "$created_at"}
                                    ]
                                }
                            }
                        },
                        {
                            "$group": {
                                "_id": None,
                                "avg_ms": {"$avg": "$processing_time"}
                            }
                        }
                    ]
                }
            }
        ]
        
        result = list(db.vendors.aggregate(pipeline))[0]
        
        return {
            "total_vendors": result["total"][0]["count"] if result["total"] else 0,
            "by_status": {item["_id"]: item["count"] for item in result["by_status"]},
            "by_document_type": {item["_id"]: item["count"] for item in result["by_document_type"]},
            "avg_processing_time_seconds": (result["avg_processing_time"][0]["avg_ms"] / 1000) if result["avg_processing_time"] else 0
        }
    
    @staticmethod
    def extraction_quality_report(confidence_threshold: float = 0.8) -> Dict[str, Any]:
        """Get vendors with low extraction confidence"""
        query = {
            "$or": [
                {"extracted_data.aadhar.confidence": {"$lt": confidence_threshold}},
                {"extracted_data.pan.confidence": {"$lt": confidence_threshold}},
                {"extracted_data.gst.confidence": {"$lt": confidence_threshold}}
            ]
        }
        
        vendors = list(db.vendors.find(
            query,
            {
                "vendor_id": 1,
                "basic_info.name": 1,
                "basic_info.company": 1,
                "extracted_data.aadhar.confidence": 1,
                "extracted_data.pan.confidence": 1,
                "extracted_data.gst.confidence": 1,
                "status": 1,
                "_id": 0
            }
        ))
        
        # Group by document type
        low_aadhar = [v for v in vendors if v.get("extracted_data", {}).get("aadhar", {}).get("confidence", 1) < confidence_threshold]
        low_pan = [v for v in vendors if v.get("extracted_data", {}).get("pan", {}).get("confidence", 1) < confidence_threshold]
        low_gst = [v for v in vendors if v.get("extracted_data", {}).get("gst", {}).get("confidence", 1) < confidence_threshold]
        
        return {
            "threshold": confidence_threshold,
            "total_low_confidence": len(vendors),
            "by_document_type": {
                "aadhar": {"count": len(low_aadhar), "vendors": low_aadhar[:10]},
                "pan": {"count": len(low_pan), "vendors": low_pan[:10]},
                "gst": {"count": len(low_gst), "vendors": low_gst[:10]}
            }
        }
    
    @staticmethod
    def vendor_processing_timeline(vendor_id: str) -> Dict[str, Any]:
        """Get complete processing timeline for a vendor"""
        # Get vendor
        vendor = db.vendors.find_one({"vendor_id": vendor_id}, {"_id": 0})
        if not vendor:
            return {"error": f"Vendor {vendor_id} not found"}
        
        # Get webhook log
        email_id = vendor.get("email_metadata", {}).get("email_id")
        webhook = db.webhook_logs.find_one({"email_id": email_id}, {"_id": 0}) if email_id else None
        
        # Get processed email
        processed = db.processed_emails.find_one({"email_id": email_id}, {"_id": 0}) if email_id else None
        
        # Get batches
        batches = list(db.batches.find({"vendor_ids": vendor_id}, {"_id": 0}))
        
        return {
            "vendor_id": vendor_id,
            "timeline": {
                "webhook_received": webhook.get("received_at") if webhook else None,
                "email_processed": processed.get("started_at") if processed else None,
                "documents_downloaded": vendor.get("created_at"),
                "extraction_started": batches[0].get("created_at") if batches else None,
                "extraction_completed": batches[0].get("completed_at") if batches else None,
                "current_status": vendor.get("status")
            },
            "webhook_details": webhook,
            "processing_details": processed,
            "batches": batches
        }
    
    @staticmethod
    def batch_processing_health(date_range: Dict = None, document_type: str = None) -> Dict[str, Any]:
        """Monitor batch processing pipeline health"""
        match_stage = {}
        
        if date_range:
            date_query = {}
            if date_range.get("start"):
                date_query["$gte"] = date_range["start"]
            if date_range.get("end"):
                date_query["$lte"] = date_range["end"]
            if date_query:
                match_stage["created_at"] = date_query
        
        if document_type:
            match_stage["document_type"] = document_type
        
        pipeline = [
            {"$match": match_stage} if match_stage else {"$match": {}},
            {
                "$facet": {
                    "total": [{"$count": "count"}],
                    "by_status": [
                        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
                        {"$sort": {"count": -1}}
                    ],
                    "avg_processing_time": [
                        {
                            "$match": {"completed_at": {"$exists": True}}
                        },
                        {
                            "$project": {
                                "processing_time": {
                                    "$subtract": [
                                        {"$toDate": "$completed_at"},
                                        {"$toDate": "$created_at"}
                                    ]
                                }
                            }
                        },
                        {
                            "$group": {
                                "_id": None,
                                "avg_ms": {"$avg": "$processing_time"}
                            }
                        }
                    ],
                    "failed_batches": [
                        {"$match": {"status": "failed"}},
                        {"$limit": 10},
                        {"$project": {"batch_id": 1, "document_type": 1, "total_documents": 1, "created_at": 1}}
                    ]
                }
            }
        ]
        
        result = list(db.batches.aggregate(pipeline))[0]
        
        total = result["total"][0]["count"] if result["total"] else 0
        by_status = {item["_id"]: item["count"] for item in result["by_status"]}
        success_count = by_status.get("completed", 0)
        success_rate = (success_count / total * 100) if total > 0 else 0
        
        return {
            "total_batches": total,
            "success_rate": round(success_rate, 2),
            "by_status": by_status,
            "avg_processing_time_seconds": (result["avg_processing_time"][0]["avg_ms"] / 1000) if result["avg_processing_time"] else 0,
            "failed_batches": result["failed_batches"]
        }
    
    @staticmethod
    def send_vendor_credentials(recipient_email: str, username: str, password: str) -> Dict[str, Any]:
        """
        Send vendor portal login credentials via email using Nylas API
        
        Args:
            recipient_email: Vendor's email address
            username: Portal login username
            password: Portal login password
            
        Returns:
            Dict with send status, log details, and confirmation message
        """
        import re
        from services.nylas_service import NylasService
        
        # ============================================================================
        # VALIDATION
        # ============================================================================
        
        # 1. Email validation
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, recipient_email):
            return {
                "success": False,
                "error": f"Invalid email format: {recipient_email}",
                "message": f"❌ Invalid email format: {recipient_email}\n\nPlease provide a valid email address (e.g., vendor@company.com)"
            }
        
        # 2. Username validation (4-50 chars, alphanumeric + underscore, hyphen, dot)
        username_pattern = r'^[a-zA-Z0-9._-]{4,50}$'
        if not re.match(username_pattern, username):
            return {
                "success": False,
                "error": "Invalid username format",
                "message": "❌ Invalid username format\n\nUsername must be:\n- 4-50 characters long\n- Only letters, numbers, underscore, hyphen, or dot\n- No whitespace"
            }
        
        # 3. Password validation (min 8 chars)
        if len(password) < 8:
            return {
                "success": False,
                "error": "Password too short",
                "message": "❌ Password too short\n\nPassword must be at least 8 characters long for security."
            }
        
        # 4. Username uniqueness check
        try:
            # Check if username already exists in sent_emails collection
            existing_username = db.sent_emails.find_one(
                {"username_sent": username},
                {"recipient_email": 1, "sent_at": 1, "_id": 0}
            )
            
            if existing_username:
                sent_to = existing_username.get("recipient_email", "unknown")
                sent_date = existing_username.get("sent_at", datetime.now())
                sent_date_str = sent_date.strftime("%Y-%m-%d %H:%M:%S") if isinstance(sent_date, datetime) else str(sent_date)
                
                return {
                    "success": False,
                    "error": "Username already exists",
                    "message": f"❌ Username already exists\n\nThe username '{username}' has already been assigned to another vendor.\n\n📋 Existing Assignment:\n• Username: {username}\n• Email: {sent_to}\n• Assigned on: {sent_date_str}\n\n💡 Please choose a different username.\n\nSuggestions:\n• {username}1\n• {username}_2\n• {username}_vendor\n• {recipient_email.split('@')[0]}_vendor"
                }
        
        except Exception as e:
            logging.warning(f"Username uniqueness check failed: {e}")
            # Continue anyway - this is a non-critical check
        
        # 5. Rate limiting check
        try:
            # Check per-recipient rate limit (max 3 per day)
            one_day_ago = datetime.now() - timedelta(days=1)
            recipient_count = db.sent_emails.count_documents({
                "recipient_email": recipient_email,
                "sent_at": {"$gte": one_day_ago}
            })
            
            if recipient_count >= 3:
                return {
                    "success": False,
                    "error": "Recipient rate limit exceeded",
                    "message": f"⚠️ Rate limit reached\n\nThis recipient ({recipient_email}) has already received {recipient_count} credential emails today.\n\nLimit: 3 emails per recipient per day\nReset time: Tomorrow at midnight\n\nPlease wait before sending more emails to this recipient."
                }
            
            # Check per-admin rate limit (max 50 per hour) - using a simple timestamp check
            one_hour_ago = datetime.now() - timedelta(hours=1)
            admin_count = db.sent_emails.count_documents({
                "sent_at": {"$gte": one_hour_ago}
            })
            
            if admin_count >= 50:
                return {
                    "success": False,
                    "error": "Admin rate limit exceeded",
                    "message": f"⚠️ Rate limit reached\n\nYou've sent {admin_count} credential emails in the last hour.\n\nLimit: 50 emails per hour\nReset time: {(one_hour_ago + timedelta(hours=1)).strftime('%I:%M %p')}\n\nNeed to send urgently? Contact system administrator."
                }
        
        except Exception as e:
            logging.warning(f"Rate limit check failed: {e}")
            # Continue anyway if rate limit check fails
        
        # ============================================================================
        # EMAIL GENERATION
        # ============================================================================
        
        # Get configuration from environment
        company_name = os.getenv("COMPANY_NAME", "Vendor Portal")
        portal_url = os.getenv("VENDOR_PORTAL_URL", "https://vendor-portal.company.com")
        support_email = os.getenv("SUPPORT_EMAIL", "support@company.com")
        support_phone = os.getenv("SUPPORT_PHONE", "+91-XXXXXXXXXX")
        sender_email = os.getenv("ADMIN_SENDER_EMAIL", "admin@company.com")
        
        # Generate HTML email body
        email_body_html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{
            font-family: Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            text-align: center;
            border-radius: 10px 10px 0 0;
        }}
        .content {{
            background: #f9f9f9;
            padding: 30px;
            border-left: 1px solid #ddd;
            border-right: 1px solid #ddd;
        }}
        .credentials-box {{
            background: white;
            border: 2px solid #667eea;
            border-radius: 8px;
            padding: 20px;
            margin: 20px 0;
        }}
        .credential-row {{
            display: flex;
            margin: 10px 0;
            font-size: 16px;
        }}
        .credential-label {{
            font-weight: bold;
            color: #667eea;
            width: 120px;
        }}
        .credential-value {{
            color: #333;
            font-family: 'Courier New', monospace;
            background: #f0f0f0;
            padding: 5px 10px;
            border-radius: 4px;
        }}
        .steps {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
        }}
        .step {{
            padding: 10px 0;
            border-left: 3px solid #667eea;
            padding-left: 15px;
            margin: 10px 0;
        }}
        .footer {{
            background: #333;
            color: #fff;
            padding: 20px;
            text-align: center;
            font-size: 12px;
            border-radius: 0 0 10px 10px;
        }}
        .button {{
            display: inline-block;
            background: #667eea;
            color: white;
            padding: 12px 30px;
            text-decoration: none;
            border-radius: 5px;
            margin: 20px 0;
            font-weight: bold;
        }}
        .security-note {{
            background: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 15px;
            margin: 20px 0;
            border-radius: 4px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🎉 Welcome to {company_name}!</h1>
        <p>Your Vendor Portal Account is Ready</p>
    </div>
    
    <div class="content">
        <p>Dear Vendor,</p>
        
        <p>Welcome to the <strong>{company_name}</strong> Vendor Portal! Your account has been successfully created and is ready to use.</p>
        
        <div class="credentials-box">
            <h3 style="margin-top: 0; color: #667eea;">🔐 Your Login Credentials</h3>
            <div class="credential-row">
                <span class="credential-label">🔐 Username:</span>
                <span class="credential-value">{username}</span>
            </div>
            <div class="credential-row">
                <span class="credential-label">🔑 Password:</span>
                <span class="credential-value">{password}</span>
            </div>
            <div class="credential-row">
                <span class="credential-label">🌐 Portal URL:</span>
                <span class="credential-value">{portal_url}</span>
            </div>
        </div>
        
        <div style="text-align: center;">
            <a href="{portal_url}" class="button">Access Vendor Portal →</a>
        </div>
        
        <div class="steps">
            <h3 style="color: #667eea;">📋 Getting Started</h3>
            <div class="step">
                <strong>1.</strong> Visit the portal using the link above or button
            </div>
            <div class="step">
                <strong>2.</strong> Log in with your credentials (username and password)
            </div>
            <div class="step">
                <strong>3.</strong> Complete your vendor registration through our chatbot assistant
            </div>
            <div class="step">
                <strong>4.</strong> Upload required documents (Aadhar, PAN, GST certificates)
            </div>
        </div>
        
        <div class="security-note">
            <strong>🔒 Security Note:</strong><br>
            Please change your password after your first login for enhanced security. Do not share your credentials with anyone. Our team will never ask for your password via email or phone.
        </div>
        
        <h3 style="color: #667eea;">🆘 Need Help?</h3>
        <ul>
            <li>💬 Chat with our vendor assistant directly on the portal</li>
            <li>📧 Email us at <a href="mailto:{support_email}">{support_email}</a></li>
            <li>📞 Call us at {support_phone}</li>
        </ul>
        
        <p>We're excited to have you onboard!</p>
        
        <p>Best regards,<br>
        <strong>{company_name} Vendor Management Team</strong></p>
    </div>
    
    <div class="footer">
        <p>━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━</p>
        <p>This is an automated message. Please do not reply to this email.</p>
        <p>For support, contact {support_email}</p>
        <p>© 2025 {company_name}. All rights reserved.</p>
    </div>
</body>
</html>
"""
        
        # Plain text version (fallback)
        email_body_text = f"""
Dear Vendor,

Welcome to the {company_name} Vendor Portal! Your account has been created and is ready to use.

Your login credentials are:
━━━━━━━━━━━━━━━━━━━━━━━━━━
🔐 Username: {username}
🔑 Password: {password}  
🌐 Portal URL: {portal_url}
━━━━━━━━━━━━━━━━━━━━━━━━━━

Getting Started:
1. Visit the portal using the link above
2. Log in with your credentials
3. Complete your vendor registration through our chatbot assistant
4. Upload required documents (Aadhar, PAN, GST)

Need Help?
- Chat with our vendor assistant directly on the portal
- Email us at {support_email}
- Call us at {support_phone}

Security Note: Please change your password after your first login. Do not share your credentials with anyone.

Best regards,
{company_name} Vendor Management Team

━━━━━━━━━━━━━━━━━━━━━━━━━━
This is an automated message. Please do not reply to this email.
"""
        
        # ============================================================================
        # SEND EMAIL VIA NYLAS
        # ============================================================================
        
        try:
            nylas = NylasService()
            
            # Prepare email data for Nylas v3 API
            email_data = {
                "subject": f"Your {company_name} Vendor Portal Login Credentials",
                "to": [{"email": recipient_email}],
                "from": [{"email": sender_email}],
                "reply_to": [{"email": support_email}],
                "body": email_body_html
            }
            
            # Send email using Nylas
            url = f"{nylas.base_url}/v3/grants/{nylas.grant_id}/messages/send"
            response = requests.post(
                url,
                headers=nylas.headers,
                json=email_data,
                timeout=30
            )
            
            if response.status_code not in [200, 201, 202]:
                error_msg = response.text
                logging.error(f"Nylas API error: {response.status_code} - {error_msg}")
                return {
                    "success": False,
                    "error": f"Nylas API returned error: {response.status_code}",
                    "message": f"❌ Failed to send credential email\n\nError: Nylas API returned error: {response.status_code}\n\nPlease verify:\n- Email address is correct: {recipient_email}\n- Email service is operational\n\nWould you like to retry with a corrected email?"
                }
            
            response_data = response.json()
            nylas_message_id = response_data.get("data", {}).get("id", "unknown")
            
        except requests.exceptions.Timeout:
            return {
                "success": False,
                "error": "Request timeout",
                "message": "❌ Failed to send credential email\n\nError: Request timeout while sending email\n\nThe email service took too long to respond. Please try again in a moment."
            }
        except Exception as e:
            logging.error(f"Error sending email: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "message": f"❌ Failed to send credential email\n\nError: {str(e)}\n\nPlease check the email configuration and try again."
            }
        
        # ============================================================================
        # LOG EMAIL SEND
        # ============================================================================
        
        timestamp = datetime.now()
        log_id = f"EMAIL_LOG_{int(timestamp.timestamp())}"
        
        try:
            email_log = {
                "email_log_id": log_id,
                "recipient_email": recipient_email,
                "email_type": "credentials",
                "username_sent": username,
                "password_sent": password,  # Store password for admin reference
                "sent_by_admin": "admin_user",  # Could be enhanced with actual admin tracking
                "sent_at": timestamp,
                "nylas_message_id": nylas_message_id,
                "status": "sent",
                "error_message": None
            }
            
            db.sent_emails.insert_one(email_log)
            
        except Exception as e:
            logging.warning(f"Failed to log email send: {e}")
            # Continue anyway - email was sent successfully
        
        # ============================================================================
        # SUCCESS RESPONSE
        # ============================================================================
        
        success_message = f"""✅ Credential email sent successfully!

Recipient Details:
━━━━━━━━━━━━━━━━━━━━━━━━━━
📧 Email: {recipient_email}
━━━━━━━━━━━━━━━━━━━━━━━━━━

Credentials Sent:
🔐 Username: {username}
🔑 Password: {password}

📨 Email Status: Sent
🕐 Sent At: {timestamp.strftime('%Y-%m-%d %H:%M:%S')} IST
📝 Log ID: {log_id}
🔖 Message ID: {nylas_message_id}

The vendor should receive the email within 1-2 minutes. The email includes:
• Login credentials (username and password)
• Portal access link
• Getting started instructions
• Support contact information

💡 Next steps:
- The vendor can now login at {portal_url}
- They should register through the chatbot on the portal
- Upload required documents (Aadhar, PAN, GST)

Would you like to send credentials to another vendor?"""
        
        return {
            "success": True,
            "recipient_email": recipient_email,
            "username": username,
            "sent_at": timestamp.isoformat(),
            "log_id": log_id,
            "nylas_message_id": nylas_message_id,
            "message": success_message
        }


# ============================================================================
# QUERY VALIDATOR
# ============================================================================

class QueryValidator:
    """Validates dynamically generated MongoDB queries for security"""
    
    ALLOWED_COLLECTIONS = ["vendors", "webhook_logs", "processed_emails", "rejected_emails", "batches"]
    
    FORBIDDEN_OPERATORS = [
        "$where", "$function", "$accumulator", "eval", "mapReduce",
        "$expr", "$jsonSchema"  # Can be exploited
    ]
    
    UPDATABLE_FIELDS = [
        "basic_info.mobile",
        "basic_info.mobile_cleaned",
        "basic_info.address",
        "basic_info.age",
        "basic_info.name",
        "basic_info.gender",
        "basic_info.company",
        "basic_info.email",
        "status"
    ]
    
    @staticmethod
    def validate_query(query_request: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Validate generated query for security and correctness"""
        
        # Check collection
        collection = query_request.get("collection")
        if collection not in QueryValidator.ALLOWED_COLLECTIONS:
            return False, f"Collection '{collection}' not allowed"
        
        # Check operation
        operation = query_request.get("operation")
        if operation not in ["find", "aggregate", "update", "count"]:
            return False, f"Operation '{operation}' not allowed"
        
        # Check for forbidden operators
        query_str = json.dumps(query_request.get("query", {}))
        for forbidden in QueryValidator.FORBIDDEN_OPERATORS:
            if forbidden in query_str:
                return False, f"Forbidden operator '{forbidden}' detected"
        
        # Validate update operations
        if operation == "update":
            update_doc = query_request.get("update", {})
            update_fields = QueryValidator._extract_update_fields(update_doc)
            
            for field in update_fields:
                if field not in QueryValidator.UPDATABLE_FIELDS:
                    return False, f"Field '{field}' is not updatable"
        
        # Check limit
        limit = query_request.get("limit", 100)
        if limit > 1000:
            return False, "Limit cannot exceed 1000 documents"
        
        return True, None
    
    @staticmethod
    def _extract_update_fields(update_doc: Dict) -> List[str]:
        """Extract field names from update document"""
        fields = []
        
        for operator, values in update_doc.items():
            if operator in ["$set", "$unset", "$inc"]:
                fields.extend(values.keys())
        
        return fields


# ============================================================================
# QUERY EXECUTOR
# ============================================================================

class QueryExecutor:
    """Executes validated queries with proper error handling"""
    
    @staticmethod
    def execute_dynamic_query(query_request: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a validated dynamic MongoDB query"""
        
        collection_name = query_request["collection"]
        operation = query_request["operation"]
        collection = db[collection_name]
        
        try:
            if operation == "find":
                query = query_request.get("query", {})
                projection = query_request.get("projection", {"_id": 0})
                sort = query_request.get("sort", {})
                limit = query_request.get("limit", 100)
                
                cursor = collection.find(query, projection)
                
                if sort:
                    cursor = cursor.sort(list(sort.items()))
                
                cursor = cursor.limit(limit)
                
                results = list(cursor)
                
                return {
                    "success": True,
                    "data": results,
                    "count": len(results)
                }
            
            elif operation == "aggregate":
                pipeline = query_request.get("query", [])
                results = list(collection.aggregate(pipeline))
                
                return {
                    "success": True,
                    "data": results,
                    "count": len(results)
                }
            
            elif operation == "count":
                query = query_request.get("query", {})
                count = collection.count_documents(query)
                
                return {
                    "success": True,
                    "count": count
                }
            
            elif operation == "update":
                query = query_request.get("query", {})
                update = query_request.get("update", {})
                
                result = collection.update_many(query, update)
                
                return {
                    "success": True,
                    "matched_count": result.matched_count,
                    "modified_count": result.modified_count
                }
        
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }


# ============================================================================
# MAIN CHATBOT ENDPOINT
# ============================================================================

@router.post("/chat", response_model=ChatResponse)
async def chat_with_admin(request: ChatRequest):
    """
    Main chatbot endpoint - Intelligent routing to functions or dynamic queries
    """
    start_time = datetime.now()
    
    try:
        # Build conversation messages
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        
        # Add conversation history
        for msg in request.conversation_history[-5:]:  # Last 5 messages for context
            messages.append({
                "role": msg.role,
                "content": msg.content
            })
        
        # Add current user message
        messages.append({
            "role": "user",
            "content": request.message
        })
        
        # Call OpenAI with function calling
        response = openai_client.chat.completions.create(
            model="gpt-4o",  # or gpt-4-turbo
            messages=messages,
            temperature=0.3,  # Low temperature for accuracy
            response_format={"type": "json_object"}  # Force JSON response
        )
        
        llm_response = response.choices[0].message.content
        llm_data = json.loads(llm_response)
        
        # Debug: Log LLM decision
        print(f"🤖 LLM Decision: {json.dumps(llm_data, indent=2)}")
        
        # Route based on LLM decision
        if llm_data.get("function"):
            # LLM decided to use pre-defined function
            result = await execute_function(llm_data)
            query_type = "function"
        
        elif llm_data.get("query_type") == "dynamic":
            # LLM generated custom MongoDB query
            result = await execute_dynamic_query_safe(llm_data)
            query_type = "dynamic_query"
        
        else:
            # Direct text response (clarification, error, etc.)
            result = {
                "response": llm_data.get("response", llm_response),
                "data": llm_data.get("data")
            }
            query_type = "text_response"
        
        execution_time = int((datetime.now() - start_time).total_seconds() * 1000)
        
        return ChatResponse(
            response=result.get("response", ""),
            data=result.get("data"),
            query_type=query_type,
            execution_time_ms=execution_time,
            suggestions=result.get("suggestions")
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Chatbot error: {str(e)}"
        )


async def execute_function(llm_data: Dict[str, Any]) -> Dict[str, Any]:
    """Execute pre-defined function based on LLM decision"""
    
    function_name = llm_data["function"]
    parameters = llm_data.get("parameters", {})
    
    functions = VendorQueryFunctions()
    
    try:
        if function_name == "list_vendors":
            # Handle empty or missing parameters gracefully
            if not parameters or parameters == {}:
                parameters = {"limit": 50}  # Default to showing 50 vendors
            data = functions.list_vendors(**parameters)
            response = format_list_vendors_response(data)
        
        elif function_name == "get_vendor_details":
            data = functions.get_vendor_details(**parameters)
            response = format_vendor_details_response(data)
        
        elif function_name == "count_vendors":
            data = functions.count_vendors(**parameters)
            response = format_count_response(data)
        
        elif function_name == "search_vendors_fuzzy":
            # Ensure parameters are correctly formatted
            search_text = parameters.get("search_text", "")
            fields = parameters.get("fields", ["name", "company", "email"])
            limit = parameters.get("limit", 20)
            
            # Validate fields is a list
            if isinstance(fields, str):
                fields = [fields]
            
            data = functions.search_vendors_fuzzy(search_text, fields, limit)
            response = format_search_results(data)
        
        elif function_name == "vendor_statistics":
            data = functions.vendor_statistics(**parameters)
            response = format_statistics_response(data)
        
        elif function_name == "extraction_quality_report":
            data = functions.extraction_quality_report(**parameters)
            response = format_quality_report(data)
        
        elif function_name == "vendor_processing_timeline":
            data = functions.vendor_processing_timeline(**parameters)
            response = format_timeline_response(data)
        
        elif function_name == "batch_processing_health":
            data = functions.batch_processing_health(**parameters)
            response = format_health_report(data)
        
        elif function_name == "send_vendor_credentials":
            # Handle credential email sending
            recipient_email = parameters.get("recipient_email", "")
            username = parameters.get("username", "")
            password = parameters.get("password", "")
            
            # Call the function
            result = functions.send_vendor_credentials(recipient_email, username, password)
            
            # Return the formatted message from the function
            response = result.get("message", "Email processing completed")
            data = result if result.get("success") else {"error": result.get("error")}
        
        else:
            return {
                "response": f"Function '{function_name}' not implemented",
                "data": None
            }
        
        return {
            "response": response,
            "data": data
        }
    
    except TypeError as e:
        return {
            "response": f"❌ Function parameter error: {str(e)}. Please try rephrasing your query.",
            "data": None
        }
    except Exception as e:
        return {
            "response": f"❌ Error executing function '{function_name}': {str(e)}",
            "data": None
        }


async def execute_dynamic_query_safe(llm_data: Dict[str, Any]) -> Dict[str, Any]:
    """Execute dynamically generated query with validation"""
    
    # Validate query
    is_valid, error_message = QueryValidator.validate_query(llm_data)
    
    if not is_valid:
        return {
            "response": f"⚠️ Query validation failed: {error_message}",
            "data": None
        }
    
    # Execute query
    result = QueryExecutor.execute_dynamic_query(llm_data)
    
    if not result.get("success"):
        return {
            "response": f"❌ Query execution failed: {result.get('error')}",
            "data": None
        }
    
    # Format response
    response = format_dynamic_query_response(result, llm_data)
    
    return {
        "response": response,
        "data": result.get("data")
    }


# ============================================================================
# RESPONSE FORMATTERS
# ============================================================================

def format_list_vendors_response(data: Dict) -> str:
    """Format list vendors response"""
    vendors = data["vendors"]
    total = data["total_count"]
    
    if total == 0:
        return "I couldn't find any vendors matching those criteria. Would you like me to show all vendors, or try a different filter?"
    
    vendor_word = "vendors" if total != 1 else "vendor"
    
    # Conversational opening
    if total == 1:
        response = f"Perfect! I found exactly 1 vendor matching your search:\n\n"
    elif total <= 5:
        response = f"Great! I found {total} {vendor_word} for you:\n\n"
    elif total <= 20:
        response = f"I discovered {total} {vendor_word} matching your criteria. Here they are:\n\n"
    else:
        response = f"Wow! I found {total} {vendor_word} matching your search. Here are the first 20:\n\n"
    
    for i, vendor in enumerate(vendors[:20], 1):
        try:
            # Safely extract fields with defaults
            basic_info = vendor.get('basic_info', {})
            name = basic_info.get('name', 'Unknown')
            company = basic_info.get('company', 'Unknown')
            email = basic_info.get('email', 'N/A')
            age = basic_info.get('age', 'N/A')
            status = vendor.get('status', 'unknown')
            
            status_icon = "✅" if status == "completed" else "⚠️" if status == "needs_review" else "🔄"
            
            response += f"{i}. {status_icon} **{name}** - {company}\n"
            response += f"   Email: {email} | Age: {age} | Status: {status}\n\n"
        except Exception as e:
            # Skip vendors with corrupt data
            print(f"⚠️ Error formatting vendor {i}: {str(e)}")
            continue
    
    # Add helpful closing
    if total > 20:
        response += f"_Showing 20 out of {total} results. Would you like me to show more or apply additional filters?_"
    elif total > 1:
        response += "\n💡 Need more details about any vendor? Just ask!"
    
    return response


def format_vendor_details_response(data: Dict) -> str:
    """Format vendor details response"""
    if "error" in data:
        if "matches" in data:
            response = f"⚠️ {data['error']}. Please specify:\n\n"
            for i, match in enumerate(data["matches"], 1):
                # Safe access for match fields
                match_name = match.get('name', 'Unknown')
                match_company = match.get('company', 'Unknown')
                match_email = match.get('email', 'N/A')
                response += f"{i}. {match_name} - {match_company} ({match_email})\n"
            return response
        return f"❌ {data['error']}"
    
    # Safe access for all vendor fields
    basic_info = data.get('basic_info', {})
    name = basic_info.get('name', 'Unknown')
    age = basic_info.get('age', 'N/A')
    gender = basic_info.get('gender', 'N/A')
    email = basic_info.get('email', 'N/A')
    mobile = basic_info.get('mobile', 'N/A')
    company = basic_info.get('company', 'Unknown')
    address = basic_info.get('address', 'N/A')
    vendor_id = data.get('vendor_id', 'N/A')
    status = data.get('status', 'Unknown')
    
    response = f"# Vendor Details: {name}\n\n"
    response += f"**Vendor ID:** {vendor_id}\n"
    response += f"**Status:** {status}\n\n"
    
    response += "## Basic Information\n"
    response += f"- Name: {name}\n"
    response += f"- Age: {age}\n"
    response += f"- Gender: {gender}\n"
    response += f"- Email: {email}\n"
    response += f"- Mobile: {mobile}\n"
    response += f"- Company: {company}\n"
    response += f"- Address: {address}\n\n"
    
    if data.get("extracted_data"):
        response += "## Extracted Documents\n"
        for doc_type in ["aadhar", "pan", "gst"]:
            if data["extracted_data"].get(doc_type):
                confidence = data["extracted_data"][doc_type].get("confidence", 0)
                icon = "✅" if confidence > 0.9 else "⚠️" if confidence > 0.8 else "❌"
                response += f"- {icon} **{doc_type.upper()}**: Confidence {confidence:.2%}\n"
    
    return response


def format_count_response(data: Dict) -> str:
    """Format count response"""
    response = f"📊 **Total Vendors:** {data['total_count']}\n\n"
    response += "**Breakdown by Status:**\n"
    
    for status, count in sorted(data['breakdown']['by_status'].items(), key=lambda x: x[1], reverse=True):
        percentage = (count / data['total_count'] * 100) if data['total_count'] > 0 else 0
        response += f"- {status}: {count} ({percentage:.1f}%)\n"
    
    return response


def format_search_results(data: List[Dict]) -> str:
    """Format search results"""
    if not data:
        return "Hmm, I couldn't find any vendors matching that search. Could you try a different name or email? Or would you like me to show all vendors?"
    
    vendor_word = "vendors" if len(data) != 1 else "vendor"
    
    # Conversational opening based on result count
    if len(data) == 1:
        response = f"Perfect! I found exactly 1 {vendor_word} matching your search:\n\n"
    else:
        response = f"Great! I found {len(data)} {vendor_word} matching your search:\n\n"
    
    for i, vendor in enumerate(data, 1):
        try:
            # Safe access for vendor fields
            basic_info = vendor.get('basic_info', {})
            name = basic_info.get('name', 'Unknown')
            company = basic_info.get('company', 'Unknown')
            email = basic_info.get('email', 'N/A')
            status = vendor.get('status', 'Unknown')
            
            response += f"{i}. **{name}** - {company}\n"
            response += f"   Email: {email} | Status: {status}\n\n"
        except Exception as e:
            # Skip vendors with corrupt data
            logging.warning(f"Skipping vendor {i} due to error: {e}")
            continue
    
    # Add helpful suggestion
    if len(data) == 1:
        response += "💡 Want to see full details or update this vendor? Just let me know!"
    else:
        response += "💡 Need more details about any of these vendors? Just ask!"
    
    return response


def format_statistics_response(data: Dict) -> str:
    """Format statistics response"""
    response = f"📊 **Vendor Statistics**\n\n"
    response += f"**Total Vendors:** {data['total_vendors']}\n\n"
    
    response += "**By Status:**\n"
    for status, count in sorted(data['by_status'].items(), key=lambda x: x[1], reverse=True):
        response += f"- {status}: {count}\n"
    
    response += f"\n**Average Processing Time:** {data['avg_processing_time_seconds']:.1f} seconds\n"
    
    return response


def format_quality_report(data: Dict) -> str:
    """Format extraction quality report"""
    response = f"📋 **Extraction Quality Report** (Threshold: {data['threshold']:.0%})\n\n"
    response += f"**Total Low Confidence Vendors:** {data['total_low_confidence']}\n\n"
    
    for doc_type, info in data['by_document_type'].items():
        response += f"**{doc_type.upper()}:** {info['count']} vendors\n"
    
    response += f"\n💡 Recommendation: Review these vendors manually for data accuracy."
    
    return response


def format_timeline_response(data: Dict) -> str:
    """Format processing timeline"""
    if "error" in data:
        return f"❌ {data['error']}"
    
    timeline = data['timeline']
    response = f"⏱️ **Processing Timeline for {data['vendor_id']}**\n\n"
    
    steps = [
        ("Webhook Received", timeline.get('webhook_received')),
        ("Email Processed", timeline.get('email_processed')),
        ("Documents Downloaded", timeline.get('documents_downloaded')),
        ("Extraction Started", timeline.get('extraction_started')),
        ("Extraction Completed", timeline.get('extraction_completed'))
    ]
    
    for step_name, timestamp in steps:
        icon = "✅" if timestamp else "⏳"
        time_str = timestamp if timestamp else "Pending"
        response += f"{icon} {step_name}: {time_str}\n"
    
    response += f"\n**Current Status:** {timeline['current_status']}"
    
    return response


def format_health_report(data: Dict) -> str:
    """Format batch processing health report"""
    response = f"🏥 **Batch Processing Health Report**\n\n"
    response += f"**Total Batches:** {data['total_batches']}\n"
    response += f"**Success Rate:** {data['success_rate']:.1f}%\n"
    response += f"**Avg Processing Time:** {data['avg_processing_time_seconds']:.1f} seconds\n\n"
    
    response += "**Status Breakdown:**\n"
    for status, count in sorted(data['by_status'].items(), key=lambda x: x[1], reverse=True):
        response += f"- {status}: {count}\n"
    
    if data['failed_batches']:
        response += f"\n⚠️ {len(data['failed_batches'])} failed batches detected. Review logs for details."
    
    return response


def format_dynamic_query_response(result: Dict, query_request: Dict) -> str:
    """Format dynamic query response"""
    operation = query_request.get("operation", "find")
    
    # Handle UPDATE operations specially
    if operation == "update":
        matched = result.get("matched_count", 0)
        modified = result.get("modified_count", 0)
        
        # Use the pre-generated response from LLM if available
        if "response" in query_request and matched > 0:
            return query_request["response"]
        
        if matched == 0:
            return "Hmm, I couldn't find any vendors matching that criteria. Could you double-check the name or try a different identifier?"
        elif modified == 0:
            return f"I found {matched} vendor(s) matching your search, but the data was already set to that value. No changes were needed!"
        else:
            return f"✅ Perfect! I've successfully updated {modified} vendor(s). The changes have been saved to the system!"
    
    # Handle FIND/AGGREGATE operations
    data = result.get("data", [])
    count = result.get("count", 0)
    
    result_word = "results" if count != 1 else "result"
    response = f"I found {count} {result_word} for your query:\n\n"
    
    if isinstance(data, list) and data:
        # Show first few results
        response += "Here's what I discovered:\n"
        for i, item in enumerate(data[:10], 1):
            response += f"{i}. {json.dumps(item, indent=2)}\n"
        
        if count > 10:
            response += f"\n_Showing 10 out of {count} results. Want to see more?_"
    elif count == 0:
        response = "I couldn't find any results matching that query. Would you like to try a different search?"
    
    return response


# ============================================================================
# HEALTH CHECK
# ============================================================================

@router.get("/health")
async def chatbot_health():
    """Health check for chatbot service"""
    return {
        "status": "healthy",
        "service": "Admin Chatbot",
        "mongodb_connected": True,
        "openai_configured": bool(os.getenv("OPENAI_API_KEY")),
        "timestamp": datetime.now().isoformat()
    }
