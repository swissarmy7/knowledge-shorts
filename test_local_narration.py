import asyncio
import logging
from pathlib import Path
from backend.services.narration_generator import generate_narration

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("shorts")

async def test_local_narration():
    job_dir = Path("test_job")
    job_dir.mkdir(exist_ok=True)
    
    text = "이제 구글 API 없이도 우리 서버에서 직접 목소리를 만들 수 있습니다. 훨씬 경제적이고 빠르죠!"
    scene_id = 999
    
    logger.info("Testing local supertonic narration...")
    result = await generate_narration(
        text=text,
        scene_id=scene_id,
        job_dir=job_dir,
        gender="female",
        role="student"
    )
    
    if result["path"]:
        logger.info(f"Success! Audio generated at: {result['path']}")
        logger.info(f"Duration: {result['duration']:.2f}s")
    else:
        logger.error("Failed to generate local narration.")

if __name__ == "__main__":
    asyncio.run(test_local_narration())
