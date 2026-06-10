import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load .env
env_path = Path("/var/www/html/my_shorts/.env")
load_dotenv(env_path)

# Make credentials path absolute
creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
if creds:
    creds_path = Path(creds)
    if not creds_path.is_absolute():
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(Path("/var/www/html/my_shorts") / creds_path)

# Import genai
from google import genai
from google.genai import types

# Define prompt using build_structured_scene_prompt helper
sys.path.insert(0, "/var/www/html/my_shorts")
from backend.services.image_generator import build_structured_scene_prompt

prompt = build_structured_scene_prompt(
    visual_desc="South Park inspired flat cutout cartoon style. The young Korean man holds up a paper scroll with the Hanja characters 유 (油) (Oil), 린 (淋) (Pour), 라 (辣) (Spicy), and 슬 (絲) (Shredded) written on it inside the cozy Chinese restaurant.",
    scene_id=7,
    topic="중식메뉴판 마스터하기 한자어 몇개로 메뉴이해하기",
    situation="",
    composition_mode="vertical",
    visual_style="south-park-comic",
    visual_bible_context="story_world: A vibrant South Park inspired flat cutout cartoon world depicting a traditional Korean-style Chinese restaurant with red lanterns, wooden menus, and steam rising from dishes | main_character: A young Korean man with round black eyes, messy short black hair, wearing a simple t-shirt, looking confused and hungry | wardrobe: A simple plain blue t-shirt and grey pants in flat cutout texture | primary_location: Inside a cozy Chinese restaurant with dark wooden tables, red Chinese character decorations on the wall, and paper menu boards hanging | fixed_props: A wooden Chinese restaurant menu board with big Korean characters and matching Hanja, and a steaming plate of food | continuity_notes: Keep the characters facial style, shirt color, and the restaurants warm, red-toned flat cartoon aesthetic consistent throughout all scenes",
    full_story_arc="Scene 1: narration=중국집 메뉴판을 볼 때마다 매번 메뉴 선택에 실패하셨나요; visual_action=South Park inspired flat cutout cartoon style. A young Korean man with round black eyes, messy short black hai || Scene 2: narration=사실 비밀 한자 몇 가지만 알면 모든 요리의 맛이 다 보입니다; visual_action=South Park inspired flat cutout cartoon style. The young Korean man with round black eyes and messy short blac || Scene 3: narration=가장 먼저 고기 종류를 나타내는 육과 기 그리고 우를 배웁시다; visual_action=South Park inspired flat cutout cartoon style. The young Korean man stands next to a wooden menu board. On the || Scene 4: narration=여기서 육은 돼지고기이며 기는 닭고기이고 우는 소고기입니다; visual_action=South Park inspired flat cutout cartoon style. A split screen showing three funny cartoon ingredients: a cute || Scene 5: narration=다음으로 조리 방식을 결정하는 탕과 수 그리고 깐을 봅시다; visual_action=South Park inspired flat cutout cartoon style. The young Korean man points at a steaming wok where a chef is c || Scene 6: narration=탕은 달콤함을 의미하고 수는 새콤함을 깐은 국물 없음을 뜻해요; visual_action=South Park inspired flat cutout cartoon style. A split screen showing a jar of sweet honey (탕), a bottle of so || Scene 7: narration=마지막으로 유와 린 그리고 라와 슬도 메뉴판에 자주 나옵니다; visual_action=South Park inspired flat cutout cartoon style. The young Korean man holds up a paper scroll with the Hanja cha || Scene 8: narration=유린은 기름을 끼얹는 방식이며 라는 매콤한 맛을 표현합니다; visual_action=South Park inspired flat cutout cartoon style. A cartoon oil bottle pouring golden oil (유) onto a crispy chicken || Scene 9: narration=이제 탕수육은 달콤하고 새콤한 돼지고기 요리로 바로 읽힙니다; visual_action=South Park inspired flat cutout cartoon style. The young Korean man happily eats a plate of crispy, glossy swe || Scene 10: narration=그렇다면 오늘 배운 깐풍기는 어떤 요리일지 댓글에 남겨주세요; visual_action=South Park inspired flat cutout cartoon style. The young Korean man holds a steaming plate of d"
)

print("Generated Prompt:")
print(prompt)

client = genai.Client(
    vertexai=True,
    project="gen-lang-client-0334897248",
    location="us-central1"
)

output_path = Path("/var/www/html/my_shorts/output/cache/images/agy/08755403f810074b13295d2d054154e9.png")
output_path.parent.mkdir(parents=True, exist_ok=True)

models_to_try = [
    'imagen-3.0-generate-002',
    'imagen-4.0-generate-001',
    'imagen-4.0-fast-generate-001',
    'imagen-3.0-generate-001'
]

success = False
for model in models_to_try:
    print(f"Calling Vertex AI generate_images with model {model}...")
    try:
        response = client.models.generate_images(
            model=model,
            prompt=prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio="9:16",
                output_mime_type="image/png"
            )
        )
        if hasattr(response, 'generated_images') and response.generated_images:
            img_bytes = response.generated_images[0].image.image_bytes
            output_path.write_bytes(img_bytes)
            print(f"SUCCESS: Saved generated image to {output_path} using model {model}")
            success = True
            break
        else:
            print(f"WARNING: No images generated in response for model {model}.")
    except Exception as e:
        print(f"WARNING: Failed with model {model}: {e}")

if not success:
    print("ERROR: All models failed.")
    sys.exit(1)
