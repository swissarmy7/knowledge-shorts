"""
Script Generator Service
Uses Gemini API to generate scripts and scene plans from a topic.
Includes web search grounding for factual accuracy.
"""
import json
import re
import logging
from google import genai
from google.genai import types
from backend.config import GOOGLE_GEMINI_API

logger = logging.getLogger("shorts")

client = genai.Client(api_key=GOOGLE_GEMINI_API)


# =============================================================================
# SYSTEM PROMPTS - 교육 숏폼 대화 스크립트 생성 전문 프롬프트
# =============================================================================
# SYSTEM PROMPTS - 교육 숏폼 대화 스크립트 생성 전문 프롬프트
# =============================================================================

# --- 공통 규칙 (두 모드 모두 적용) ---
COMMON_RULES = """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
캐릭터 설정 가이드 (Dynamic Roles & Visual Consistency)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

영상 전체에서 캐릭터의 외형이 일관되게 유지되어야 합니다. 또한, 주제(Topic)와 의도(Direction)에 따라 가장 적절한 '직업'과 '역할'을 부여하세요.
이미 특정 캐릭터 설정(이름, 성별, 나이 등)이 지시사항에 포함되어 있다면 이를 최우선으로 준수하세요.

- **char_teacher (메인 화자 / 전문가 A)**: 주제에 가장 전문적인 인물. (예: 역사-교수님, 요리-쉐프, 경제-자산관리사 등)
- **char_student (서브 화자 / 동료 전문가 B 또는 학습자)**: 대화 상대. (예: 역사-학생, 요리-수자제/견습생, 경제-동료 애널리스트 등)
- **이름(name)**: 주제에 어울리는 직함이나 이름을 부여하되, 지시에 포함된 이름이 있다면 반드시 그 이름을 사용하세요.
- **description (외형 묘사)**: 캐릭터의 성별, 연령, 직업에 어울리는 구체적이고 고정적인 복장(영문)을 작성하세요. 반드시 머리 스타일, 눈 색깔, 얼굴형 등을 포함하여 **모든 장면에서 100% 동일한 외형이 유지**되도록 '고정된 기준(Anchor)' 역할을 하는 묘사여야 합니다. 
- **Visual Consistency Rules**: 
  - 캐릭터의 피부색이나 머리색 등이 장면의 배경에 따라 변해서는 안 됩니다.
  - 옷차림(Profession-appropriate attire)을 한 번 정하면 끝까지 유지하세요.
- **age_group**: MUST be [young-adult]. (Always use 20s~30s, vibrant, youthful. Absolutely FORBIDDEN: 'middle-aged', 'elder', 'old man', 'gray hair', 'senile traits').
- **IDs**: 반드시 `char_teacher`와 `char_student` ID를 사용.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
상황 및 배경 설정 (Dynamic Scene Context)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

주제와 캐릭터의 역할에 완벽하게 어울리는 장소와 상황을 설정하세요.
- **Time/Situation**: 주제에 적합한 공간 (예: 요리-주방, 과학-연구소, 역사-박물관/유적지, 경제-증권가 등)
- **Background Matching**: 씬마다 배경(`background`)과 상세 묘사(`background_description`)를 설정하되, 해당 장면의 대화 내용에 등장하는 구체적인 사물이나 상황이 반영되도록 하세요.
- **Background Constraint**: `background_description`에는 캐릭터의 외형(얼굴, 옷 등)에 대한 묘사를 절대 포함하지 마세요. 이는 배경 정보일 뿐이며, 캐릭터 묘사는 `characters` 리스트의 정보를 따릅니다.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
JSON 출력 형식 (마크다운 코드블록 없이 순수 JSON만)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{
    "video_title": {
        "highlight": "첫 장면에 노출될 '노란색 강조' 제목 (최대 13자). 시청자의 뇌를 자극하는 '후킹' 단어 위주.",
        "rest": "강조 부분 뒤에 이어지는 '흰색' 제목 (최대 18자). 구체적인 맥락 제공."
    },
    "subject": "주제 분류 (단일 단어, 박스 안에 표시될 핵심 카테고리. 허용 예시: 경제, 수학, 과학, 역사, 사회, 인문학, IT, 자기계발, 건강 등)",
    "youtube_title": "SEO 최적화 제목 (#Shorts 포함)",
    "youtube_description": "매력적인 영상 설명 (해시태그 포함)",
    "youtube_tags": ["태그1", "태그2", "... 핵심 태그 10~15개"],
    "core_knowledge": "핵심 지식/메시지 요약",
    "situation_setting": {
        "time_period": "시대적 배경 (한글)",
        "situation": "상황 설정 (한글). 주제와 역할의 연관성 설명.",
        "concept": "분위기/컨셉 (한글)"
    },
    "characters": [
        {
            "id": "char_teacher",
            "name": "주제에 맞는 직함/이름 (예: 요리사 성진, 김 대리 등)",
            "description": "English physical description including modern, trendy, and youthful professional attire. Focus on 20s-30s youthful look.",
            "voice_category": "male 또는 female",
            "age_group": "young-adult",
            "color": "#HEX"
        },
        {
            "id": "char_student",
            "name": "주제에 맞는 직함/이름 (예: 수제자 민수, 신입사원 지은 등)",
            "description": "English physical description including youthful modern look. Focus on early 20s.",
            "voice_category": "male 또는 female",
            "age_group": "young-adult",
            "color": "#HEX"
        }
    ],
    "scenes": [
        {
            "scene_id": 1,
            "character_id": "char_teacher 또는 char_student",
            "character": "캐릭터 성함/직함 (한글, characters 리스트의 name과 일치)",
            "background": "배경 장소 (한글, 주제에 맞는 구체적 장소)",
            "background_description": "Detailed English description of the background, reflecting the scene's script content",
            "motion": "캐릭터의 동작 (한글)",
            "script": "대사 (구어체, 순수 대사만)",
            "duration": 5
        }
    ]
}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
후킹 타이틀 제작 전략 (YouTube Click-Bait Strategy)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
타이틀은 단순히 주제를 설명하는 것이 아니라, 시청자가 1초 만에 멈추게 하는 '갈고리'입니다. 

1. **Highlight (노란색 글자 - 시각적 충격)**:
   - **기법**: 의문형, 부정형, 충격적 사실, 강력한 형용사 사용.
   - **Good**: "99%가 틀림", "이 걸 몰랐어?", "충격적인 정체", "절대 하지마", "이건 마법임"
   - **Bad**: "세종대왕 정보", "지구의 나이", "커피의 효능" (너무 평범함)
   
2. **Rest (흰색 글자 - 호기심 충족)**:
   - 강조 문구 뒤에 붙어 무엇에 관한 내용인지 본능적으로 이해하게 만듭니다.
   - **Good**: "우리가 속은 소금의 진실", "삼성도 모르는 비밀 무기", "내일부터 당장 연봉 오름"
   
3. **Subject (주제 카테고리)**:
   - 복잡한 설명 대신 시청자가 콘텐츠의 '분야'를 즉각적으로 인지하게 하는 단일 키워드여야 합니다.
   - **Allowed**: "경제", "과학", "역사", "수학", "사회", "인문학", "IT", "건강" 등
   - **Bad**: "역설 경제", "미친 팩트", "지식 카타르시스" (너무 추상적임)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
스크립트 품질 및 정보 전달 규칙 (CRITICAL)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. **타이틀 퀄리티**: `video_title`은 영상의 얼굴입니다. 위 후킹 전략을 사용하여 검색량 높은 키워드와 자극적인 문구를 조합하세요.
2. **지식 밀도 극대화**: "대박!", "와!", "정말요?" 같은 단순 감탄사 비중을 15% 이하로 낮추고, 모든 씬에서 실질적인 정보(수치, 원인, 결과, 핵심 개념 등)가 한 문장 이상 포함되어야 합니다.
3. **정보 소우선 순위**: 유저가 제공한 '의도/방향(User Info)' 정보가 구체적일 경우, 해당 정보를 **절차와 논리에 맞춰 가공하는 데 집중**하세요. 임의로 내용을 축약하지 말고 모든 핵심 팩트를 다이얼로그에 녹여내세요.
4. **영상 길이 필수 준수**: 총 영상 길이 **30~85초** 내외. 씬 개수 **정확히 {scene_count}개**.
5. **대화의 리듬**: 정보가 많더라도 지루하지 않게 "그게 왜 그런 거죠?", "사실 이건 ~이기 때문입니다"와 같은 인과관계를 중심으로 자연스러운 핑퐁 대화를 유지하세요.
6. **마무리(Outro)**: 마지막 씬은 반드시 지식의 핵심을 한 줄 요약하며 채널 구독/좋아요 유도 멘트로 마무리.
7. **감탄사/말줄임표 금지**: TTS 품질을 위해 "오", "아", "헐" 등 단독 감탄사와 `...` 사용 금지. 문장 끝에는 반드시 명확한 마침표(.)나 물음표(?)를 사용하세요.
"""


