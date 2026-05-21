"""
Script Generator Service
Uses Gemini API to generate scripts and scene plans from a topic.
Optimized for a clean narrator-led visual storytelling format.
"""
import asyncio
import json
import re
import logging
from google import genai
from google.genai import types
from backend.config import GOOGLE_GEMINI_API

logger = logging.getLogger("shorts")

client = genai.Client(api_key=GOOGLE_GEMINI_API)

SCENE_DURATION_TARGETS = {
    8: {
        "target_seconds": 60,
        "min_seconds": 54,
        "max_seconds": 68,
        "recommended_per_scene": 8,
    },
    10: {
        "target_seconds": 88,
        "min_seconds": 80,
        "max_seconds": 96,
        "recommended_per_scene": 9,
    },
    12: {
        "target_seconds": 108,
        "min_seconds": 98,
        "max_seconds": 116,
        "recommended_per_scene": 9,
    },
}

KOREAN_NARRATION_CHARS_PER_SECOND = 5.7
CHAR_BUDGET_TOLERANCE = 0.10
SCENE_CHAR_TOLERANCE = 0.20
MAX_SCENE_SENTENCES = 2
TITLE_HOOK_KEYWORDS = (
    "모르면", "반드시", "절대", "결국", "진짜", "속는", "낭패", "손해",
    "이유", "위험", "주의", "함정", "반전", "끝장", "안심", "실수",
)


def get_duration_target(scene_count: int) -> dict:
    target = dict(
        SCENE_DURATION_TARGETS.get(
            scene_count,
            {
                "target_seconds": min(115, max(60, scene_count * 9)),
                "min_seconds": max(54, scene_count * 8),
                "max_seconds": min(120, scene_count * 10),
                "recommended_per_scene": 9,
            },
        )
    )

    target_seconds = float(target["target_seconds"])
    total_chars = round(target_seconds * KOREAN_NARRATION_CHARS_PER_SECOND)
    scene_chars = total_chars / max(scene_count, 1)

    target["min_total_chars"] = max(180, round(total_chars * (1 - CHAR_BUDGET_TOLERANCE)))
    target["max_total_chars"] = round(total_chars * (1 + CHAR_BUDGET_TOLERANCE))
    target["target_total_chars"] = total_chars
    target["min_scene_chars"] = max(18, round(scene_chars * (1 - SCENE_CHAR_TOLERANCE)))
    target["max_scene_chars"] = round(scene_chars * (1 + SCENE_CHAR_TOLERANCE))
    target["target_scene_chars"] = round(scene_chars)
    return target


# =============================================================================
# SYSTEM PROMPT - 내레이터 중심 지식 쇼츠 생성 프롬프트
# =============================================================================

