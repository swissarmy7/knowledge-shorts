import asyncio
from pathlib import Path
from backend.services.google_tts_service import generate_google_tts

async def test_fine_tuned_voices():
    test_dir = Path("d:/workspace/test/temp/tts_fine_tune_test")
    test_dir.mkdir(parents=True, exist_ok=True)
    
    # Matching the mapping in narration_generator.py
    voice_configs = {
        "Teacher_Male": {"name": "ko-KR-Wavenet-C", "pitch": -2.0, "rate": 1.02},
        "Teacher_Female": {"name": "ko-KR-Wavenet-B", "pitch": -1.0, "rate": 1.02},
        "Student_Male": {"name": "ko-KR-Neural2-C", "pitch": 0.5, "rate": 1.08},
        "Student_Female": {"name": "ko-KR-Neural2-B", "pitch": 1.0, "rate": 1.08},
        "Mascot_Cat": {"name": "ko-KR-Neural2-A", "pitch": 4.0, "rate": 1.12}
    }
    
    text = "안녕하세요! 구글 클라우드 미세 조정 테스트입니다. 제 목소리 톤이 어떤가요? 마음에 드시나요?"
    
    print("🚀 Starting Google TTS Fine-Tuning Test...")
    
    for name, config in voice_configs.items():
        output_path = test_dir / f"fine_tuned_{name}.mp3"
        print(f"🎙️ Generating for {name} (Pitch:{config['pitch']}, Rate:{config['rate']})...")
        success = await generate_google_tts(
            text=text, 
            voice_name=config['name'], 
            output_path=str(output_path),
            pitch=config['pitch'],
            speaking_rate=config['rate']
        )
        if success:
            print(f"✅ Saved to {output_path}")
        else:
            print(f"❌ Failed for {name}")

if __name__ == "__main__":
    asyncio.run(test_fine_tuned_voices())
