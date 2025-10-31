# OpenAI LLM-based verification for vendor info vs documents
import os
import json
from openai import OpenAI

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

def verify_vendor_info_with_documents(vendor_draft_path: str, vendor_id: str) -> bool:
	"""
	Verifies if the vendor's basic info matches Aadhaar, PAN, and GST document data using OpenAI LLM.
	Updates the vendor draft JSON with an 'is_verified' field.
	Returns True if verified, False otherwise.
	"""
	if not client:
		raise RuntimeError("OpenAI API key not set in environment variable 'OPENAI_API_KEY'.")

	# Load vendor draft data
	with open(vendor_draft_path, 'r', encoding='utf-8') as f:
		vendor_drafts = json.load(f)

	vendor = vendor_drafts.get(vendor_id)
	if not vendor:
		raise ValueError(f"Vendor with id {vendor_id} not found.")

	# Prepare info for LLM
	basic = vendor.get('basic_details') or {}
	aadhaar = vendor.get('aadhaar_data') or {}
	pan = vendor.get('pan_data') or {}
	gst = vendor.get('gst_data') or {}

	# Extract key fields for comparison
	basic_name = basic.get('full_name', '').lower().strip()
	basic_gender = basic.get('gender', '').lower().strip()
	basic_age = basic.get('age')
	
	# Extract document data
	aadhaar_name = aadhaar.get('name', '').lower().strip()
	aadhaar_gender = aadhaar.get('gender', '').lower().strip()
	aadhaar_dob = aadhaar.get('dob', '')
	
	pan_name = pan.get('name', '').lower().strip()
	pan_dob = pan.get('dob', '')
	
	gst_name = gst.get('business_name', '').lower().strip()
	
	prompt = f"""
Compare basic info with document data. Check if name, gender, and date of birth are reasonably similar (allow minor spelling differences, abbreviations, and formatting variations).

Basic Info:
- Name: {basic_name}
- Gender: {basic_gender}
- Age: {basic_age}

Documents:
- Aadhaar: Name="{aadhaar_name}", Gender="{aadhaar_gender}", DOB="{aadhaar_dob}"
- PAN: Name="{pan_name}", DOB="{pan_dob}"
- GST: Business Name="{gst_name}"

Rules:
- Names should be reasonably similar (allow abbreviations, middle names, spelling variations)
- Gender should match if available
- DOB/Age should be consistent if available
- Consider it verified if basic details match reasonably well with ANY document

Provide response in this exact format:
Status: verified/not_verified
Reason: [detailed explanation of what matches or what doesn't match]
"""

	response = client.chat.completions.create(
		model="gpt-4o",
		messages=[{"role": "system", "content": "You are a flexible document verification assistant. Be reasonable with minor differences in names, spellings, and formats."},
				  {"role": "user", "content": prompt}],
		max_tokens=100,
		temperature=0.1
	)
	
	result = response.choices[0].message.content.strip()
	
	# Parse the response to extract status and reason
	lines = result.split('\n')
	status_line = ""
	reason_line = ""
	
	for line in lines:
		if line.lower().startswith('status:'):
			status_line = line.split(':', 1)[1].strip().lower()
		elif line.lower().startswith('reason:'):
			reason_line = line.split(':', 1)[1].strip()
	
	is_verified = 'verified' in status_line and 'not_verified' not in status_line
	verification_reason = reason_line if reason_line else "No specific reason provided"

	# Update vendor draft with both verification status and reason
	vendor['is_verified'] = is_verified
	vendor['verification_reason'] = verification_reason
	vendor_drafts[vendor_id] = vendor
	with open(vendor_draft_path, 'w', encoding='utf-8') as f:
		json.dump(vendor_drafts, f, indent=2, ensure_ascii=False)

	return is_verified