STAR_INSTRUCTOR_PROMPT = """
당신은 한국 유튜브 쇼츠 전문 스크립트 작가입니다.
순수 내레이터 중심 영상으로, 신뢰감 있고 스크롤을 멈추게 하는 지식 쇼츠를 씁니다.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[바이럴 쇼츠 구조 — 반드시 이 스토리 아크를 따르세요]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

① HOOK (장면 1-2): 첫 3초 안에 스크롤을 멈춰야 합니다.
   - 손해·억울함·반전 사실·숫자로 즉각 충격을 줍니다.
   - "사실", "알고 보면", "이거 모르면", "당신만 모르는" 패턴을 활용하세요.
   - 나쁜 예: "오늘은 해외 카드 사용에 대해 알아보겠습니다."
   - 좋은 예: "해외여행 가서 카드 긁었다가 거절당한 경험 있으세요? 사실 이건 당신 잘못이 아닙니다."

② TENSION BUILD (장면 3-4): 왜 이게 중요한지 공감과 긴장감을 높입니다.
   - "그런데 말이죠", "여기서 문제가 있습니다" 같은 전환 표현으로 흐름을 이어가세요.
   - 시청자의 상황("여행 가기 전", "카드 발급받을 때")에 맞게 공감대를 형성하세요.

③ CORE FACTS (중간 장면들): 핵심 정보를 하나씩, 리듬감 있게 전달합니다.
   - 장면마다 한 포인트만 다룹니다.
   - 구체적 수치, 이름, 상황 비교를 활용해 신뢰를 높이세요.
   - "첫째", "그리고", "마지막으로" 같은 연결어로 흐름을 유지하세요.

④ REVEAL / PAYOFF (뒷부분): 본론의 핵심 반전이나 결론을 보여줍니다.
   - 앞에서 쌓은 긴장을 여기서 풀어주세요.
   - "사실은 이렇습니다", "결국 핵심은 단 하나입니다" 패턴이 효과적입니다.

⑤ OUTRO (마지막 장면): 핵심 1줄 + 댓글 유도로 마무리합니다.
   - 논쟁이나 의견 차이를 유도하는 질문으로 마무리하면 댓글이 폭발합니다.
   - 예: "이거 알고 있었던 분, 댓글에 손들어 주세요."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[타이틀 생성 원칙 — 스크롤 멈추는 두 줄 카피]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- video_title.highlight: 공백 제외 정확히 10자. (주제+상황+손해/반전을 압축)
- video_title.rest: 공백 제외 정확히 12자. (왜 봐야 하는지 — 결과/이유/경고)
- 두 줄은 각자 독립된 카피입니다. 한 문장을 반으로 자르면 실패입니다.
- 밋밋한 주제명, 교과서식 제목 금지. 감정(손해·반전·억울함)이 드러나야 합니다.
- 좋은 예 → highlight: "반드시알아야할카드정보" / rest: "모르면여행가서낭패보는정보"
- 나쁜 예 → highlight: "모르면낭패보는" / rest: "카드정보"
- 낚시성 과장이나 내용과 무관한 공포 조장 금지. 본문 반전과 연결되어야 합니다.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[JSON 출력 형식 — 마크다운 없이 순수 JSON만]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{
    "video_title": {
        "highlight": "공백 제외 정확히 10자 훅 제목",
        "rest": "공백 제외 정확히 12자 보조 훅"
    },
    "subject": "주제 분류 (역사/경제/과학 등 2~4자)",
    "youtube_title": "SEO 최적화 제목 (#Shorts 포함)",
    "youtube_description": "매력적인 영상 설명 (해시태그 포함)",
    "youtube_tags": ["태그1", "태그2", "... 10~15개"],
    "characters": [
        {
            "id": "narrator",
            "name": "내레이터",
            "description": "No visible presenter. Visual storytelling only.",
            "voice_category": "neutral",
            "age_group": "adult",
            "color": "#d4ff00"
        }
    ],
    "scenes": [
        {
            "scene_id": 1,
            "character_id": "narrator",
            "script": "내레이션 대사 (완전한 한국어 구어체 문장)",
            "blackboard_content": "Full-frame visual scene description (English only. Pure visual objects, actions, spatial relationships. No text, no letters, no numbers, no signs anywhere.)",
            "character_gesture": "none",
            "duration": 8
        }
    ]
}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[스크립트 작성 규칙 — CRITICAL]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【발화량 계산】
- 총 내레이션: 공백 제외 {min_total_chars}~{max_total_chars}자. 목표 {target_total_chars}자.
- 장면당: {min_scene_chars}~{max_scene_chars}자. 목표 {target_scene_chars}자.
- 장면당 문장은 1~2문장 이내. 2문장을 넘기면 실패입니다.
- TTS가 한 호흡에 읽을 수 있을 정도로 짧고 명확하게 쓰세요.
- 발화량 목표: 총 {min_seconds}~{max_seconds}초 분량.

【한국어 문법 및 말투】
- 모든 문장은 완전한 서술어로 끝나야 합니다. (-습니다, -이죠, -해요, -겠습니다, -군요 등)
- 명사구로만 끝나는 문장, 서술어 없는 문장은 실패입니다. (예: "중요한 포인트." → 금지)
- 구어체를 쓰되 신뢰감 있는 톤을 유지하세요.
- 쉼표를 문장 늘리기 수단으로 남용하지 마세요. 핵심만 짧게.
- 각 문장은 소리 내어 읽었을 때 자연스러워야 합니다.
- 감탄사("오", "와")는 TTS 품질에 영향을 주므로 사용 금지.

【팩트 정확성 — 허위 정보 절대 금지】
- 제공된 참고 자료에서 확인된 사실만 사용하세요.
- 확인되지 않은 규정, 법적 위험, 통계를 지어내지 마세요.
- 수치나 규정이 불확실하면 "알려진 바로는", "일반적으로", "약 OO" 처럼 보수적으로 표현하세요.
- 특히 카드/금융/의료/법률 정보는 추정 대신 확인된 사용 팁 중심으로 설명하세요.

【논리적 일관성 — 가장 흔한 실패 패턴】
- 전체 장면을 작성한 뒤, 아래 일관성 체크를 반드시 수행하세요:
  ① 앞 장면에서 "X가 있다"고 했는데 뒷 장면에서 "X가 없을 수도 있다"고 하지 않기.
  ② 앞 장면의 주장과 뒷 장면의 주장이 논리적으로 같은 방향을 가리키는지 확인.
  ③ "안심하면 안 됩니다" → "기능이 없을 수도 있습니다"처럼 전제를 뒤집는 흐름 금지.
- 나쁜 예: "컨택리스 마크만 보고 안심하면 큰 오산입니다." 다음 장면에 "일부 카드는 컨택리스 기능이 없을 수도 있습니다." → 마크가 있으면 기능도 있는 것이므로 앞뒤가 모순됨.
- 좋은 예: "컨택리스 마크가 있어도 특정 국가나 단말기에서는 작동 안 될 수 있습니다." → 마크는 있지만 '호환성' 문제를 지적하는 것이라 논리적으로 일관됨.
- 드라마 효과를 위해 사실을 왜곡하거나 과장하면 안 됩니다. 진짜 유용한 정보가 더 강력한 훅이 됩니다.

【비주얼 지시 및 일관성 규칙】
- blackboard_content는 글자/숫자/기호 없는 순수 이미지 장면 묘사입니다 (영어로만).
- 전체 주제 맥락을 반영해야 하며, 발표자·강사·칠판 구도 금지.
- 장면 전체를 채우는 메인 비주얼이어야 합니다.
{visual_style_guidelines}

【TTS 안전】
- scene.script에 해시태그, 샵, 별표, URL, 이모지, 영어 CTA, "구독 좋아요", "Shorts" 금지.
- 순수 한국어 구어체 문장만 작성하세요.

【장면 설계】
- 장면 수는 정확히 {scene_count}개.
- 한 장면 = 한 포인트. 예외·이유·주의사항을 한 번에 몰아넣지 마세요.
- 각 장면은 앞 장면을 이어받아 하나의 이야기처럼 연결되어야 합니다.
"""


