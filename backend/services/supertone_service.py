import httpx
import os
from backend.config import SUPER_TONE_API_KEY

async def generate_supertone_tts(text, voice_id, output_path):
    """
    Generate Korean TTS using Supertone API (sona_speech_2_flash).
    """
    url = f"https://supertoneapi.com/v1/text-to-speech/{voice_id}"
    
    headers = {
        "x-sup-api-key": SUPER_TONE_API_KEY,
        "Content-Type": "application/json"
    }
    
    payload = {
        "text": text,
        "language": "ko",
        "style": "neutral",
        "model": "sona_speech_2_flash",
        "voice_settings": {
            "pitch_shift": 0,
            "pitch_variance": 1.1, # Slightly boosted for natural melody
            "speed": 1.0
        }
    }
    
    # Requesting mp3 format directly
    params = {"output_format": "mp3"}
    
    async with httpx.AsyncClient() as client:
        import logging
        logger = logging.getLogger("shorts")
        logger.info(f"[SupertoneAPI] Request: voice_id={voice_id}, text='{text[:30]}...'")
        
        response = await client.post(url, headers=headers, json=payload, params=params, timeout=60.0)
        
        if response.status_code == 200:
            with open(output_path, "wb") as f:
                f.write(response.content)
            return True
        else:
            print(f"Supertone API Error: {response.status_code} - {response.text}")
            return False
