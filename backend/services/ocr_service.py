import os
import re
import base64
import json
from typing import Dict, Any, Tuple, Optional, List
from openai import OpenAI
from PIL import Image
import io
import pytesseract
from pdf2image import convert_from_path
from dataclasses import dataclass

@dataclass
class OCRResult:
    text: str
    detected_language: str
    translated_text: str
    confidence: float

class OCRService:
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
    def encode_image_to_base64(self, image_path: str) -> str:
        """Convert image to base64 for OpenAI Vision API"""
        # If the file is a PDF, convert first page to image
        if image_path.lower().endswith('.pdf'):
            try:
                images = convert_from_path(image_path, first_page=1, last_page=1)
                if images:
                    # Save the first page as a temporary JPEG
                    temp_image_path = image_path + '_temp.jpg'
                    images[0].save(temp_image_path, 'JPEG')
                    with open(temp_image_path, "rb") as image_file:
                        base64_string = base64.b64encode(image_file.read()).decode('utf-8')
                    # Clean up temporary file
                    os.remove(temp_image_path)
                    return base64_string
            except Exception as e:
                print(f"PDF conversion failed: {e}")
                raise
        else:
            # Handle regular image files
            with open(image_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode('utf-8')
    
    def extract_text_with_tesseract(self, image_path: str, lang: str = 'eng+hin+tam+tel+kan+mal+pan+ben') -> str:
        """Fallback OCR using Tesseract with multi-language support"""
        try:
            image = Image.open(image_path)
            text = pytesseract.image_to_string(image, lang=lang)
            return text
        except Exception as e:
            print(f"Tesseract OCR failed: {e}")
            return ""

    # Voice-related methods
    async def transcribe_audio(self, audio_file_path: str) -> str:
        """Convert audio to text using OpenAI Whisper API"""
        try:
            with open(audio_file_path, "rb") as audio_file:
                transcription = await self.client.audio.transcriptions.acreate(
                    file=audio_file,
                    model="whisper-1"
                )
            return transcription.text
        except Exception as e:
            print(f"Audio transcription failed: {e}")
            return ""
    
    async def text_to_speech(self, text: str, voice: str = "nova") -> bytes:
        """Convert text to speech using OpenAI TTS API"""
        try:
            response = await self.client.audio.speech.acreate(
                model="tts-1",
                voice=voice,  # alloy, echo, fable, onyx, nova, shimmer
                input=text
            )
            return response.content
        except Exception as e:
            print(f"Text to speech failed: {e}")
            return b""

    async def detect_and_translate(self, image_path: str) -> OCRResult:
        """
        Detect text in any language and translate to English if needed
        Returns the original text, detected language, translated text, and confidence score
        """
        try:
            base64_image = self.encode_image_to_base64(image_path)
            
            # First, detect text and language
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Read the text in this image. Return a JSON with: 'text' (original text), 'language' (detected language), 'needs_translation' (true if not English). Be accurate with language detection."
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                response_format={ "type": "json_object" }
            )
            
            result = json.loads(response.choices[0].message.content)
            original_text = result.get('text', '')
            detected_language = result.get('language', 'unknown')
            needs_translation = result.get('needs_translation', False)
            
            translated_text = original_text
            if needs_translation and original_text:
                # Translate to English if needed
                translation_response = self.client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {
                            "role": "user",
                            "content": f"Translate this text to English while preserving any numbers, dates, and IDs exactly as they appear: {original_text}"
                        }
                    ]
                )
                translated_text = translation_response.choices[0].message.content
            
            return OCRResult(
                text=original_text,
                detected_language=detected_language,
                translated_text=translated_text,
                confidence=0.95 if response.choices[0].finish_reason == "stop" else 0.7
            )
            
        except Exception as e:
            print(f"OpenAI Vision API OCR failed: {e}")
            # Fallback to Tesseract
            text = self.extract_text_with_tesseract(image_path)
            return OCRResult(
                text=text,
                detected_language="unknown",
                translated_text=text,
                confidence=0.3
            )
    
    async def process_aadhaar_card(self, image_path: str) -> Tuple[Dict[str, Any], float]:
        """Process Aadhaar card and extract information using OpenAI Vision API with multilingual support"""
        try:
            # First, use our multilingual OCR to detect and translate text
            ocr_result = await self.detect_and_translate(image_path)
            base64_image = self.encode_image_to_base64(image_path)
            
            prompt = f"""
            Extract the following information from this Aadhaar card image:
            1. Full Name
            2. Aadhaar Number (12-digit number)
            3. Father's Name (if visible)
            4. Date of Birth
            5. Gender
            6. Address
            
            Original detected text: {ocr_result.text}
            English translation: {ocr_result.translated_text}
            Detected language: {ocr_result.detected_language}
            
            Return the information in the following JSON format:
            {{
                "name": "extracted name in English",
                "name_original": "name in original language if different from English",
                "aadhaar_number": "extracted aadhaar number",
                "father_name": "extracted father name in English or null",
                "father_name_original": "father's name in original language if different from English",
                "dob": "extracted date of birth in DD/MM/YYYY format",
                "gender": "Male/Female/Other",
                "address": "extracted address in English",
                "address_original": "address in original language if different from English",
                "detected_language": "{ocr_result.detected_language}",
                "confidence": {ocr_result.confidence}
            }}
            
            Keep all numbers, dates, and the Aadhaar number exactly as they appear in the original.
            If any field is not clearly visible or readable, set it to null.
            Provide a confidence score between 0.0 and 1.0 based on image quality and text clarity.
            """
            
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}",
                                    "detail": "high"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=500
            )
            
            # Parse the JSON response
            result_text = response.choices[0].message.content
            result_json = self._extract_json_from_response(result_text)
            
            # Validate Aadhaar number format
            if result_json.get('aadhaar_number'):
                result_json['aadhaar_number'] = self._validate_aadhaar_number(result_json['aadhaar_number'])
            
            confidence = result_json.pop('confidence', 0.8)
            return result_json, confidence
            
        except Exception as e:
            print(f"OpenAI Vision API failed: {e}")
            # Fallback to Tesseract + regex
            return await self._fallback_aadhaar_extraction(image_path)
    
    async def process_pan_card(self, image_path: str) -> Tuple[Dict[str, Any], float]:
        """Process PAN card and extract information using OpenAI Vision API with multilingual support"""
        try:
            # First, use our multilingual OCR to detect and translate text
            ocr_result = await self.detect_and_translate(image_path)
            base64_image = self.encode_image_to_base64(image_path)
            
            prompt = f"""
            Extract the following information from this PAN card image:
            1. Full Name
            2. PAN Number (10-character alphanumeric)
            3. Father's Name
            4. Date of Birth
            
            Original detected text: {ocr_result.text}
            English translation: {ocr_result.translated_text}
            Detected language: {ocr_result.detected_language}
            
            Return the information in the following JSON format:
            {{
                "name": "extracted name in English",
                "name_original": "name in original language if different from English",
                "pan_number": "extracted PAN number",
                "father_name": "extracted father name in English or null",
                "father_name_original": "father's name in original language if different from English",
                "dob": "extracted date of birth in DD/MM/YYYY format",
                "detected_language": "{ocr_result.detected_language}",
                "confidence": {ocr_result.confidence}
            }}
            
            Keep all numbers, dates, and the PAN number exactly as they appear in the original.
            If any field is not clearly visible or readable, set it to null.
            Provide a confidence score between 0.0 and 1.0 based on image quality and text clarity.
            """
            
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}",
                                    "detail": "high"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=500
            )
            
            # Parse the JSON response
            result_text = response.choices[0].message.content
            result_json = self._extract_json_from_response(result_text)
            
            # Validate PAN number format
            if result_json.get('pan_number'):
                result_json['pan_number'] = self._validate_pan_number(result_json['pan_number'])
            
            confidence = result_json.pop('confidence', 0.8)
            return result_json, confidence
            
        except Exception as e:
            print(f"OpenAI Vision API failed: {e}")
            # Fallback to Tesseract + regex
            return await self._fallback_pan_extraction(image_path)
    
    async def process_gst_certificate(self, image_path: str) -> Tuple[Dict[str, Any], float]:
        """Process GST certificate and extract information using OpenAI Vision API with multilingual support"""
        try:
            # First, use our multilingual OCR to detect and translate text
            ocr_result = await self.detect_and_translate(image_path)
            base64_image = self.encode_image_to_base64(image_path)
            
            prompt = f"""
            Extract the following information from this GST Certificate image:
            1. GSTIN (15-character alphanumeric)
            2. Legal Name of Business
            3. Trade Name (if different)
            4. Address
            5. State
            6. Registration Type
            7. Date of Registration
            8. Constitution of Business
            9. Name (of signing officer/authority)
            10. Designation (of signing officer/authority)
            11. Date of Issue
            
            Original detected text: {ocr_result.text}
            English translation: {ocr_result.translated_text}
            Detected language: {ocr_result.detected_language}
            
            Return the information in the following JSON format:
            {{
                "gstin": "extracted GSTIN number",
                "business_name": "extracted legal business name in English",
                "business_name_original": "business name in original language if different from English",
                "trade_name": "extracted trade name or null",
                "address": "extracted address in English",
                "address_original": "address in original language if different from English",
                "state": "extracted state name",
                "registration_type": "Regular/Composition/Casual/etc",
                "date_of_registration": "extracted date in DD/MM/YYYY format",
                "constitution_of_business": "Proprietorship/Partnership/Company/etc",
                "name": "name of signing officer/authority",
                "designation": "designation of signing officer/authority",
                "date_of_issue": "date of certificate issue in DD/MM/YYYY format",
                "detected_language": "{ocr_result.detected_language}",
                "confidence": {ocr_result.confidence}
            }}
            
            Keep all numbers, dates, and the GSTIN exactly as they appear in the original.
            If any field is not clearly visible or readable, set it to null.
            Provide a confidence score between 0.0 and 1.0 based on image quality and text clarity.
            """
            
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}",
                                    "detail": "high"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=600
            )
            
            # Parse the JSON response
            result_text = response.choices[0].message.content
            result_json = self._extract_json_from_response(result_text)
            
            # Validate GSTIN format
            if result_json.get('gstin'):
                result_json['gstin'] = self._validate_gstin(result_json['gstin'])
            
            confidence = result_json.pop('confidence', 0.8)
            return result_json, confidence
            
        except Exception as e:
            print(f"OpenAI Vision API failed: {e}")
            # Fallback to Tesseract + regex
            return await self._fallback_gst_extraction(image_path)
    
    def _extract_json_from_response(self, response_text: str) -> Dict[str, Any]:
        """Extract JSON from OpenAI response text"""
        try:
            # Try to find JSON in the response
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            
            if json_start != -1 and json_end != 0:
                json_str = response_text[json_start:json_end]
                return json.loads(json_str)
            else:
                raise ValueError("No JSON found in response")
        except Exception as e:
            print(f"Failed to parse JSON from response: {e}")
            return {}
    
    def _validate_aadhaar_number(self, aadhaar: str) -> Optional[str]:
        """Validate and clean Aadhaar number"""
        if not aadhaar:
            return None
        
        # Remove all non-digits
        aadhaar_clean = re.sub(r'\D', '', aadhaar)
        
        # Check if it's 12 digits
        if len(aadhaar_clean) == 12:
            return aadhaar_clean
        
        return None
    
    def _validate_pan_number(self, pan: str) -> Optional[str]:
        """Validate and clean PAN number"""
        if not pan:
            return None
        
        # Remove spaces and convert to uppercase
        pan_clean = pan.replace(' ', '').upper()
        
        # PAN format: 5 letters, 4 digits, 1 letter
        pan_pattern = r'^[A-Z]{5}[0-9]{4}[A-Z]{1}$'
        
        if re.match(pan_pattern, pan_clean):
            return pan_clean
        
        return None
    
    def _validate_gstin(self, gstin: str) -> Optional[str]:
        """Validate and clean GSTIN number"""
        if not gstin:
            return None
        
        # Remove spaces and convert to uppercase
        gstin_clean = gstin.replace(' ', '').upper()
        
        # GSTIN format: 2 digits (state code) + 10 chars PAN + 1 digit (entity number) + 1 letter (Z by default) + 1 alphanumeric (checksum)
        gstin_pattern = r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}[Z]{1}[0-9A-Z]{1}$'
        
        if re.match(gstin_pattern, gstin_clean) and len(gstin_clean) == 15:
            return gstin_clean
        
        return None
    
    async def _fallback_aadhaar_extraction(self, image_path: str) -> Tuple[Dict[str, Any], float]:
        """Fallback method using Tesseract OCR for Aadhaar"""
        text = self.extract_text_with_tesseract(image_path)
        
        # Extract Aadhaar number using regex
        aadhaar_pattern = r'\b\d{4}\s*\d{4}\s*\d{4}\b'
        aadhaar_match = re.search(aadhaar_pattern, text)
        aadhaar_number = self._validate_aadhaar_number(aadhaar_match.group()) if aadhaar_match else None
        
        # Extract other information using basic patterns
        result = {
            "name": None,
            "name_original": None,
            "aadhaar_number": aadhaar_number,
            "father_name": None,
            "father_name_original": None,
            "dob": None,
            "gender": None,
            "address": None,
            "address_original": None,
            "detected_language": "unknown"
        }
        
        return result, 0.5  # Lower confidence for fallback method
    
    async def _fallback_pan_extraction(self, image_path: str) -> Tuple[Dict[str, Any], float]:
        """Fallback method using Tesseract OCR for PAN"""
        text = self.extract_text_with_tesseract(image_path)
        
        # Extract PAN number using regex
        pan_pattern = r'\b[A-Z]{5}[0-9]{4}[A-Z]{1}\b'
        pan_match = re.search(pan_pattern, text)
        pan_number = pan_match.group() if pan_match else None
        
        result = {
            "name": None,
            "name_original": None,
            "pan_number": pan_number,
            "father_name": None,
            "father_name_original": None,
            "dob": None,
            "detected_language": "unknown"
        }
        
        return result, 0.5  # Lower confidence for fallback method
    
    async def _fallback_gst_extraction(self, image_path: str) -> Tuple[Dict[str, Any], float]:
        """Fallback method using Tesseract OCR for GST"""
        text = self.extract_text_with_tesseract(image_path)
        
        # Extract GSTIN using regex
        gstin_pattern = r'\b[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}[Z]{1}[0-9A-Z]{1}\b'
        gstin_match = re.search(gstin_pattern, text)
        gstin = self._validate_gstin(gstin_match.group()) if gstin_match else None
        
        result = {
            "gstin": gstin,
            "business_name": None,
            "business_name_original": None,
            "trade_name": None,
            "address": None,
            "address_original": None,
            "state_code": gstin[:2] if gstin else None,
            "state": None,
            "registration_type": None,
            "date_of_registration": None,
            "constitution_of_business": None,
            "taxpayer_type": None,
            "detected_language": "unknown"
        }
        
        return result, 0.5  # Lower confidence for fallback method