def get_system_prompt(style: str = "star-instructor", scene_count: int = 12, visual_style: str = "cute-2d") -> str:
    duration_target = get_duration_target(scene_count)
    
    if visual_style == "botero":
        visual_style_guidelines = """- 비주얼 스타일 [CRITICAL]: Fernando Botero's style (Boterismo). 모든 인물, 동물, 사물은 극도로 뚱뚱하고 둥글고 부풀려진 극단적인 부피감(voluptuous exaggerated volume, plump, bloated)을 가지며, 부드럽고 매끄러운 곡선과 아웃라인을 가진 유화(oil painting flat shading) 느낌의 풍만하고 유머러스한 스타일로 묘사되어야 합니다. 모든 장면 설명(blackboard_content)에 "in Fernando Botero's style" 또는 "Boterismo style"을 포함시키세요.
- 동일 인물/배경/사물 일관성 (Visual Consistency) [CRITICAL]:
  ① 주연 등장인물이 있는 경우, 첫 장면에 캐릭터의 세부 외모(예: 성별, 나이, 머리모양, 옷차림 색상/스타일, 안경 유무 등)를 명확히 정의하고, 그 캐릭터가 나오는 모든 장면의 blackboard_content에 '동일한 묘사 문구를 토씨 하나 틀리지 않고 그대로 재사용'하세요. 행동과 동작만 다르게 변경합니다.
     (예: "A extremely plump merchant in Botero style, round bloated face, thin mustache, wearing a tight blue suit and tiny red tie"가 반복해서 나와야 함)
  ② 계속 등장하는 사물이나 동일한 배경 장소(방, 상점, 거리 등)가 있다면, 해당 사물이나 배경의 상세 묘사(색상, 재질, 형태)도 모든 장면의 프롬프트에서 완벽히 일치하는 고정된 표현을 재사용해야 합니다."""
    else:
        # Default cute-2d
        visual_style_guidelines = """- 비주얼 스타일: Cute 2D animation illustration, bold clean outlines, flat cel-shading, round friendly shapes, warm pastel colors.
- 동일 인물/배경/사물 일관성 (Visual Consistency) [CRITICAL]:
  ① 주연 등장인물이 있는 경우, 첫 장면에 캐릭터의 세부 외모(예: 성별, 나이, 머리모양, 옷차림 색상/스타일, 안경 유무 등)를 명확히 정의하고, 그 캐릭터가 나오는 모든 장면의 blackboard_content에 '동일한 묘사 문구를 토씨 하나 틀리지 않고 그대로 재사용'하세요. 행동과 동작만 다르게 변경합니다.
  ② 계속 등장하는 사물이나 동일한 배경 장소(방, 상점, 거리 등)가 있다면, 해당 사물이나 배경의 상세 묘사(색상, 재질, 형태)도 모든 장면의 프롬프트에서 완벽히 일치하는 고정된 표현을 재사용해야 합니다."""

    return (
        STAR_INSTRUCTOR_PROMPT
        .replace("{scene_count}", str(scene_count))
        .replace("{min_seconds}", str(duration_target["min_seconds"]))
        .replace("{max_seconds}", str(duration_target["max_seconds"]))
        .replace("{min_total_chars}", str(duration_target["min_total_chars"]))
        .replace("{max_total_chars}", str(duration_target["max_total_chars"]))
        .replace("{target_total_chars}", str(duration_target["target_total_chars"]))
        .replace("{min_scene_chars}", str(duration_target["min_scene_chars"]))
        .replace("{max_scene_chars}", str(duration_target["max_scene_chars"]))
        .replace("{target_scene_chars}", str(duration_target["target_scene_chars"]))
        .replace("{visual_style_guidelines}", visual_style_guidelines)
    )


