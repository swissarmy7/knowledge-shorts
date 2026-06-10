"""
Supertonic Local TTS Service
Uses lightning-fast, on-device ONNX models for high-quality Korean narration.
Enhanced with natural breathing cues and optimized short-form speed/fidelity.
"""
import os
import re
import logging
import asyncio
import subprocess
from pathlib import Path
from typing import Optional
import soundfile as sf

# Import Supertonic TTS
from supertonic import TTS

logger = logging.getLogger("shorts")

# Voice Mapping: Map roles and short names to Supertonic voice styles
# Supertonic has styles like F1~F5 (Female) and M1~M5 (Male)
VOICE_STYLE_MAPPING = {
    # Short names
    "M1": "M1", # Teacher/Warm Male (Reliable, authoritative)
    "M2": "M2", # Youthful Male (Clear, active)
    "M3": "M3",
    "M4": "M4",
    "M5": "M5", # Child Male
    "F1": "F1", # Teacher/Calm Female (Intelligent, warm)
    "F2": "F2", # Youthful Female (Bright, curious)
    "F3": "F3",
    "F4": "F4",
    "F5": "F5", # Child Female
    
    # Legacy Google Chirp3 mapped names for backward compatibility
    "ko-KR-Chirp3-HD-Achird": "M1",
    "ko-KR-Chirp3-HD-Puck": "M2",
    "ko-KR-Chirp3-HD-Fenrir": "M5",
    "ko-KR-Chirp3-HD-Aoede": "F1",
    "ko-KR-Chirp3-HD-Leda": "F2",
    "ko-KR-Chirp3-HD-Kore": "F5",
}


def get_voice_name(char_id: str, gender: str, role: str, age_group: str = "young-adult") -> str:
    """
    Selects the best Supertonic style (M1~M5, F1~F5) for the character/narrator.
    This replaces the legacy Google TTS mapping.
    """
    # Direct style override (F1~F5, M1~M5) from customizable frontend select
    direct_key = str(gender).upper()
    if direct_key in ["M1", "M2", "M3", "M4", "M5", "F1", "F2", "F3", "F4", "F5"]:
        return direct_key

    if char_id == "char_cat":
        return "F5"  # Mascot -> Child Female

    gender_input = str(gender).lower()
    gender_key = "female" if "female" in gender_input else "male"
    age_input = str(age_group).lower()

    if gender_key == "female":
        if age_input in ["elder", "middle-aged"]:
            return "F1"  # Calm, intelligent middle-aged female (F1)
        elif age_input == "child":
            return "F5"  # Child female (F5)
        else:
            return "F2"  # Bright, youthful young-adult female (F2)
    else:
        if age_input in ["elder", "middle-aged"]:
            return "M1"  # Warm, reliable middle-aged male (M1)
        elif age_input == "child":
            return "M5"  # Child male (M5)
        else:
            return "M2"  # Clear, trendy youthful young-adult male (M2)


def preprocess_korean_text(text: str) -> str:
    """
    Cleans and preprocesses text for Supertonic TTS, 
    inserting natural human breathing cues (<breath>) at optimal intervals
    and emotion cues (<sigh>, <laugh>) dynamically based on keyword matching
    to make the narration sound exceptionally natural and less 'AI-like'.
    """
    # 1. Clean up existing tags to avoid duplication or confusion
    cleaned = text.replace("<breath>", "").replace("<sigh>", "").replace("<laugh>", "").strip()
    
    # 2. Split into sentences or clauses (using punctuation . ? !)
    parts = re.split(r'([.?!])', cleaned)
    
    processed_parts = []
    current_clause_len = 0
    
    # Emotion Keywords
    SIGH_KEYWORDS = ["에휴", "아쉬", "결국", "한숨", "슬픈", "안타까", "힘들", "어려운"]
    LAUGH_KEYWORDS = ["하하", "웃음", "재밌", "대박", "기쁜", "즐거", "ㅋㅋㅋ"]
    
    for i in range(0, len(parts) - 1, 2):
        sentence = parts[i]
        punctuation = parts[i+1]
        
        # Keyword detection for emotion tags
        has_sigh = any(kw in sentence for kw in SIGH_KEYWORDS)
        has_laugh = any(kw in sentence for kw in LAUGH_KEYWORDS)
        
        clause = sentence + punctuation
        if has_sigh:
            # Insert sigh cue at the beginning of the sentence
            clause = "<sigh> " + clause
        if has_laugh:
            # Insert laugh cue before the final punctuation
            clause = sentence + " <laugh>" + punctuation
            
        processed_parts.append(clause)
        current_clause_len += len(sentence)
        
        # If this isn't the absolute end, and we have spoken a substantial phrase (e.g. > 15 chars),
        # insert a natural breath cue to simulate realistic pauses and inhalations.
        if i < len(parts) - 3 and current_clause_len > 15:
            processed_parts.append(" <breath>")
            current_clause_len = 0  # Reset counter
            
    # Add any trailing text
    if len(parts) % 2 == 1:
        processed_parts.append(parts[-1])
        
    final_text = "".join(processed_parts).strip()
    # Normalize double spaces that might occur from tag injection
    final_text = re.sub(r"\s+", " ", final_text)
    logger.debug(f"[SupertonicPreprocess] Original: {text} -> Preprocessed: {final_text}")
    return final_text


