"""
Supertonic Local TTS Service
Uses lightning-fast, on-device ONNX models for high-quality Korean narration.
"""
import os
import logging
import asyncio
import subprocess
from pathlib import Path
from typing import Optional
import soundfile as sf
import io

# Import Supertonic TTS
from supertonic import TTS

logger = logging.getLogger("shorts")

# Voice Mapping: Map Google Chirp3 roles to Supertonic voice styles
# Supertonic 3 has styles like F1~F5 (Female) and M1~M5 (Male)
VOICE_STYLE_MAPPING = {
    "ko-KR-Chirp3-HD-Achird": "M1", # Teacher/Warm Male
    "ko-KR-Chirp3-HD-Puck": "M2",   # Youthful Male
    "ko-KR-Chirp3-HD-Fenrir": "M5", # Child-like Male
    "ko-KR-Chirp3-HD-Aoede": "F1",  # Teacher/Calm Female
    "ko-KR-Chirp3-HD-Leda": "F2",   # Youthful Female
    "ko-KR-Chirp3-HD-Kore": "F5",   # Child-like Female
}

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

    async def generate_tts(self, text: str, voice_name: str, output_path: str) -> bool:
        """
        Synthesizes speech using local Supertonic model.
        Converts output WAV to MP3 to maintain compatibility.
        """
        try:
            # Map voice name to style string
            style_key = VOICE_STYLE_MAPPING.get(voice_name, "F1")
            logger.info(f"[SupertonicLocal] Synthesis: voice={voice_name} -> style={style_key}")

            # Run in thread pool to avoid blocking event loop
            loop = asyncio.get_event_loop()
            engine = self._get_engine()
            
            # Get style object
            style = engine.get_voice_style(style_key)

            # synthesize returns (waveform_ndarray, duration_ndarray)
            # waveform is (1, num_samples)
            wav_tuple = await loop.run_in_executor(
                None, 
                lambda: engine.synthesize(
                    text=text, 
                    lang="ko", 
                    voice_style=style
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
                
                logger.info(f"[SupertonicLocal] OK: {output_path} generated ({duration[0]:.2f}s).")
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

async def generate_supertonic_local(text: str, voice_name: str, output_path: str, **kwargs) -> bool:
    """Public API: generate TTS using local Supertonic model."""
    global _service
    if _service is None:
        _service = SupertonicLocalService()
    return await _service.generate_tts(text, voice_name, output_path)