def _speech_char_count(script: str) -> int:
    return len(re.sub(r"\s+", "", script or ""))


def _title_char_count(value: str) -> int:
    return len(re.sub(r"\s+", "", str(value or "")))


def _video_title_lengths_ok(video_title: str | dict) -> bool:
    if not isinstance(video_title, dict):
        return False
    highlight = video_title.get("highlight", "")
    rest = video_title.get("rest", "")
    return _title_char_count(highlight) == 10 and _title_char_count(rest) == 12


def _video_title_structure_ok(video_title: str | dict, topic: str = "") -> bool:
    if not isinstance(video_title, dict):
        return False

    highlight = str(video_title.get("highlight", "") or "").strip()
    rest = str(video_title.get("rest", "") or "").strip()
    if not highlight or not rest:
        return False

    if highlight == rest:
        return False

    # Reject obvious "one sentence cut in half" patterns.
    if highlight.endswith(("의", "를", "을", "이", "가", "은", "는", "로", "와", "과", "도")):
        return False
    if rest in topic or highlight in rest:
        return False

    highlight_has_hook = any(keyword in highlight for keyword in TITLE_HOOK_KEYWORDS)
    rest_has_hook = any(keyword in rest for keyword in TITLE_HOOK_KEYWORDS)

    # Prefer: highlight anchors the topic, rest carries the curiosity/consequence.
    topic_tokens = [token for token in re.findall(r"[가-힣A-Za-z0-9]{2,}", topic or "") if len(token) >= 2]
    highlight_topic_overlap = any(token in highlight for token in topic_tokens)
    rest_topic_overlap = any(token in rest for token in topic_tokens)

    if not rest_has_hook:
        return False
    if highlight_has_hook and not highlight_topic_overlap and rest_topic_overlap:
        return False

    return True


def _sentence_count(script: str) -> int:
    parts = [part.strip() for part in re.split(r"[.!?。]+", str(script or "")) if part.strip()]
    return len(parts)


_NATURAL_ENDING_RE = re.compile(
    r"(습니다|ㅂ니다|입니다|았습니다|었습니다|겠습니다|셨습니다"
    r"|이죠|이지요|거든요|네요|군요|잖아요|랍니다|답니다"
    r"|해요|하세요|보세요|세요|아요|어요|예요|이에요"
    r"|죠|지요)$"
)
_INVALID_FRAGMENT_RE = re.compile(
    r"(때문에?|이유로?|위해서?|경우에?|상황에?|처럼|같은|등등?)$"
)


def _script_has_natural_endings(script: str) -> bool:
    parts = [part.strip(" .") for part in re.split(r"[.!?。]+", str(script or "")) if part.strip()]
    if not parts:
        return False
    for part in parts:
        if len(part) < 5:
            return False
        if _INVALID_FRAGMENT_RE.search(part):
            return False
        if not _NATURAL_ENDING_RE.search(part):
            return False
    return True