# =============================================================================
# MODE A: 전문가/학습자 대화 (Expert-Learner) - (구) 선생님/학생 모드
# =============================================================================
TEACHER_STUDENT_PROMPT = """당신은 교육용 숏폼 전문 스크립트 작가입니다. 
지식을 전달하는 **전문가(Expert)**와 시청자를 대변하여 호기심 가득한 질문을 던지는 **학습자(Learner)**의 대화입니다.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
① 대화 역학 (Dialogue Dynamics)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- **Expert (char_teacher)**: 단순히 지식을 말하는 것이 아니라, 현상의 원인과 비유를 곁들여 "깊게" 설명합니다. "부실한 정보"는 절대 금물입니다.
- **Learner (char_student)**: "와 신기하다"로 끝내지 마세요. "그럼 반대로 이런 경우는요?", "그 기술의 핵심 원리는 뭔가요?" 같이 수준 높고 구체적인 질문을 던져 정보를 이끌어내세요.
- **반드시 지켜야 할 구성**: 학습자는 전체 정보량의 흐름을 주도하며, 최소 3번 이상의 명확한 심화 질문을 던져야 합니다.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
② 내러티브 아크 (Narrative Arc)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔴 HOOK (1~2): 전문가가 흔한 오해를 지적하거나, 충격적인 수치를 선언하며 시작.
🟡 BUILD (3~5): 학습자의 구체적 의문 제기 + 전문가의 배경 지식 및 메커니즘 설명
🟢 REVEAL (6~8): 가장 핵심이 되는 지식(하이라이트) 전달.
🔵 DEEPEN (9~11): 실전 활용 예시 또는 한 단계 더 깊은 비하인드 스토리 전달.
⚪ OUTRO (12): 전체 내용의 1줄 요약 + 구독 유도.
""" + COMMON_RULES


