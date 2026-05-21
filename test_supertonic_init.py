import sys
import logging
import os
from supertonic import TTS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("supertonic_test")

try:
    logger.info("Initializing Supertonic TTS (this may download models)...")
    # By default it uses the latest model (supertonic-3)
    engine = TTS()
    logger.info("Supertonic TTS initialized successfully!")
    
    text = "안녕하세요. 로컬 보이스 엔진 테스트 중입니다. 이 목소리는 서버에서 직접 생성되고 있습니다."
    logger.info(f"Generating test audio for: '{text}'")
    
    # supertonic 3 supports multiple languages, default is often English or detected
    # We specify language="ko" for Korean
    audio_data = engine.generate(text=text, language="ko")
    
    output_path = "test_supertonic.wav"
    with open(output_path, "wb") as f:
        f.write(audio_data)
        
    logger.info(f"Test audio saved to {output_path} (Size: {os.path.getsize(output_path)} bytes)")
    sys.exit(0)
except Exception as e:
    logger.error(f"Failed to initialize or run Supertonic: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