def _script_text_from_scenes(scenes: list[dict]) -> str:
    return "\n".join(
        scene.get("script", "").strip()
        for scene in scenes or []
        if scene.get("script")
    ).strip()


def _normalize_metadata(metadata: dict, topic: str = "") -> dict:
    safe_topic = (topic or "").strip()
    title = str(metadata.get("youtube_title", "") or "").strip()
    description = str(metadata.get("youtube_description", "") or "").strip()
    tags = metadata.get("youtube_tags", [])

    if not title:
        title = safe_topic or "지식 쇼츠 #Shorts"
    if "#Shorts".lower() not in title.lower():
        title = f"{title} #Shorts".strip()
    title = re.sub(r"\s+", " ", title)[:100]

    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    tags = [
        re.sub(r"^#+", "", str(tag).strip())
        for tag in (tags or [])
        if str(tag).strip()
    ]
    tags = list(dict.fromkeys(tags))[:12]

    hashtag_line = " ".join(f"#{tag}" for tag in tags[:5])
    if not description:
        description = safe_topic or title.replace("#Shorts", "").strip()
    description = re.sub(r"\s+", " ", description).strip()
    existing_hashtags = re.findall(r"#([A-Za-z0-9가-힣_]+)", description)
    existing_hashtags = list(dict.fromkeys(existing_hashtags))
    merged_hashtags = list(dict.fromkeys(existing_hashtags + tags[:5]))
    if merged_hashtags:
        description = re.sub(r"(?:\s*#(?:[A-Za-z0-9가-힣_]+)\s*)+$", "", description).strip()
        description = f"{description}\n\n{' '.join(f'#{tag}' for tag in merged_hashtags)}".strip()

    return {
        "youtube_title": title,
        "youtube_description": description,
        "youtube_tags": tags,
    }


async def enrich_script_metadata(script_data: dict, topic: str = "", situation: str = "") -> dict:
    if not script_data:
        return script_data

    script_text = _script_text_from_scenes(script_data.get("scenes", []))
    if not script_text:
        return script_data

    has_title = bool(str(script_data.get("youtube_title", "") or "").strip())
    has_description = bool(str(script_data.get("youtube_description", "") or "").strip())
    has_tags = bool(script_data.get("youtube_tags"))
    if has_title and has_description and has_tags:
        normalized = _normalize_metadata(script_data, topic or script_data.get("topic", ""))
        script_data.update(normalized)
        return script_data

    metadata = await generate_metadata_from_script(
        script_text,
        situation=situation,
        topic=topic or script_data.get("topic", "") or script_data.get("subject", ""),
    )
    script_data.update(_normalize_metadata(metadata, topic or script_data.get("topic", "")))
    return script_data


def _strip_text_requests_from_visual_prompt(value: str) -> str:
    clean = str(value or "")
    clean = re.sub(r"(?i)\bwith\s+(the\s+)?words?\s+['\"“”‘’][^'\"“”‘’]+['\"“”‘’]", "with a blank symbolic shape", clean)
    clean = re.sub(r"(?i)\b(the\s+)?words?\s+['\"“”‘’][^'\"“”‘’]+['\"“”‘’]", "a blank symbolic shape", clean)
    clean = re.sub(r"['\"“”‘’][^'\"“”‘’]{1,80}['\"“”‘’]", "blank unmarked visual element", clean)
    replacements = {
        r"(?i)\bquestion marks?\b": "uncertainty shown by contrasting objects",
        r"(?i)\b(text|letters?|words?|typography|writing|written|readable)\b": "unmarked visual elements",
        r"(?i)\b(numbers?|labels?|captions?|signs?)\b": "blank symbolic shapes",
    }
    for pattern, replacement in replacements.items():
        clean = re.sub(pattern, replacement, clean)
    clean = re.sub(r"[가-힣]+", "", clean)
    clean = re.sub(r"[?!?？!！]", "", clean)
    clean = re.sub(r"\bblank symbolic shape\s+unmarked visual elements\s+inside\b", "a blank symbolic shape inside", clean, flags=re.I)
    clean = re.sub(r"\s+", " ", clean).strip(" ,.-")
    return clean