# =============================================================================
# MODE B: 전문가 대담 (Expert Dialogue) - 지식 공유 동료들
# =============================================================================
EXPERT_DIALOGUE_PROMPT = """당신은 지식 숏폼 전문 스크립트 작가입니다. 
두 명의 **주제 전문가(Peer Experts)**가 서로의 의견에 살을 붙이며 고도의 정보를 교환하는 설정입니다.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
① 대화 역학 (Dialogue Dynamics)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- **상호 보완 (Additive Knowledge)**: A가 화두(팩트)를 던지면, B는 "맞아요. 거기에 더해 이러한 연구 결과도 있죠"라며 정보를 누적시킵니다.
- **최고 지식 밀도**: 이 모드는 가장 수준 높은 정보를 전달해야 합니다. 가벼운 수다보다는 "정보의 정수인(Nucleus)"을 전달하는 데 집중하세요.
- **전문화된 톤**: 전문가끼리의 대화이므로 용어나 수치가 정확해야 하며, 대화 한 마디 한 마디가 꽉 찬 정보를 담고 있어야 합니다.
""" + COMMON_RULES


# =============================================================================
# Prompt Selector
# =============================================================================
def get_system_prompt(style: str = "teacher-student", scene_count: int = 12) -> str:
    """Select the appropriate system prompt based on the dialogue style.
    Injects dynamic scene_count into the prompt template."""
    if style == "expert-dialogue":
        return EXPERT_DIALOGUE_PROMPT.replace("{scene_count}", str(scene_count))
    return TEACHER_STUDENT_PROMPT.replace("{scene_count}", str(scene_count))


