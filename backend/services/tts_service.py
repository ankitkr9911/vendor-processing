from openai import OpenAI
import os
import base64
from typing import Optional

class TTSService:
    """Service for handling text-to-speech conversion using OpenAI's API"""
    
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
    def text_to_speech(self, text: str, voice: Optional[str] = "nova") -> str:
        """
        Convert text to speech using OpenAI's TTS API
        Args:
            text: The text to convert to speech
            voice: The voice to use (nova, alloy, echo, fable, onyx, or shimmer)
        Returns:
            Base64 encoded audio data
        """
        try:
            # Create speech from text using OpenAI's TTS API
            response = self.client.audio.speech.create(
                model="tts-1",
                voice=voice,
                input=text,
                speed=1.0
            )
            
            # Get the speech audio content
            audio_data = response.content
            
            # Convert to base64 for sending over HTTP
            audio_base64 = base64.b64encode(audio_data).decode('utf-8')
            
            return audio_base64
            
        except Exception as e:
            raise Exception(f"Failed to convert text to speech: {str(e)}")