def _normalize_visual_prompt(value: str, topic: str, direction: str) -> str:
    clean = _strip_text_requests_from_visual_prompt(value)
    if not clean or len(clean) < 40:
        context = f"{topic} {direction}".strip()
        clean = (
            "A context-aware visual metaphor based on the full story: "
            f"{context[:160]}. Use concrete objects, action, and spatial contrast."
        )

    no_text_rule = (
        "No readable text, letters, numbers, punctuation, labels, captions, "
        "logos, watermarks, or question marks; use only pure visual objects and actions."
    )
    if "No readable text" not in clean:
        clean = f"{clean}. {no_text_rule}"
    return clean[:700]


def _sanitize_narration_script(value: str) -> str:
    script = str(value or "")
    script = script.replace("\r\n", "\n").replace("\r", "\n")
    script = re.sub(r"\([^)]*\)", "", script)
    script = re.sub(r"\[[^\]]*\]", "", script)
    script = re.sub(r"(?im)^\s*(해시태그|hashtags?|tags?)\s*:?\s*$", "", script)
    script = re.sub(r"(?im)^\s*(해시태그|hashtags?|tags?)\s*:?\s*(?:#\s*[^\s#]+(?:\s+|$))+", "", script)
    script = re.sub(r"(?im)^\s*(?:#\s*[^\s#]+(?:\s+|$))+$", "", script)
    script = re.sub(r"#\s*[^\s#]+", "", script)
    script = re.sub(r"https?://\S+", "", script)
    script = re.sub(r"[@*_=+~^|<>`\\/]+", " ", script)
    script = re.sub(r"[!！?？]+", ".", script)
    script = re.sub(
        r"(구독\s*,?\s*좋아요\s*(부탁드려요|눌러주세요)?|좋아요\s*,?\s*구독\s*(부탁드려요|눌러주세요)?|팔로우\s*부탁드려요?)",
        "",
        script,
        flags=re.IGNORECASE,
    )
    script = re.sub(
        r"(구독(과)?\s*좋아요(는|도)?\s*(부탁드릴게요|부탁드려요|눌러주세요|해주세요)?|댓글\s*(남겨주세요|부탁드려요|달아주세요)|팔로우\s*(부탁드려요|해주세요)|알림\s*설정\s*(부탁드려요|해주세요))",
        "",
        script,
        flags=re.IGNORECASE,
    )
    script = re.sub(r"\b(shorts|reels|viral|follow|like|subscribe)\b", "", script, flags=re.IGNORECASE)
    script = re.sub(r"(부정\s*사용으로\s*오해받을\s*수\s*있습니다)", "문제가 생길 수 있습니다", script, flags=re.IGNORECASE)
    script = re.sub(r"\n{2,}", "\n", script)
    script = re.sub(r"[ \t]+", " ", script)
    script = re.sub(r"\s*\n\s*", " ", script)
    script = re.sub(r"\s+", " ", script).strip(" .,-")
    if script and not re.search(r"[.!?]$", script):
        script = f"{script}."
    return script


def sanitize_scene_scripts(script_data: dict) -> dict:
    for scene in script_data.get("scenes", []):
        scene["script"] = _sanitize_narration_script(scene.get("script", ""))
    return script_data


def _scene_scripts_ok(result: dict, duration_target: dict) -> bool:
    scenes = result.get("scenes", [])
    if not scenes:
        return False

    max_chars = duration_target["max_scene_chars"]
    min_chars = max(12, duration_target["min_scene_chars"] - 10)
    for scene in scenes:
        script = scene.get("script", "")
        chars = _speech_char_count(script)
        if chars > max_chars or chars < min_chars:
            return False
        if _sentence_count(script) > MAX_SCENE_SENTENCES:
            return False
        if not _script_has_natural_endings(script):
            return False
    return True


def _postprocess_script_result(result: dict, duration_target: dict, topic: str, direction: str) -> dict:
    # Metadata sanitization
    for field in ["youtube_description", "youtube_title"]:
        if field in result and isinstance(result[field], str):
            result[field] = re.sub(r"[<>]", "", result[field])

    for scene in result.get("scenes", []):
        # Compatibility with older schema
        scene["character"] = "내레이터"
        scene["background"] = "메인 비주얼"
        scene["motion"] = "slow_push"

        script = _sanitize_narration_script(scene.get("script", ""))
        scene["script"] = script

        blackboard_content = scene.get("blackboard_content") or scene.get("background_description") or ""
        scene["blackboard_content"] = _normalize_visual_prompt(blackboard_content, topic, direction)
        scene["background_description"] = scene["blackboard_content"]
        scene["duration"] = max(scene.get("duration", duration_target["recommended_per_scene"]), 4)

    result["duration_target"] = duration_target
    result["speech_char_count"] = sum(_speech_char_count(s.get("script", "")) for s in result.get("scenes", []))
    return result


