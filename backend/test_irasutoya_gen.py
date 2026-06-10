import asyncio
import sys
import os

# backend 패키지를 import할 수 있도록 sys.path 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.script_generator import generate_script

async def test_irasutoya_prompt():
    print("Testing Ssul-Shorts Irasutoya script generation...")
    
    # 썰 쇼츠 스타일과 장면 개수 3개로 짧게 생성 요청
    topic = "조선시대 야간 순찰대(순라군)의 무서운 야간 근무 썰"
    direction = "오싹하고 재미있는 미스터리 풍으로 전개해줘."
    
    result = await generate_script(
        topic=topic,
        direction=direction,
        style="ssul-shorts",
        scene_count=3
    )
    
    print("\n--- Generated Script Metadata ---")
    print(f"Title: {result.get('video_title')}")
    print(f"Subject: {result.get('subject')}")
    
    print("\n--- Generated Scenes & Visual Prompts ---")
    for scene in result.get("scenes", []):
        print(f"\n[Scene {scene.get('scene_id')}]")
        print(f"Script: {scene.get('script')}")
        print(f"Visual Prompt (blackboard_content):")
        print(f"  => {scene.get('background_description') or scene.get('blackboard_content')}")
        
        # 이라스토야 고유 스타일 규칙들이 들어있는지 검증
        prompt = scene.get('background_description') or scene.get('blackboard_content') or ""
        has_irasutoya_style = "Irasutoya" in prompt
        has_ratio = "--ar 9:16" in prompt
        
        print(f"  - Irasutoya style key matching: {has_irasutoya_style}")
        print(f"  - Ratio '--ar 9:16' matching: {has_ratio}")

if __name__ == "__main__":
    async def main():
        try:
            await test_irasutoya_prompt()
        except Exception as e:
            print(f"Error during test: {e}")
            import traceback
            traceback.print_exc()

    asyncio.run(main())
