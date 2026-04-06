import logging
import shutil
from pathlib import Path

logger = logging.getLogger("shorts")

try:
    from gradio_client import Client
except ImportError:
    Client = None

# Global cached client to avoid fetching API schema on every generation
_qwen_client = None

# Voice Mapping for Qwen CustomVoice
QWEN_VOICES = {
    "male": {
        "teacher": "Ryan",
        "student": "Dylan",
        "child": "Aiden"
    },
    "female": {
        "teacher": "Serena",
        "student": "Sohee",
        "child": "Ono_anna"
    },
    "mascot": "Uncle_fu" # Fun voice
}

def _get_qwen_speaker(char_id: str, gender: str, role: str, age_group: str) -> str:
    """Select the best speaker from the available 9 CustomVoice options."""
    if char_id == "char_cat":
        return QWEN_VOICES["mascot"]

    gender_key = "female" if "female" in str(gender).lower() else "male"
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

    speaker = QWEN_VOICES[gender_key].get(role_key, "Sohee")
    return speaker

def _get_qwen_instruct(speaker: str) -> str:
    """Generate completely fixed, strict English style instructions per speaker for 1.7B model."""
    
    # Base instructions enforcing absolute consistency and ignoring text emotion
    base_instruct = "Read the following text in a very natural, conversational tone. IMPORTANT: Maintain exactly the same voice, pitch, and energy level from start to finish. Do NOT change emotion based on the text. Do NOT overact. Speak cleanly and consistently. "
    
    if speaker == "Ryan":
        return base_instruct + "Your voice is a steady, clear male voice."
    elif speaker == "Dylan":
        return base_instruct + "Your voice is a steady, clear young male voice."
    elif speaker == "Aiden":
        return base_instruct + "Your voice is a steady, clear little boy voice."
    elif speaker == "Serena":
        return base_instruct + "Your voice is a steady, clear female voice."
    elif speaker == "Sohee":
        return base_instruct + "Your voice is a steady, clear young female voice."
    elif speaker == "Ono_anna":
        return base_instruct + "Your voice is a steady, clear little girl voice."
    elif speaker == "Uncle_fu":
        return base_instruct + "Your voice is a steady, clear, slightly fun voice."
    
    return base_instruct + "Speak with a steady, natural tone."

async def generate_qwen_tts(
    text: str,
    output_path: str,
    character_id: str,
    gender: str,
    role: str,
    age_group: str,
    model_size: str = "0.6B"
) -> bool:
    """
    Connects to the local Pinokio Qwen TTS (Gradio) instance.
    Uses model_size="1.7B", language="Korean".
    Calculates a consistent, deterministic seed based on speaker name to lock identity and speed.
    """
    if Client is None:
        logger.error("[QwenTTS] gradio_client is not installed. Fallback to Google.")
        return False
        
    speaker = _get_qwen_speaker(character_id, gender, role, age_group)
    instruct_prompt = _get_qwen_instruct(speaker)
    
    # Generate a fixed integer seed from the speaker name so they ALWAYS sound exactly the same
    import hashlib
    speaker_seed = int(hashlib.md5(speaker.encode()).hexdigest()[:8], 16)
    
    logger.info(f"[QwenTTS] Char:{character_id} -> Speaker:{speaker} | Prompt: {instruct_prompt}")
    
    global _qwen_client
    
    try:
        # Lazy initialize and cache the client to save massive overhead
        if _qwen_client is None:
            _qwen_client = Client("http://127.0.0.1:7860")
        
        result = _qwen_client.predict(
            text=text,
            language="Korean",
            speaker=speaker,
            instruct=instruct_prompt if model_size == "1.7B" else "",
            model_size=model_size,
            seed=speaker_seed,
            api_name="/generate_custom_voice"
        )
        
        # Result is a tuple: (filepath, status_str)
        generated_audio_path = result[0]
        status_msg = result[1]
        
        if not generated_audio_path:
            logger.error(f"[QwenTTS] Failed to generate: {status_msg}")
            return False
            
        # Move the generated file to our desired output path
        shutil.copy(generated_audio_path, output_path)
        logger.info(f"[QwenTTS] Success! Saved to {output_path}")
        return True
        
    except Exception as e:
        logger.warning(f"[QwenTTS] Connection/Generation failed: {e}. Falling back to Google.")
        return False