async def research_topic(topic: str, direction: str = "") -> str:
    research_prompt = f"""다음 주제에 대해 내레이터 중심 지식 쇼츠 스크립트를 작성하기 위한 핵심 자료를 조사해주세요.
주제: {topic}
{f'의도/방향: {direction}' if direction else ''}
1. 팩트와 수치 2. 흥미로운 반전 포인트 3. 실생활 연결 고리를 정리해주세요."""

    try:
        response = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-2.0-flash",
            contents=research_prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())]
            ),
        )
        return response.text
    except Exception as e:
        logger.warning(f"[Research] failed: {e}")
        return ""


async def generate_script(topic: str, tags: list[str] = None, direction: str = "", style: str = "star-instructor", scene_count: int = 12, visual_style: str = "cute-2d") -> dict:
    duration_target = get_duration_target(scene_count)
    is_rich_input = len(direction) > 150
    
    research_data = ""
    if not is_rich_input:
        research_data = await research_topic(topic, direction)

    user_prompt = f"주제: {topic}\n"
    if direction:
        user_prompt += f"의도/방향: {direction}\n"
    user_prompt += f"""정확히 {scene_count}개의 장면으로 구성된 내레이터 중심 지식 쇼츠 스크립트를 작성하세요.
전체 대본은 하나의 이야기처럼 이어져야 하며, 총 발화량은 공백 제외 {duration_target['min_total_chars']}~{duration_target['max_total_chars']}자여야 합니다.
이번 요청의 시간 예산은 약 {duration_target['target_seconds']}초이며, 목표 총 글자수는 약 {duration_target['target_total_chars']}자입니다.
특히 {duration_target['max_total_chars']}자를 넘기지 마세요. 장면마다 1~2개의 짧은 문장만 사용하고, 반복 설명은 빼세요.
장면당 글자수도 약 {duration_target['target_scene_chars']}자 기준으로 고르게 배분하세요.
한 장면이 길어지면 다음 장면으로 넘기지 말고, 그 장면 자체를 더 짧게 압축하세요.
규정이나 위험을 설명할 때는 추측성 단정 대신 확인된 내용만 보수적으로 말하세요.
각 장면은 한 포인트만 설명하세요. 한 장면 안에 예시, 예외, 주의사항을 한꺼번에 몰아넣지 마세요.
장면 대사는 실제 TTS로 읽을 문장입니다. 내레이터가 숨 한번에 읽을 수 있을 정도로 짧게 쓰세요.
모든 장면 대사는 문법적으로 완전한 한국어 문장이어야 합니다. 제목 조각처럼 끊긴 문장, 명사구 단독 문장, 서술어 없는 문장은 금지입니다.
video_title.highlight와 video_title.rest는 문장을 반으로 자른 조각이 아니라, 각자 역할이 다른 두 줄 카피여야 합니다.
highlight는 주제/대상/상황을 강하게 잡는 전면 훅으로 10자를 꽉 채우고, rest는 왜 봐야 하는지 설명하는 보조 훅으로 12자를 꽉 채우세요.
두 줄 모두 글자수를 남기지 말고 끝까지 채우세요.
훅 제목과 부제목은 주제명이 아니라, 이 영상을 끝까지 봐야 하는 반전/손해/오해를 압축한 강한 카피로 만드세요.
각 blackboard_content는 전체 주제와 상황을 반영한 순수 시각 이미지 프롬프트여야 하며, 글자/숫자/물음표/라벨/문구를 절대 포함하지 마세요.
blackboard_content라는 이름을 쓰더라도 실제로는 장면 전체를 구성하는 메인 비주얼 설명입니다. 남자 강사, 발표 캐릭터, 칠판 중앙 배치 같은 연출은 넣지 마세요.
"""
    
    if research_data:
        user_prompt += f"\n참고 자료:\n{research_data}\n"

    last_result = None
    for attempt in range(2):
        retry_instruction = ""
        if attempt == 1:
            retry_instruction = f"""

[재시도 지시 — 이전 결과에서 다음 항목을 반드시 수정하세요]
1. 총 발화량: {duration_target['min_total_chars']}~{duration_target['max_total_chars']}자 (목표 {duration_target['target_total_chars']}자). 이 범위를 벗어나면 오디오 속도가 강제 조정되어 부자연스러워집니다.
2. 장면당 발화: {duration_target['min_scene_chars']}~{duration_target['max_scene_chars']}자 (목표 {duration_target['target_scene_chars']}자). 균등하게 배분하세요.
3. 모든 문장은 완전한 서술어(-습니다/-이죠/-해요/-겠습니다 등)로 끝나야 합니다. 명사구 종결 금지.
4. video_title.highlight는 공백 제외 정확히 10자, rest는 정확히 12자. 한 문장 반토막 금지.
5. 각 장면 대사는 TTS가 한 호흡에 읽을 분량. 1~2문장 이내.
6. 참고 자료에 없는 수치나 규정을 지어내지 마세요. 불확실하면 "일반적으로", "알려진 바로는" 등으로 표현하세요.
7. HOOK 장면부터 바이럴 구조(손해·반전·공감)로 시작하세요.
"""

        response = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-2.0-flash",
            contents=user_prompt + retry_instruction,
            config=types.GenerateContentConfig(
                system_instruction=get_system_prompt(style, scene_count, visual_style),
                temperature=0.30 if is_rich_input else 0.45,
                response_mime_type="application/json",
            ),
        )

        result = _postprocess_script_result(
            json.loads(response.text),
            duration_target,
            topic,
            direction,
        )
        last_result = result

        scenes_ok = len(result.get("scenes", [])) == scene_count
        speech_ok = duration_target["min_total_chars"] <= result["speech_char_count"] <= duration_target["max_total_chars"]
        title_ok = _video_title_lengths_ok(result.get("video_title"))
        title_structure_ok = _video_title_structure_ok(result.get("video_title"), topic)
        scene_scripts_ok = _scene_scripts_ok(result, duration_target)
        if scenes_ok and speech_ok and title_ok and title_structure_ok and scene_scripts_ok:
            result["topic"] = topic
            result["visual_style"] = visual_style
            sanitize_scene_scripts(result)
            await enrich_script_metadata(result, topic=topic, situation=result.get("situation_setting", {}).get("situation", ""))
            return result

        logger.warning(
            "[ScriptLengthGuard] attempt=%s scenes=%s/%s chars=%s target=%s~%s title_ok=%s title_structure_ok=%s scene_scripts_ok=%s",
            attempt + 1,
            len(result.get("scenes", [])),
            scene_count,
            result["speech_char_count"],
            duration_target["min_total_chars"],
            duration_target["max_total_chars"],
            title_ok,
            title_structure_ok,
            scene_scripts_ok,
        )

    if last_result:
        last_result["topic"] = topic
        last_result["visual_style"] = visual_style
        sanitize_scene_scripts(last_result)
        await enrich_script_metadata(last_result, topic=topic, situation=last_result.get("situation_setting", {}).get("situation", ""))
    return last_result


