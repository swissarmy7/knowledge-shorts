"""
Google Cloud TTS Service
Uses Chirp 3.0 HD voices for maximum natural-sounding Korean speech.
"""
import os
import json
import base64
import logging
import asyncio
import httpx
from pathlib import Path
from google.oauth2 import service_account
from google.auth.transport.requests import Request
from backend.config import GOOGLE_APPLICATION_CREDENTIALS

logger = logging.getLogger("shorts")

# ======================================================================
# Chirp 3.0 HD Voice Pool (ko-KR) - Natural, human-like voices
# ======================================================================
# These voices do NOT support pitch/speakingRate adjustments.
# Voice differentiation comes from choosing different voice names.
# ======================================================================

CHIRP3_VOICES = {
    "male": {
        # Warm, authoritative, professorial
        "teacher": "ko-KR-Chirp3-HD-Achird",
        # Energetic, youthful
        "student": "ko-KR-Chirp3-HD-Puck",
        # Child-like
        "child": "ko-KR-Chirp3-HD-Fenrir",
    },
    "female": {
        # Calm, knowledgeable, clear
        "teacher": "ko-KR-Chirp3-HD-Aoede",
        # Bright, curious, youthful
        "student": "ko-KR-Chirp3-HD-Leda",
        # Child-like
        "child": "ko-KR-Chirp3-HD-Kore",
    },
    "mascot": "ko-KR-Chirp3-HD-Kore"
}


def get_voice_name(char_id: str, gender: str, role: str, age_group: str = "young-adult") -> str:
    """Select the best Chirp 3.0 HD voice for the character."""
    
    if char_id == "char_cat":
        return CHIRP3_VOICES["mascot"]

    gender_input = str(gender).lower()
    gender_key = "female" if "female" in gender_input else "male"

    role_input = str(role).lower()
    age_input = str(age_group).lower()
    
    if age_input == "child":
        role_key = "child"
    elif "teacher" in char_id or any(kw in role_input for kw in ["teacher", "professor", "doctor", "expert"]):
        role_key = "teacher"
    elif "student" in char_id or any(kw in role_input for kw in ["student", "pupil"]):
        role_key = "student"
    else:
        role_key = "teacher" if age_input in ["elder", "middle-aged"] else "student"

    voice = CHIRP3_VOICES[gender_key].get(role_key, CHIRP3_VOICES[gender_key]["student"])
    logger.info(f"[Voice] {char_id} ({gender}/{role}/{age_group}) -> {voice}")
    return voice


class GoogleTTSService:
    def __init__(self):
        self.credentials_path = GOOGLE_APPLICATION_CREDENTIALS
        if not self.credentials_path:
            raise ValueError("GOOGLE_APPLICATION_CREDENTIALS not found in environment")
        
        if not os.path.isabs(self.credentials_path):
            potential_path = Path("d:/workspace/test") / self.credentials_path
            if potential_path.exists():
                self.credentials_path = str(potential_path)

        self.credentials = service_account.Credentials.from_service_account_file(
            self.credentials_path,
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        self.client = httpx.AsyncClient()

    async def _get_access_token(self):
        """Refreshes and returns the access token."""
        if not self.credentials.valid:
            self.credentials.refresh(Request())
        return self.credentials.token

    async def generate_tts(self, text: str, voice_name: str, output_path: str) -> bool:
        """
        Synthesizes speech using Google Cloud TTS Chirp 3.0 HD.
        Uses v1beta1 endpoint (required for Chirp3-HD voices).
        Chirp3-HD does NOT support pitch or speakingRate parameters.
        """
        try:
            token = await self._get_access_token()
            
            # v1beta1 is REQUIRED for Chirp 3.0 HD voices
            url = "https://texttospeech.googleapis.com/v1beta1/text:synthesize"
            
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8"
            }
            
            payload = {
                "input": {"text": text},
                "voice": {
                    "languageCode": "ko-KR",
                    "name": voice_name
                },
                "audioConfig": {
                    "audioEncoding": "MP3",
                    "sampleRateHertz": 24000,
                }
            }
            
            max_retries = 3
            retry_delay = 2.0  # Initial delay for exponential backoff

            for attempt in range(max_retries):
                try:
                    response = await self.client.post(url, headers=headers, json=payload, timeout=60.0)
                    
                    if response.status_code == 200:
                        data = response.json()
                        audio_content = base64.b64decode(data["audioContent"])
                        with open(output_path, "wb") as out:
                            out.write(audio_content)
                        logger.info(f"[GoogleTTS] OK: {voice_name} -> {output_path} ({len(audio_content)} bytes)")
                        return True
                    elif response.status_code in [500, 502, 503, 504]:
                        logger.warning(f"[GoogleTTS] Transient Error {response.status_code} (Attempt {attempt + 1}/{max_retries}). Retrying in {retry_delay}s...")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(retry_delay)
                            retry_delay *= 2  # Exponential backoff
                            continue
                        else:
                            logger.error(f"[GoogleTTS] API Error: {response.status_code} after {max_retries} attempts - {response.text[:300]}")
                            return False
                    else:
                        logger.error(f"[GoogleTTS] API Error: {response.status_code} - {response.text[:300]}")
                        return False
                except (httpx.RequestError, asyncio.TimeoutError) as e:
                    logger.warning(f"[GoogleTTS] Request Exception {type(e).__name__} (Attempt {attempt + 1}/{max_retries}). Retrying in {retry_delay}s...")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2
                        continue
                    else:
                        logger.error(f"[GoogleTTS] Exception after {max_retries} attempts: {e}")
                        return False
                
        except Exception as e:
            logger.error(f"[GoogleTTS] Exception: {e}")
            return False


# Global instance
_service = None

async def generate_google_tts(text: str, voice_name: str, output_path: str, **kwargs) -> bool:
    """Public API: generate TTS using Chirp 3.0 HD. Extra kwargs are ignored for backward compat."""
    global _service
    if _service is None:
        _service = GoogleTTSService()
    return await _service.generate_tts(text, voice_name, output_path)
