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
    visual_desc="South Park inspired flat cutout cartoon style. The boy pours a shiny golden stream of hot oil over a pile of crispy fried chicken from a small metal pitcher. A label reads 유린 on the pitcher.",
    scene_id=6,
    topic="중국집 메뉴 해독의 비밀 모르면 주문할 때 손해봅니다.",
    situation="",
    composition_mode="vertical",
    visual_style="south-park-comic",
    visual_bible_context="story_world: A bright, colorful South Park styled cartoon world centered around a bustling Chinese restaurant with glowing neon signs and huge menus | main_character: A young South Park style boy with large round white eyes, tiny black pupil dots, no nose, looking curious or hungry | wardrobe: A simple green winter jacket with a brown collar and yellow mittens, and a bright red beanie | primary_location: Inside a cozy cartoon Chinese restaurant with red lanterns hanging from the ceiling, round wooden tables, and a large chalkboard menu on the wall | fixed_props: A huge paper menu with bold Korean letters, a steaming white plate of food, and a set of wooden chopsticks | continuity_notes: The boys red beanie and green jacket must remain identical in every scene. The red lanterns and restaurant background should stay consistent when inside",
    full_story_arc="Scene 1: narration=중국집 메뉴판 앞에서 매번 당황하셨다면 이제 이 영상을 끝까지 보세요; visual_action=South Park inspired flat cutout cartoon style. A young boy with large round eyes, wearing a red beanie and gre || Scene 2: narration=어려운 중국집 메뉴판의 한자 몇 가지만 알면 주문이 정말 쉬워집니다; visual_action=South Park inspired flat cutout cartoon style. The boy points his finger with a bright bulb of idea above his || Scene 3: narration=가장 중요한 고기는 육이 돼지고기 기는 닭고기 우는 소고기라는 뜻입니다; visual_action=South Park inspired flat cutout cartoon style. Inside the restaurant. On a round wooden table, three caricatur || Scene 4: narration=그리고 달콤함을 뜻하는 탕과 새콤한 맛의 수는 소스를 결정해 줍니다; visual_action=South Park inspired flat cutout cartoon style. A dish of food is shown with sugar cubes and a slice of lemon s || Scene 5: narration=국물이 전혀 없이 바짝 졸여서 볶아낸 요리에는 깐풍이라는 말이 붙습니다; visual_action=South Park inspired flat cutout cartoon style. A chef tossing dry chicken in a wok with flames but no liquid s || Scene 6: narration=뜨거운 기름을 바삭바삭한 고기 위에 끼얹는 요리는 유린이라고 부릅니다; visual_action=South Park inspired flat cutout cartoon style. The boy pours a shiny golden stream of hot oil over a pile of c || Scene 7: narration=매콤한 맛을 내는 라와 길쭉하게 썬 조가 만나면 라조기가 완성됩니다; visual_action=South Park inspired flat cutout cartoon style. A funny red chili character wearing sunglasses is standing next || Scene 8: narration=가늘게 채 썬 요리를 뜻하는 슬과 귀한 세 가지 재료 삼도 기억해두세요; visual_action=South Park inspired flat cutout cartoon style. A plate showing neatly shredded vegetables and three sparkling || Scene 9: narration=이제 배운 글자들을 서로 조합해보면 처음 보는 메뉴의 맛도 척척 압니다; visual_action=South Park inspired flat cutout cartoon style. The boy sits at a table, eating a delicious plate of sweet and || Scene 10: narration=여러분이 중국집에서 가장 좋아하는 인생 최애 메뉴를 댓글로 적어주세요; visual_action=South Park inspired flat cutout cartoon st"
)

print("Generated Prompt:")
print(prompt)

client = genai.Client(
    vertexai=True,
    project="gen-lang-client-0334897248",
    location="us-central1"
)

output_path = Path("/var/www/html/my_shorts/output/cache/images/agy/90093d96aa7bb24e8a6886024f753797.png")
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