# =============================================================================
# Web Search Research (Gemini + Google Search Grounding)
# =============================================================================
async def research_topic(topic: str, direction: str = "") -> str:
    """Use Gemini + Google Search to gather real-time facts about the topic.
    Returns a structured summary of key facts for script generation."""
    
    research_prompt = f"""다음 주제에 대해 교육용 숏폼 영상 스크립트를 작성하기 위한 핵심 자료를 조사해주세요.

주제: {topic}
{f'의도/방향: {direction}' if direction else ''}

다음 항목을 조사하세요:
1. **핵심 사실과 수치** - 정확한 날짜, 숫자, 인물 이름, 장소
2. **흥미로운 사실** - 대중이 잘 모르는 놀라운 포인트 (훅에 활용)
3. **비유/실생활 연결** - 쉽게 이해할 수 있는 비유 소재
4. **최신 동향** - 관련 최근 이슈나 뉴스 (있다면)
5. **논쟁/반전 포인트** - 흔한 오해, 반전 사실 (있다면)

한국어로 간결하게, 팩트 위주로 정리해주세요. 각 항목에 출처가 있으면 포함해주세요."""

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=research_prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())]
            ),
        )
        research_text = response.text
        logger.info(f"[Research] Topic research completed: {len(research_text)} chars")
        return research_text
    except Exception as e:
        logger.warning(f"[Research] Web search failed, proceeding without research data: {e}")
        return ""


# =============================================================================
# Script Generation - Two-step pipeline (Research → Generate)
# =============================================================================
async def generate_script(topic: str, tags: list[str] = None, direction: str = "", style: str = "teacher-student", scene_count: int = 12) -> dict:
    """Generate a script with scene plan from a topic.
    
    Pipeline:
    1. Research: Use Google Search grounding to gather real-time facts (skip if direction is detailed)
    2. Generate: Use researched facts + SYSTEM_PROMPT to create the script
    """
    # Determination of "richness" of input direction
    is_rich_input = len(direction) > 150
    
    # --- Step 1: Research facts about the topic ---
    research_data = ""
    if not is_rich_input:
        logger.info(f"[ScriptGen] Step 1/2: Researching topic '{topic}' because input is simple.")
        research_data = await research_topic(topic, direction)
    else:
        logger.info(f"[ScriptGen] Step 1/2: Skipping extra research as provided direction is already rich.")

    # --- Step 2: Generate script with enriched context ---
    logger.info(f"[ScriptGen] Step 2/2: Generating script...")
    
    user_prompt = ""
    if is_rich_input:
        user_prompt += "[SOURCE_PRIORITY: HIGH]\n당신은 아래 제공된 '의도/방향'의 정보를 바탕으로 스크립트를 작성해야 합니다. 추가 검색 데이터보다 아래 내용을 최우선으로 반영하세요.\n\n"
        user_prompt += f"주제: {topic}\n\n"
        user_prompt += f"의도/방향 (핵심 정보원):\n{direction}\n\n"
    else:
        user_prompt += f"주제: {topic}\n"
        if direction:
            user_prompt += f"의도/방향: {direction}\n"
            
    user_prompt += f"🎯 장면 수: 정확히 {scene_count}개의 씬을 생성하세요. 두 화자가 번갈아가며 대화합니다.\n"
    if tags:
        user_prompt += f"태그: {', '.join(tags)}\n"
    
    # Append research data if available
    # Append research data if available
    if research_data:
        user_prompt += f"\n📋 보조 참고 자료 (위 주제에 대해 조사된 추가 팩트입니다):\n{research_data}"

    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=get_system_prompt(style, scene_count),
            temperature=0.8,
            response_mime_type="application/json",
        ),
    )

    result = json.loads(response.text)
    
    # === Post-processing ===
    
    # Sanitize YouTube metadata (angle brackets are forbidden by YouTube API)
    for field in ["youtube_description", "youtube_title"]:
        if field in result and isinstance(result[field], str):
            result[field] = re.sub(r'[<>]', '', result[field])
    if "youtube_tags" in result and isinstance(result["youtube_tags"], list):
        result["youtube_tags"] = [re.sub(r'[<>]', '', t) for t in result["youtube_tags"]]
    
    for scene in result.get("scenes", []):
        if "overlays" not in scene:
            scene["overlays"] = []
        
        # Ensure UI metadata fields exist to avoid frontend 'undefined'
        if "character" not in scene: 
            char_id = scene.get("character_id", "char_student")
            # Default fallback ONLY if name is missing from AI output
            char_meta = next((c for c in result.get("characters", []) if c["id"] == char_id), None)
            scene["character"] = char_meta["name"] if char_meta else ("전문가" if "teacher" in char_id else "학생")
        if "background" not in scene: scene["background"] = "배경"
        if "motion" not in scene: scene["motion"] = "기본 동작"
            
        # Scrub script text (TTS safety)
        script = scene.get("script", "")
        # 1. Remove parentheticals like (화내며), (smiling)
        script = re.sub(r'\(.*?\)', '', script)
        # 2. Remove character name prefixes like "홍길동: ", "Officer : " 
        # Supports Korean, English, and wide-width colons
        script = re.sub(r'^[가-힣a-zA-Z0-9\s]+[:：]', '', script)
        # 3. Remove ellipsis (TTS reads them unnaturally) and clean up whitespace
        script = script.replace('...', ' ')
        script = re.sub(r'\s+', ' ', script).strip()
        scene["script"] = script
                
    return result


