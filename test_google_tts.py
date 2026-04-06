import asyncio
from pathlib import Path
from backend.services.google_tts_service import generate_google_tts

async def test_voices():
    test_dir = Path("d:/workspace/test/temp/tts_test")
    test_dir.mkdir(parents=True, exist_ok=True)
    
    voices = {
        "Teacher_Male": "ko-KR-Wavenet-C",
        "Teacher_Female": "ko-KR-Wavenet-B",
        "Student_Male": "ko-KR-Neural2-C",
        "Student_Female": "ko-KR-Neural2-B",
        "Mascot": "ko-KR-Neural2-A"
    }
    
    text = "안녕하세요! 구글 클라우드 텍스트 투 스피치 테스트 중입니다. 이 목소리는 어떤가요? 마음에 드시나요?"
    
    print("🚀 Starting Google TTS Voice Test...")
    
    for name, voice_id in voices.items():
        output_path = test_dir / f"test_{name}.mp3"
        print(f"🎙️ Generating for {name} ({voice_id})...")
        success = await generate_google_tts(text, voice_id, str(output_path))
        if success:
            print(f"✅ Saved to {output_path}")
        else:
            print(f"❌ Failed for {name}")

if __name__ == "__main__":
    asyncio.run(test_voices())