class SupertonicLocalService:
    _instance = None
    _engine: Optional[TTS] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SupertonicLocalService, cls).__new__(cls)
        return cls._instance

    def _get_engine(self) -> TTS:
        if self._engine is None:
            logger.info("[SupertonicLocal] Initializing TTS engine...")
            self._engine = TTS()
            logger.info("[SupertonicLocal] TTS engine ready.")
        return self._engine

    async def generate_tts(self, text: str, voice_name: str, output_path: str, speed: float = 1.10) -> bool:
        """
        Synthesizes speech using local Supertonic model.
        Preprocesses text to insert natural human breathing cues.
        Optimized with custom speed and 10 steps for a clean, premium, engaging tone.
        Converts output WAV to MP3 to maintain compatibility.
        """
        try:
            # Map voice name to style string
            style_key = VOICE_STYLE_MAPPING.get(voice_name, "M2")
            logger.info(f"[SupertonicLocal] Synthesis: voice={voice_name} -> style={style_key} (speed={speed:.2f})")

            # Inject natural breaths into text
            natural_text = preprocess_korean_text(text)

            # Run in thread pool to avoid blocking event loop
            loop = asyncio.get_event_loop()
            engine = self._get_engine()
            
            # Get style object
            style = engine.get_voice_style(style_key)

            # synthesize parameters:
            # - speed: custom speed factor (natively computed, avoiding FFmpeg metallic distortion)
            # - total_steps: 10 (higher quality, cleaner pronunciations)
            # - silence_duration: 0.25 (short-form optimized spacing)
            wav_tuple = await loop.run_in_executor(
                None, 
                lambda: engine.synthesize(
                    text=natural_text, 
                    lang="ko", 
                    voice_style=style,
                    speed=speed,
                    total_steps=10,
                    silence_duration=0.25
                )
            )
            
            waveform, duration = wav_tuple
            
            # Save to temporary WAV file
            temp_wav = Path(output_path).with_suffix(".wav")
            # waveform[0] to get the 1D array
            sf.write(temp_wav, waveform[0], engine.sample_rate)

            # Convert WAV to MP3 using ffmpeg (non-blocking)
            try:
                await asyncio.to_thread(
                    subprocess.run,
                    [
                        "ffmpeg", "-y", "-i", str(temp_wav),
                        "-codec:a", "libmp3lame", "-qscale:a", "2",
                        str(output_path)
                    ],
                    capture_output=True, check=True
                )
                if os.path.exists(temp_wav):
                    os.remove(temp_wav)
                
                logger.info(f"[SupertonicLocal] OK: {output_path} generated ({duration[0]:.2f}s) from '{natural_text}'.")
                return True
            except subprocess.CalledProcessError as e:
                logger.error(f"[SupertonicLocal] FFmpeg conversion failed: {e.stderr.decode()}")
                return False

        except Exception as e:
            logger.error(f"[SupertonicLocal] Exception: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

# Global instance
_service = None

async def generate_supertonic_local(text: str, voice_name: str, output_path: str, speed: float = 1.10, **kwargs) -> bool:
    """Public API: generate TTS using local Supertonic model."""
    global _service
    if _service is None:
        _service = SupertonicLocalService()
    return await _service.generate_tts(text, voice_name, output_path, speed=speed)
