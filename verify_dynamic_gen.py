
import asyncio
import json
from backend.services.script_generator import generate_script

async def test_generation():
    print("Testing dynamic script generation...")
    topic = "The Battle of Waterloo"
    result = await generate_script(topic)
    
    print("\n--- Generated Script Metadata ---")
    print(f"Title: {result.get('video_title')}")
    print(f"Situation Setting: {json.dumps(result.get('situation_setting'), indent=2, ensure_ascii=False)}")
    
    print("\n--- Generated Characters ---")
    for char in result.get("characters", []):
        print(f"ID: {char.get('id')}, Name: {char.get('name')}, Category: {char.get('voice_category')}")
        print(f"Description: {char.get('description')}")
    
    print("\n--- Scenes ---")
    for scene in result.get("scenes", []):
        print(f"Scene {scene.get('scene_id')}: {scene.get('character')} ({scene.get('character_id')}) @ {scene.get('background')}")
        print(f"Motion/Scene Info: {scene.get('motion')}")
        print(f"Script: {scene.get('script')[:30]}...")
        print(f"English BG: {scene.get('background_description')[:50]}...")

if __name__ == "__main__":
    async def main():
        try:
            await test_generation()
        except Exception as e:
            print(f"Error during test: {e}")
            import traceback
            traceback.print_exc()

    asyncio.run(main())