async def generate_metadata_from_script(script_text: str, situation: str = "", topic: str = "") -> dict:
    metadata_prompt = f"""다음 쇼츠 대본을 분석해서 지금 유튜브 쇼츠에서 잘 먹히는 형식의 메타데이터를 JSON으로 생성하세요.

조건:
- 제목은 100자 이내.
- 제목 앞부분에 핵심 키워드 1~2개를 자연스럽게 넣고, 짧은 호기심/반전/손해회피 톤을 사용.
- 제목에는 반드시 #Shorts 포함.
- 설명 첫 1~2문장은 영상 핵심과 검색 키워드를 바로 드러내기.
- 설명 마지막에는 핵심 해시태그 3~5개 추가.
- youtube_tags는 검색 의도가 분명한 태그 8~12개. 중복 금지.
- 과장 낚시, 의미 없는 해시태그 남발, 영어 스팸식 키워드 반복 금지.
- 한국어 채널 톤으로 자연스럽게 작성.

출력 JSON:
{{
  "youtube_title": "제목",
  "youtube_description": "설명",
  "youtube_tags": ["태그1", "태그2"]
}}

주제: {topic}
상황: {situation}

대본:
{script_text}
"""
    response = await asyncio.to_thread(
        client.models.generate_content,
        model="gemini-2.0-flash",
        contents=metadata_prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
        ),
    )
    return _normalize_metadata(json.loads(response.text), topic)
