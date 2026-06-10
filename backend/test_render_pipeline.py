import asyncio
import logging
from pathlib import Path
import sys
import os
import time
from PIL import Image

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.narration_generator import generate_narration
from backend.services.video_composer import compose_video

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("render_pipeline_test")

async def run_test():
    job_id = "test_opt_001"
    job_dir = Path("/app/output") / f"job_{job_id}"
    job_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. 더미 이미지 2장 생성 (Pillow)
    img1_path = job_dir / "scene_1.png"
    img2_path = job_dir / "scene_2.png"
    
    # 이라스토야 파스텔 톤 1080x1920 세로형 크기 이미지
    img1 = Image.new("RGB", (1080, 1920), color="#ffe4e1") # 분홍빛 파스텔
    img2 = Image.new("RGB", (1080, 1920), color="#e0ffff") # 하늘빛 파스텔
    img1.save(img1_path)
    img2.save(img2_path)
    
    logger.info(f"Dummy images created: {img1_path}, {img2_path}")
    
    # 2. TTS 음성 2개 생성 (1.15배 빠른 발화속도)
    logger.info("Generating narration audio tracks via Supertonic TTS...")
    narr1 = await generate_narration(
        text="어 최적화가 진짜 잘 되는지 한번 확인해 볼까요? 카툰썰토리 대박나자!",
        scene_id=1,
        job_dir=job_dir,
        gender="M2", # 남성 청년 톤
        role="teacher",
        age_group="young-adult",
        speed=1.15
    )
    
    narr2 = await generate_narration(
        text="웜 크림 액자와 카툰썰토리 엠블럼 배지가 아름답게 잘 들어갔는지 렌더링을 시작합니다.",
        scene_id=2,
        job_dir=job_dir,
        gender="F3", # 여성 청년 톤
        role="teacher",
        age_group="young-adult",
        speed=1.15
    )
    
    logger.info(f"Narration 1 duration: {narr1['duration']}s, path: {narr1['path']}")
    logger.info(f"Narration 2 duration: {narr2['duration']}s, path: {narr2['path']}")
    
    # 3. 비디오 장면 정보 구성
    scenes = [
        {
            "scene_id": 1,
            "character_id": "narrator",
            "script": "어 최적화가 진짜 잘 되는지 한번 확인해 볼까요? 카툰썰토리 대박나자!",
            "duration": narr1['duration'],
            "motion": "slow_push",
            "volume": 1.0,
            "overlays": []
        },
        {
            "scene_id": 2,
            "character_id": "narrator",
            "script": "웜 크림 액자와 카툰썰토리 엠블럼 배지가 아름답게 잘 들어갔는지 렌더링을 시작합니다.",
            "duration": narr2['duration'],
            "motion": "slow_push",
            "volume": 1.0,
            "overlays": []
        }
    ]
    
    images = [str(img1_path), str(img2_path)]
    narrations = [narr1, narr2]
    
    scenes_metadata = {
        "video_title": {
            "highlight": "카툰썰토리",
            "rest": "성능최적화렌더링테스트"
        },
        "subject": "최적화",
        "characters": [
            {
                "id": "narrator",
                "name": "내레이터",
                "description": "No visible presenter. Visual storytelling only.",
                "voice_category": "M2",
                "age_group": "adult",
                "color": "#d4ff00"
            }
        ]
    }
    
    # 4. 리모션 렌더링 시작 및 시간 계측
    start_time = time.time()
    logger.info("🚀 Remotion Video Composing started...")
    
    video_path = await compose_video(
        scenes=scenes,
        images=images,
        narrations=narrations,
        job_dir=job_dir,
        job_id=job_id,
        scenes_metadata=scenes_metadata,
        progress_callback=lambda p, msg: logger.info(f"Progress [{p*100:.1f}%]: {msg}")
    )
    
    elapsed = time.time() - start_time
    logger.info(f"✅ Video compose finished successfully!")
    logger.info(f"💾 Output Video: {video_path}")
    logger.info(f"⚡ Total Rendering Time: {elapsed:.2f} seconds")

if __name__ == "__main__":
    asyncio.run(run_test())
