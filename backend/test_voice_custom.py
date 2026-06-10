import asyncio
import logging
from pathlib import Path
import sys
import os

# backend 패키지를 import할 수 있도록 sys.path 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.narration_generator import generate_narration
from backend.services.supertonic_local_service import get_voice_name

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("shorts_test")

async def test_custom_voice():
    # output 디렉토리 밑에 임시 테스트용 작업 디렉토리 생성 (컨테이너 내 마운트된 경로)
    job_dir = Path("/app/output/test_job")
    job_dir.mkdir(exist_ok=True)
    
    # 1. 목소리 매핑 검증
    # F3 (청년 여성 - 차갑고 신비로운 톤)을 직접 인입시켰을 때 올바르게 F3가 매칭되는지 확인
    mapped_voice = get_voice_name(
        char_id="narrator",
        gender="F3",
        role="teacher",
        age_group="young-adult"
    )
    logger.info(f"Mapping Test: Input gender='F3' -> Mapped Voice Style: {mapped_voice}")
    assert mapped_voice == "F3", f"Expected F3, but got {mapped_voice}"
    
    # M1 (중년 남성 - 따뜻하고 신뢰감 있는 톤)을 직접 인입시켰을 때 올바르게 M1이 매칭되는지 확인
    mapped_voice_m1 = get_voice_name(
        char_id="narrator",
        gender="M1",
        role="teacher",
        age_group="young-adult"
    )
    logger.info(f"Mapping Test: Input gender='M1' -> Mapped Voice Style: {mapped_voice_m1}")
    assert mapped_voice_m1 == "M1", f"Expected M1, but got {mapped_voice_m1}"

    # 2. 실제 나레이션 합성 검증 (F3 목소리, 속도 1.12배 지정)
    text = "어젯밤 늦은 시간, 불이 꺼진 복도 끝에서 소름 끼치는 웃음소리가 들려왔다. 에휴, 그날 가지 말았어야 했는데."
    scene_id = 777
    
    logger.info("Generating local supertonic narration with custom voice F3 and speed 1.12...")
    result = await generate_narration(
        text=text,
        scene_id=scene_id,
        job_dir=job_dir,
        gender="F3",  # voice_category가 gender 파라미터로 흘러들어감
        role="teacher",
        age_group="young-adult",
        speed=1.12
    )
    
    if result["path"]:
        logger.info(f"Success! Custom voice narration generated at: {result['path']}")
        logger.info(f"Generated Audio Duration: {result['duration']:.2f}s")
        # 해당 경로 파일이 진짜 존재하는지 확인
        audio_file = Path(result["path"])
        if audio_file.exists():
            logger.info(f"File size: {audio_file.stat().st_size} bytes")
        else:
            logger.error("Audio file does not exist on disk!")
    else:
        logger.error("Failed to generate custom narration.")

if __name__ == "__main__":
    asyncio.run(test_custom_voice())
