"""
Nylas API Integration Service
Handles email fetching and attachment downloads from Nylas
"""
import os
import requests
from typing import List, Dict, Any, Optional
from datetime import datetime


class NylasService:
    """Service for interacting with Nylas API"""
    
    def __init__(self):
        self.api_key = os.getenv("NYLAS_API_KEY")
        self.client_id = os.getenv("NYLAS_CLIENT_ID")
        self.grant_id = os.getenv("NYLAS_GRANT_ID")
        self.base_url = "https://api.us.nylas.com"
        
        if not all([self.api_key, self.grant_id]):
            raise ValueError("Missing Nylas configuration. Check NYLAS_API_KEY and NYLAS_GRANT_ID")
        
        self.headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
    
    def fetch_emails(self, limit: int = 1000, subject_filter: str = "VENDOR REGISTRATION") -> List[Dict[str, Any]]:
        """
        Fetch emails from Nylas with subject filter
        
        Args:
            limit: Maximum number of emails to fetch
            subject_filter: Subject line filter
            
        Returns:
            List of email objects
        """
        try:
            url = f"{self.base_url}/v3/grants/{self.grant_id}/messages"
            
            params = {
                "limit": min(limit, 200),  # Nylas has per-request limits
                "subject": subject_filter
            }
            
            all_emails = []
            next_cursor = None
            
            while len(all_emails) < limit:
                if next_cursor:
                    params["page_token"] = next_cursor
                
                response = requests.get(url, headers=self.headers, params=params)
                
                if response.status_code != 200:
                    print(f"Error fetching emails: {response.status_code} - {response.text}")
                    break
                
                data = response.json()
                emails = data.get("data", [])
                all_emails.extend(emails)
                
                # Check for pagination
                next_cursor = data.get("next_cursor")
                if not next_cursor or not emails:
                    break
                
                # Stop if we have enough
                if len(all_emails) >= limit:
                    all_emails = all_emails[:limit]
                    break
            
            print(f"Fetched {len(all_emails)} emails from Nylas")
            return all_emails
            
        except Exception as e:
            print(f"Error in fetch_emails: {str(e)}")
            raise
    
    def get_email_details(self, message_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a specific email
        
        Args:
            message_id: Nylas message ID
            
        Returns:
            Email details including body and attachments
        """
        try:
            url = f"{self.base_url}/v3/grants/{self.grant_id}/messages/{message_id}"
            
            response = requests.get(url, headers=self.headers)
            
            if response.status_code != 200:
                print(f"Error fetching email {message_id}: {response.status_code}")
                return None
            
            return response.json().get("data")
            
        except Exception as e:
            print(f"Error in get_email_details: {str(e)}")
            return None
    
    def download_attachment(self, grant_id: str, message_id: str, attachment_id: str, save_folder: str) -> Optional[str]:
        """
        Download an attachment from an email
        
        Args:
            grant_id: Nylas grant ID (for webhook compatibility)
            message_id: Nylas message ID
            attachment_id: Attachment ID (format: v0:base64_filename:base64_content:size)
            save_folder: Folder to save the file
            
        Returns:
            Full path to saved file if successful, None otherwise
        """
        try:
            # Use the provided grant_id or fall back to default
            gid = grant_id or self.grant_id
            
            # Nylas v3: Attachments are accessed via a different endpoint
            # First, decode the attachment_id to get the filename
            # Format: v0:base64_filename:base64_content_type:size
            import base64
            
            try:
                parts = attachment_id.split(':')
                if len(parts) >= 2:
                    filename_b64 = parts[1]
                    filename = base64.b64decode(filename_b64).decode('utf-8')
                else:
                    filename = f"attachment_{attachment_id[:20]}"
            except:
                filename = f"attachment_{attachment_id[:20]}"
            
            print(f"🔍 Decoded filename: {filename}")
            
            # Nylas v3 API: Download endpoint (NOT metadata endpoint)
            # GET /v3/grants/{grant_id}/attachments/{attachment_id}/download?message_id={message_id}
            url = f"{self.base_url}/v3/grants/{gid}/attachments/{attachment_id}/download"
            
            print(f"🔗 Downloading from: {url}")
            print(f"🔗 Query params: message_id={message_id}")
            
            # Set headers for binary download - MUST NOT include Content-Type: application/json
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "*/*"  # Accept any content type
            }
            
            params = {"message_id": message_id}
            
            response = requests.get(url, headers=headers, params=params, stream=True)
            
            if response.status_code != 200:
                print(f"❌ Error downloading attachment: {response.status_code}")
                print(f"   Response: {response.text}")
                return None
            
            # Ensure directory exists
            os.makedirs(save_folder, exist_ok=True)
            
            # Build full save path
            save_path = os.path.join(save_folder, filename)
            
            # Write file
            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            print(f"✅ Downloaded: {filename} ({os.path.getsize(save_path)} bytes)")
            return save_path
            
        except Exception as e:
            print(f"❌ Error in download_attachment: {str(e)}")
            import traceback
            traceback.print_exc()
            return None
    
    def get_attachments_info(self, message_id: str) -> List[Dict[str, Any]]:
        """
        Get information about all attachments in an email
        
        Args:
            message_id: Nylas message ID
            
        Returns:
            List of attachment information dictionaries
        """
        try:
            email_details = self.get_email_details(message_id)
            
            if not email_details:
                return []
            
            attachments = email_details.get("attachments", [])
            
            return [{
                "id": att.get("id"),
                "filename": att.get("filename"),
                "content_type": att.get("content_type"),
                "size": att.get("size"),
            } for att in attachments]
            
        except Exception as e:
            print(f"Error in get_attachments_info: {str(e)}")
            return []