# =============================================================================
# Metadata Generation from User-Written Script
# =============================================================================
async def generate_metadata_from_script(script_text: str, situation: str = "") -> dict:
    """Generate YouTube metadata (title, description, tags) from a user-written script.
    
    Used when the user writes their own script in manual mode and needs
    AI-generated metadata for YouTube upload.
    """
    logger.info(f"[MetadataGen] Generating metadata from manual script ({len(script_text)} chars)")
    
    metadata_prompt = f"""아래는 유튜브 쇼츠 영상에 사용될 대본입니다. 이 대본을 분석하여 YouTube에 최적화된 메타데이터를 생성해주세요.

대본:
{script_text}

{f'상황 설정: {situation}' if situation else ''}

다음 JSON 형식으로 응답해주세요 (마크다운 코드블록 없이 순수 JSON만):
{{
    "youtube_title": "SEO 최적화된 제목 (#Shorts 포함, 대본 내용을 분석하여 시청자의 호기심을 끌 수 있는 제목)",
    "youtube_description": "매력적인 영상 설명. 대본의 핵심 내용을 요약하여 시청자의 호기심을 자극하고 검색(SEO)에 유리하게 상세히 작성 (해시태그 포함). 꺽쇠 괄호(<, >)는 절대 사용하지 마세요.",
    "youtube_tags": ["태그1", "태그2", "... 대본 내용과 관련된 검색 키워드 최소 10개, 최대 15개. 꺽쇠 괄호(<, >)는 절대 사용하지 마세요."],
    "video_title": {{
        "highlight": "첫 장면 제목의 강조 부분 (핵심 키워드, 최대 13자)",
        "rest": "나머지 제목 (최대 18자)"
    }},
    "subject": "주제 분류명 (2~4자, 예: 역사, 과학, 금융 등)"
}}"""

    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=metadata_prompt,
        config=types.GenerateContentConfig(
            temperature=0.7,
            response_mime_type="application/json",
        ),
    )

    result = json.loads(response.text)
    
    # Post-processing: sanitize YouTube metadata (same as generate_script)
    for field in ["youtube_description", "youtube_title"]:
        if field in result and isinstance(result[field], str):
            result[field] = re.sub(r'[<>]', '', result[field])
    if "youtube_tags" in result and isinstance(result["youtube_tags"], list):
        result["youtube_tags"] = [re.sub(r'[<>]', '', t) for t in result["youtube_tags"]]
    
    logger.info(f"[MetadataGen] Generated metadata: title='{result.get('youtube_title', '')}'")
    return result
