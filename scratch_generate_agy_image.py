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

visual_desc = "South Park cutout cartoon style. A character with big circular eyes looks completely confused in front of a giant Korean-Chinese restaurant menu filled with complex names. A small speech bubble above their head says 뭐 먹지?.."
visual_bible_context = "story_world: A vibrant and colorful South Park inspired 2D cutout world depicting various scenes in and around a cozy Korean-Chinese restaurant | main_character: No recurring main character on screen, focusing entirely on visual elements, text overlays, food items, and restaurant background setups | wardrobe: No main character present, so wardrobe is not applicable | primary_location: A typical Korean-Chinese restaurant interior with red lanterns, wooden tables, a large handwritten menu on the wall, and plates of delicious food | fixed_props: Chinese restaurant menus, red lanterns, chopsticks, white ceramic plates, and stylized Korean-Chinese dishes | continuity_notes: Maintain the consistent flat cutout cartoon style with thick black outlines, bold colors, and humorous situations throughout all scenes"
full_story_arc = "Scene 1: narration=중국집 메뉴판 보고 당황한 적 많으시죠. 이 공식만 알면 메뉴가 바로 보입니다; visual_action=South Park cutout cartoon style. A character with big circular eyes looks completely confused in front of a gi || Scene 2: narration=그동안 요리 이름이 너무 헷갈려서 늘 먹던 짜장면만 주문했다면 집중하세요; visual_action=South Park cutout cartoon style. A table with a simple black bowl of Jjajangmyeon, and the character eating it || Scene 3: narration=가장 먼저 요리 이름에 육이 들어가면 돼지고기 기는 닭고기를 뜻합니다; visual_action=South Park cutout cartoon style. A split screen. On the left, a cute flat cartoon pig next to the large Korean || Scene 4: narration=여기에 탕이라는 글자는 달콤한 설탕을 수라는 글자는 새콤한 식초를 말해요; visual_action=South Park cutout cartoon style. A cartoon sugar bowl with the letter 탕(糖) pouring sugar onto a plate, and a c || Scene 5: narration=그리고 깐이라는 글자는 국물이 없이 볶는 것이고 풍은 소스를 졸인 방식입니다; visual_action=South Park cutout cartoon style. A cartoon chef tossing a wok over high flames with no sauce splashing out, la || Scene 6: narration=또한 유린은 뜨거운 기름을 끼얹는 요리이고 라는 매콤한 맛을 의미합니다; visual_action=South Park cutout cartoon style. A flat ladle pouring hot golden oil over a crispy chicken dish, labeled 유린(油淋 || Scene 7: narration=마지막으로 슬은 재료를 실처럼 가늘게 채 썬 것이며 삼은 해산물 삼선입니다; visual_action=South Park cutout cartoon style. A wooden cutting board with vegetables chopped into thin threads, labeled 슬(絲 || Scene 8: narration=이제 배운 단어를 조합하면 탕수육은 달고 신 소스의 돼지고기 요리가 됩니다; visual_action=South Park cutout cartoon style. A delicious plate of sweet and sour pork, with colorful cartoon labels floati || Scene 9: narration=같은 원리로 깐풍기는 국물 없이 맵게 졸여낸 닭고기 요리라는 뜻이 됩니다; visual_action=South Park cutout cartoon style. A plate of spicy crispy chicken, with labels: 깐(마르게) + 풍(볶은) + 기(닭) combining || Scene 10: narration=오늘 배운 단어 조합으로 다음에 주문하고 싶은 요리를 댓글에 써주세요; visual_action=South Park cutout car"

prompt = build_structured_scene_prompt(
    visual_desc=visual_desc,
    scene_id=1,
    topic="중국집 메뉴판 마스터하기 이것만 알면 주문이 쉬워진다.",
    situation="",
    composition_mode="vertical",
    visual_style="south-park-comic",
    visual_bible_context=visual_bible_context,
    full_story_arc=full_story_arc
)

print("Generated Prompt:")
print(prompt)

client = genai.Client(
    vertexai=True,
    project="gen-lang-client-0334897248",
    location="us-central1"
)

output_path = Path("/var/www/html/my_shorts/output/cache/images/agy/d99fb23069aa0c1ec611d982440f12b1.png")
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
