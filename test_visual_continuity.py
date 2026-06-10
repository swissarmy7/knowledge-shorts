import sys
import types

# Unit tests do not call Gemini, but the production modules import google-genai at
# module import time. The host Python used by pytest may not have that package,
# so provide a tiny import stub for pure helper tests.
fake_google = types.ModuleType("google")
fake_genai = types.ModuleType("google.genai")
fake_types = types.ModuleType("google.genai.types")
setattr(fake_genai, "Client", lambda *args, **kwargs: None)
setattr(fake_types, "Tool", lambda *args, **kwargs: None)
setattr(fake_types, "GoogleSearch", lambda *args, **kwargs: None)
setattr(fake_types, "GenerateContentConfig", lambda *args, **kwargs: None)
setattr(fake_types, "Modality", types.SimpleNamespace(IMAGE="IMAGE"))
setattr(fake_google, "genai", fake_genai)
setattr(fake_genai, "types", fake_types)
sys.modules.setdefault("google", fake_google)
sys.modules.setdefault("google.genai", fake_genai)
sys.modules.setdefault("google.genai.types", fake_types)

from backend.services.script_generator import apply_visual_continuity_context
from backend.services.image_generator import build_structured_scene_prompt


def test_visual_bible_and_story_arc_are_attached_to_each_scene():
    script_data = {
        "subject": "예절",
        "visual_bible": {
            "story_world": "A Korean funeral hall etiquette lesson with solemn atmosphere.",
            "main_character": "The same Korean adult visitor with short black hair and a calm respectful expression.",
            "wardrobe": "A formal black mourning suit with a white shirt and no colorful accessories.",
            "primary_location": "The same quiet Korean funeral hall with pale wood floor and white chrysanthemum stands.",
            "fixed_props": "White chrysanthemum flowers and a low condolence altar without readable text.",
            "continuity_notes": "Never change into hanbok or casual bright clothing.",
        },
        "scenes": [
            {
                "scene_id": 1,
                "script": "장례식장에서는 먼저 차분히 입장해야 합니다.",
                "blackboard_content": "A visitor entering a funeral hall and preparing to bow.",
            },
            {
                "scene_id": 2,
                "script": "절할 때는 손 위치와 속도를 조심해야 합니다.",
                "blackboard_content": "The same visitor performing a respectful bow.",
            },
        ],
    }

    result = apply_visual_continuity_context(script_data, topic="장례식장 절 예절", direction="")

    for scene in result["scenes"]:
        assert "formal black mourning suit" in scene["visual_bible_context"]
        assert "Never change into hanbok" in scene["visual_bible_context"]
        assert "Scene 1:" in scene["full_story_arc"]
        assert "Scene 2:" in scene["full_story_arc"]


def test_image_prompt_prioritizes_global_continuity_over_local_action():
    prompt = build_structured_scene_prompt(
        visual_desc="The same visitor performing a respectful bow.",
        scene_id=2,
        topic="장례식장 절 예절",
        visual_style="modern-editorial",
        visual_bible_context=(
            "wardrobe: A formal black mourning suit with a white shirt and no colorful accessories | "
            "primary_location: The same quiet Korean funeral hall | "
            "continuity_notes: Never change into hanbok or casual bright clothing."
        ),
        full_story_arc="Scene 1: entering a funeral hall || Scene 2: bowing etiquette",
    )

    assert "Global Story Bible" in prompt
    assert "formal black mourning suit" in prompt
    assert "Never change into hanbok" in prompt
    assert "funeral etiquette means black mourning clothes" in prompt
    assert "Polished Korean editorial illustration" in prompt
