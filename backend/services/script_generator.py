"""
Script Generator Service
Uses host-side agy to generate scripts and scene plans from a topic.
Optimized for a clean narrator-led visual storytelling format.
"""
import asyncio
import json
import re
import logging
import time
from typing import Union
from backend.services.agy_text_client import generate_text_with_agy
from backend.config import SCRIPT_GENERATION_ATTEMPTS, SCRIPT_RESEARCH_ENABLED

logger = logging.getLogger("shorts")

SCENE_DURATION_TARGETS = {
    8: {
        "target_seconds": 53,
        "min_seconds": 47,
        "max_seconds": 57,
        "recommended_per_scene": 6,
    },
    10: {
        "target_seconds": 51,
        "min_seconds": 46,
        "max_seconds": 56,
        "recommended_per_scene": 5,
    },
    12: {
        "target_seconds": 48,
        "min_seconds": 43,
        "max_seconds": 54,
        "recommended_per_scene": 4,
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


def get_duration_target(scene_count: int, speed: str = "1.12") -> dict:
    # 1.12배(약간 빠르게) 단일 표준 기준 고정 (초당 5.8자)
    chars_per_sec = 5.8

    target = dict(
        SCENE_DURATION_TARGETS.get(
            scene_count,
            {
                "target_seconds": 53.0 if scene_count < 9 else (48.0 if scene_count > 11 else 51.0),
                "min_seconds": 47.0 if scene_count < 9 else (43.0 if scene_count > 11 else 46.0),
                "max_seconds": 57.0 if scene_count < 9 else (54.0 if scene_count > 11 else 56.0),
                "recommended_per_scene": max(4, round(48 / max(scene_count, 1))),
            },
        )
    )

    target_seconds = float(target["target_seconds"])
    total_chars = round(target_seconds * chars_per_sec)
    scene_chars = total_chars / max(scene_count, 1)

    target["min_total_chars"] = max(160, round(total_chars * 0.93))
    target["max_total_chars"] = round(total_chars * 1.05)
    target["target_total_chars"] = total_chars
    target["min_scene_chars"] = max(14, round(scene_chars * 0.88))
    target["max_scene_chars"] = round(scene_chars * 1.10)
    target["target_scene_chars"] = round(scene_chars)
    target["chars_per_second"] = chars_per_sec
    return target



def get_duration_target_ssul(scene_count: int, speed: str = "1.12") -> dict:
    # 1.12배(약간 빠르게) 단일 표준 기준 고정 (초당 6.0자 - 썰 형식은 발화가 약간 더 촘촘함)
    chars_per_sec = 6.0

    target = dict(
        SCENE_DURATION_TARGETS.get(
            scene_count,
            {
                "target_seconds": 53.0 if scene_count < 9 else (48.0 if scene_count > 11 else 51.0),
                "min_seconds": 47.0 if scene_count < 9 else (43.0 if scene_count > 11 else 46.0),
                "max_seconds": 57.0 if scene_count < 9 else (54.0 if scene_count > 11 else 56.0),
                "recommended_per_scene": max(4, round(48 / max(scene_count, 1))),
            },
        )
    )

    target_seconds = float(target["target_seconds"])
    total_chars = round(target_seconds * chars_per_sec)
    scene_chars = total_chars / max(scene_count, 1)

    target["min_total_chars"] = max(160, round(total_chars * 0.94))
    target["max_total_chars"] = round(total_chars * 1.04)
    target["target_total_chars"] = total_chars
    target["min_scene_chars"] = max(14, round(scene_chars * 0.88))
    target["max_scene_chars"] = round(scene_chars * 1.08)
    target["target_scene_chars"] = round(scene_chars)
    target["chars_per_second"] = chars_per_sec
    
    return target


SSUL_SHORTS_PROMPT = """
# Role: 유튜브 쇼츠 전문 썰/독백 대본 작가 (커뮤니티 글 각색 전문가)
당신은 블라인드, 에브리타임, 네이트판 등 커뮤니티의 실화 사연을 모티브로 삼아, 유튜브 쇼츠 알고리즘이 선호하는 흡입력 있고 안전한 '독백형 썰 쇼츠' 대본으로 재창작하는 전문 작가입니다.

사용자가 제공하는 [원문 내용]을 바탕으로, 아래의 [원문 필터링 및 각색 규칙]과 [수학적 제약 조건]을 완벽히 준수하여 대본을 작성해야 합니다.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🛑 [원문 필터링 및 각색 규칙 - 필수]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
원문의 내용을 그대로 복사하는 것은 저작권 및 명예훼손의 위험이 있으므로, 반드시 다음과 같이 '재창작'해야 합니다.

1. [출처 세탁 및 화자 설정]: 원문이 블라인드나 타 커뮤니티 글이더라도 대본에서는 "내 친구 이야기", "우리 회사 대리님 실화", "내가 직접 겪은 일"처럼 화자를 '나 또는 주변 인물'로 설정하여 1인칭 독백 실화 풍으로 바꿉니다.
2. [고유명사 및 특정성 완전히 삭제]: 삼성, 네이버 등 실제 기업명은 '우리 회사', '대기업', 'A사' 등으로 익명화하고, 부서나 특정 직급, 지역 등 인물이 특정될 수 있는 단어는 완전히 배제하거나 흔한 설정으로 변경하세요.
3. [구어체 완벽 변환]: 커뮤니티 특유의 문어체 텍스트(예: "~하노", "본인 방금 ~하는 상상함", "~음")를 실제 입으로 자연스럽게 말하는 템포 빠른 구어체로 100% 재작성하세요.
4. [극적 각색 (사이다 추가)]: 스토리의 몰입도를 위해 원작의 뼈대는 유지하되, 결말이나 중간 과정을 조금 더 황당하거나 킹받게, 혹은 사이다(참교육) 요소가 살도록 극적으로 변형하세요.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📐 [수학적 제약 조건 및 글자 수 계산 공식]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
한국어 일반 독백의 평균 발화 속도는 '초당 음절(글자) 수'를 기준으로 계산합니다. 지정된 재생 시간 내에 지정된 장면 수가 균등하게 배분되어야 하며, 공백을 제외한 순수 글자 수를 철저히 지켜야 합니다.

1. 발화 속도 기준 (초당 글자 수):
   - [보통] (0.95x~1.05x 배속): 초당 5.0 ~ 5.5글자
   - [빠르게] (1.12x 배속): 초당 6.0글자
   - [매우 빠르게] (1.20x 배속): 초당 6.5글자

2. 목표 설정 가이드라인 (오차범위 ±5%):
   - 총 글자 수 제한: {min_total_chars}~{max_total_chars}자 (목표: {target_total_chars}자)
   - 장면당 글자 수 제한: {min_scene_chars}~{max_scene_chars}자 (목표: {target_scene_chars}자)
   - 장면별 배분: 각 장면(Scene)의 글자 수는 {target_scene_chars}자 내외로 최대한 균등하게 쪼개어져야 합니다. (Scene 1과 마지막 Scene은 전달력 위주로 약간의 유연성 허용)
   - 한 장면당 문장은 최대 1~2문장 이내여야 합니다. 절대 2문장을 넘기지 마세요.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎙️ [나레이션 설정 및 보이스 연동]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- 성별 및 목소리: {voice_gender} ({voice_age})
- 분위기 및 톤: {voice_tone}
- 발화 속도 배속: {voice_speed}x (초당 글자수 {chars_per_second}자 기준)

이 나레이션 설정을 감안하여, 대본의 어투와 리듬감을 분위기(톤)에 꼭 맞춰 작성해 주세요. 
- 지정된 어투(예: 친구한테 말하는 반말 등)를 첫 문장부터 끝까지 완벽하게 유지하세요.
- 수퍼톤 TTS 엔진의 호흡을 고려하여 불필요한 문장 부호(, . !)를 남발하지 마세요.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✍️ [작성 및 출력 양식 - JSON형식]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
반드시 markdown formatting(```json ... ```) 없이 순수 JSON 텍스트만 출력하세요.
출력 시 각 장면의 대사(script)는 문장 끝에 반드시 공백 제외 글자 수를 괄호 형태로 표기해야 합니다. (예: "우리 회사 대리님이 글쎄 이랬다니까.(글자 수: 22자)")

{
    "video_title": {
        "highlight": "공백 제외 정확히 10자 훅 제목",
        "rest": "공백 제외 정확히 12자 보조 훅"
    },
    "subject": "주제 분류 (유머/공포/직장 등 2~4자)",
    "youtube_title": "SEO 최적화 제목 (#Shorts 포함)",
    "youtube_description": "매력적인 영상 설명 (해시태그 포함)",
    "youtube_tags": ["회사썰", "직장인공감", "참교육사이다", "꿀잼이야기", "실화바탕", "쇼츠추천", "인기급상승", "썰쇼츠"],
    "visual_bible": {
        "story_world": "One concise English sentence defining the exact world, setting, era, and mood that must stay fixed across every image.",
        "main_character": "Exact English phrase for recurring character appearance, age, hair, body, facial features, and expression language. Reuse verbatim in every relevant scene.",
        "wardrobe": "Exact English phrase for fixed clothing, colors, accessories, and formality level. Reuse verbatim in every relevant scene.",
        "primary_location": "Exact English phrase for recurring location architecture, props, lighting, and spatial layout. Reuse verbatim when the location continues.",
        "fixed_props": "Exact English phrase for recurring props and objects that should not change shape/color across scenes.",
        "continuity_notes": "English notes about what must never change, and what may change only by story progression."
    },
    "characters": [
        {
            "id": "narrator",
            "name": "내레이터",
            "description": "No visible presenter. Visual storytelling only.",
            "voice_category": "{voice_category}",
            "age_group": "{voice_age_group}",
            "color": "#ff3b30"
        }
    ],
    "scenes": [
        {
            "scene_id": 1,
            "character_id": "narrator",
            "script": "구어체 1인칭 독백 대사. 문장 끝에는 반드시 공백제외 글자 수가 괄호 형태로 포함되어야 합니다. 예시: '어제 진짜 황당한 일 겪었잖아.(글자 수: 21자)'",
            "blackboard_content": "Full-frame visual scene description (English or Korean. South Park inspired cartoon scene, may include short Korean speech bubbles, signs, phone screens, map labels, or captions if useful.)",
            "character_gesture": "none",
            "duration": {recommended_per_scene}
        }
    ]
}

【비주얼 지시 및 일관성 규칙】
- blackboard_content는 사우스파크풍 만화 장면 묘사입니다. 짧은 한국어 말풍선·간판·지도 라벨·휴대폰 화면 문구를 넣어도 됩니다.
- 전체 주제 맥락을 반영해야 하며, 발표자·강사·칠판 구도 금지.
- 장면 전체를 채우는 메인 비주얼이어야 합니다.
- visual_bible을 먼저 만든 뒤, 모든 blackboard_content는 그 visual_bible을 기반으로 작성하세요.
- 장면별 프롬프트는 그 장면 대사만 보고 만들면 실패입니다. 반드시 전체 대본의 장소·복장·상황 흐름을 반영하세요.
- 예: 전체 주제가 장례식장 절 예절이면, 모든 관련 장면에는 같은 장례식장, 같은 검은 정장/검은 원피스, 같은 조문 분위기가 유지되어야 합니다. 어느 장면에서도 갑자기 한복·밝은 캐주얼복·다른 장소로 바뀌면 실패입니다.
- 계속 등장하는 인물·복장·장소·소품은 visual_bible의 exact phrase를 blackboard_content에 그대로 반복하고, 장면마다 동작·카메라 구도만 바꾸세요.
{visual_style_guidelines}

【TTS 안전 및 최종 검수】
- scene.script에 해시태그, 샵, 별표, URL, 이모지, 영어 CTA, "구독 좋아요", "Shorts" 금지.
- 순수 한국어 구어체 문장과 괄호 글자 수 표기만 작성하세요.
- 실제 작성된 총 글자 수 합계가 {min_total_chars}~{max_total_chars}자 목표 기준에 완벽히 부합하도록 자가 검증을 마친 후 출력하세요.

【장면 설계】
- 장면 수는 정확히 {scene_count}개.
- 한 장면 = 한 포인트. 예외·이유·주의사항을 한 번에 몰아넣지 마세요.
- 각 장면은 앞 장면을 이어받아 하나의 이야기처럼 연결되어야 합니다.
}
"""


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
    "youtube_tags": ["알고보면쓸모있는", "신기한과학", "역사미스터리", "생활상식", "1분꿀팁", "소름주의", "지식쇼츠", "쇼츠트렌드"],
    "visual_bible": {
        "story_world": "One concise English sentence defining the exact world, setting, era, and mood that must stay fixed across every image.",
        "main_character": "Exact English phrase for recurring character appearance, age, hair, body, facial features, and expression language. Reuse verbatim in every relevant scene.",
        "wardrobe": "Exact English phrase for fixed clothing, colors, accessories, and formality level. Reuse verbatim in every relevant scene.",
        "primary_location": "Exact English phrase for recurring location architecture, props, lighting, and spatial layout. Reuse verbatim when the location continues.",
        "fixed_props": "Exact English phrase for recurring props and objects that should not change shape/color across scenes.",
        "continuity_notes": "English notes about what must never change, and what may change only by story progression."
    },
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
            "blackboard_content": "Full-frame visual scene description (English or Korean. South Park inspired cartoon scene, may include short Korean speech bubbles, signs, phone screens, map labels, or captions if useful.)",
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

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎙️ [나레이션 설정 및 보이스 연동]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- 성별 및 목소리: {voice_gender} ({voice_age})
- 분위기 및 톤: {voice_tone}
- 발화 속도 배속: {voice_speed}x (초당 글자수 {chars_per_second}자 기준)

이 나레이션 설정을 감안하여, 대본의 어투와 리듬감을 분위기(톤)와 발화 속도에 꼭 맞춰 작성해 주세요. 
- 지정된 속도({voice_speed}x, 초당 글자수 {chars_per_second}자)에 맞는 발화량과 템포감을 고려하여 대본을 작성하세요.
- 수퍼톤 TTS 엔진의 자연스러운 흐름을 위해 쉼표와 불필요한 문장 부호를 최소화하세요.

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
- blackboard_content는 사우스파크풍 만화 장면 묘사입니다. 짧은 한국어 말풍선·간판·지도 라벨·휴대폰 화면 문구를 넣어도 됩니다.
- 전체 주제 맥락을 반영해야 하며, 발표자·강사·칠판 구도 금지.
- 장면 전체를 채우는 메인 비주얼이어야 합니다.
- visual_bible을 먼저 만든 뒤, 모든 blackboard_content는 그 visual_bible을 기반으로 작성하세요.
- 장면별 프롬프트는 그 장면 대사만 보고 만들면 실패입니다. 반드시 전체 대본의 장소·복장·상황 흐름을 반영하세요.
- 예: 전체 주제가 장례식장 절 예절이면, 모든 관련 장면에는 같은 장례식장, 같은 검은 정장/검은 원피스, 같은 조문 분위기가 유지되어야 합니다. 어느 장면에서도 갑자기 한복·밝은 캐주얼복·다른 장소로 바뀌면 실패입니다.
- 계속 등장하는 인물·복장·장소·소품은 visual_bible의 exact phrase를 blackboard_content에 그대로 반복하고, 장면마다 동작·카메라 구도만 바꾸세요.
{visual_style_guidelines}

【TTS 안전】
- scene.script에 해시태그, 샵, 별표, URL, 이모지, 영어 CTA, "구독 좋아요", "Shorts" 금지.
- 순수 한국어 구어체 문장만 작성하세요.

【장면 설계】
- 장면 수는 정확히 {scene_count}개.
- 한 장면 = 한 포인트. 예외·이유·주의사항을 한 번에 몰아넣지 마세요.
- 각 장면은 앞 장면을 이어받아 하나의 이야기처럼 연결되어야 합니다.
"""


def get_system_prompt(
    style: str = "star-instructor", 
    scene_count: int = 12, 
    visual_style: str = "south-park-comic",
    voice_gender: str = "여성",
    voice_age: str = "청년",
    voice_tone: str = "차분하게",
    voice_speed: str = "1.12"
) -> str:
    if style == "ssul-shorts":
        duration_target = get_duration_target_ssul(scene_count, voice_speed)
        
        visual_style_guidelines = """- 비주얼 스타일 [CRITICAL - 따뜻한 에디토리얼 일러스트]:
  모든 이미지는 고급 모바일 매거진/뉴스레터에 쓰이는 polished editorial illustration 무드로 100% 고정되어야 합니다.
  각 장면의 blackboard_content는 "polished Korean editorial illustration, clean cinematic composition, expressive human gestures, premium magazine-style digital painting, warm natural light, refined color palette" 키워드를 포함하세요.
  흰 배경 아이콘처럼 만들지 말고, 장면 전체가 하나의 스토리 컷처럼 보이도록 공간·인물·소품의 관계를 묘사하세요."""

        # voice_category 및 voice_age_group 매핑
        voice_category = "female" if any(g in voice_gender for g in ["여", "female"]) else "male"
        
        if any(a in voice_age for a in ["아이", "child", "아동"]):
            voice_age_group = "child"
        elif any(a in voice_age for a in ["노인", "senior", "어르신"]):
            voice_age_group = "senior"
        else:
            voice_age_group = "adult"

        recommended_per_scene = duration_target.get("recommended_per_scene", 9)

        return (
            SSUL_SHORTS_PROMPT
            .replace("{scene_count}", str(scene_count))
            .replace("{min_total_chars}", str(duration_target["min_total_chars"]))
            .replace("{max_total_chars}", str(duration_target["max_total_chars"]))
            .replace("{target_total_chars}", str(duration_target["target_total_chars"]))
            .replace("{min_scene_chars}", str(duration_target["min_scene_chars"]))
            .replace("{max_scene_chars}", str(duration_target["max_scene_chars"]))
            .replace("{target_scene_chars}", str(duration_target["target_scene_chars"]))
            .replace("{voice_gender}", voice_gender)
            .replace("{voice_age}", voice_age)
            .replace("{voice_tone}", voice_tone)
            .replace("{voice_speed}", voice_speed)
            .replace("{chars_per_second}", str(duration_target["chars_per_second"]))
            .replace("{voice_category}", voice_category)
            .replace("{voice_age_group}", voice_age_group)
            .replace("{recommended_per_scene}", str(recommended_per_scene))
            .replace("{visual_style_guidelines}", visual_style_guidelines)
        )

    duration_target = get_duration_target(scene_count, voice_speed)
    
    if style == "ssul-shorts" or visual_style == "irasutoya":
        visual_style_guidelines = """- 비주얼 스타일 [CRITICAL - 따뜻한 에디토리얼 일러스트]:
  모든 이미지는 고급 모바일 매거진/뉴스레터에 쓰이는 polished editorial illustration 무드로 100% 고정되어야 합니다.
  각 장면의 blackboard_content는 "polished Korean editorial illustration, clean cinematic composition, expressive human gestures, premium magazine-style digital painting, warm natural light, refined color palette" 키워드를 포함하세요.
  흰 배경 아이콘처럼 만들지 말고, 장면 전체가 하나의 스토리 컷처럼 보이도록 공간·인물·소품의 관계를 묘사하세요."""
    elif visual_style == "botero":
        visual_style_guidelines = """- 비주얼 스타일 [CRITICAL]: Fernando Botero's style (Boterismo). 모든 인물, 동물, 사물은 극도로 뚱뚱하고 둥글고 부풀려진 극단적인 부피감(voluptuous exaggerated volume, plump, bloated)을 가지며, 부드럽고 매끄러운 곡선과 아웃라인을 가진 유화(oil painting flat shading) 느낌의 풍만하고 유머러스한 스타일로 묘사되어야 합니다. 모든 장면 설명(blackboard_content)에 "in Fernando Botero's style" 또는 "Boterismo style"을 include시키세요.
- 동일 인물/배경/사물 일관성 (Visual Consistency) [CRITICAL]:
  ① 주연 등장인물이 있는 경우, 첫 장면에 캐릭터의 세부 외모(예: 성별, 나이, 머리모양, 옷차림 색상/스타일, 안경 유무 등)를 명확히 정의하고, 그 캐릭터가 나오는 모든 장면의 blackboard_content에 '동일한 묘사 문구를 토씨 하나 틀리지 않고 그대로 재사용'하세요. 행동과 동작만 다르게 변경합니다.
     (예: "A extremely plump merchant in Botero style, round bloated face, thin mustache, wearing a tight blue suit and tiny red tie"가 반복해서 나와야 함)
  ② 계속 등장하는 사물이나 동일한 배경 장소(방, 상점, 거리 등)가 있다면, 해당 사물이나 배경의 상세 묘사(색상, 재질, 형태)도 모든 장면의 프롬프트에서 완벽히 일치하는 고정된 표현을 재사용해야 합니다."""
    elif visual_style == "webtoon-cinematic":
        visual_style_guidelines = """- 비주얼 스타일: premium Korean webtoon cinematic cutscene, dramatic but clean line art, expressive faces and gestures, soft painterly cel shading, high-quality mobile thumbnail readability.
- 동일 인물/배경/사물 일관성 (Visual Consistency) [CRITICAL]:
  ① visual_bible의 main_character, wardrobe, primary_location, fixed_props 문구를 관련 장면마다 영어로 그대로 반복하세요.
  ② 장면별로 바뀌는 것은 행동, 카메라 거리, 손 위치, 시선, 감정뿐입니다. 복장·장소·인물 외형은 스토리상 명시된 변화가 없으면 절대 바꾸지 마세요."""
    elif visual_style == "south-park-comic":
        visual_style_guidelines = """- 비주얼 스타일 [기본값 - 사우스파크풍 만화]:
  모든 이미지는 South Park inspired flat cutout cartoon style로 생성하세요. 두꺼운 검은 외곽선, 단순한 원형 눈, 종이 오려붙인 듯한 평면 캐릭터, 강한 원색, 과장된 표정, 유머러스한 상황 연출을 사용하세요.
  장면 안에 한국어 말풍선, 간판, 종이 메모, 휴대폰 화면, 지도 라벨 같은 짧은 한글 문구를 넣어도 됩니다. 단, 화면이 복잡해지지 않게 핵심 문구 1~2개만 크게 넣으세요.
  모든 장면은 같은 만화 세계관, 같은 캐릭터 디자인, 같은 색감과 컷아웃 질감을 유지하세요."""
    else:
        # Default South Park comic style; legacy cute-2d/modern-editorial map here too.
        visual_style_guidelines = """- 비주얼 스타일 [기본값 - 사우스파크풍 만화]:
  모든 이미지는 South Park inspired flat cutout cartoon style로 생성하세요. 두꺼운 검은 외곽선, 단순한 원형 눈, 종이 오려붙인 듯한 평면 캐릭터, 강한 원색, 과장된 표정, 유머러스한 상황 연출을 사용하세요.
  장면 안에 한국어 말풍선, 간판, 종이 메모, 휴대폰 화면, 지도 라벨 같은 짧은 한글 문구를 넣어도 됩니다. 단, 화면이 복잡해지지 않게 핵심 문구 1~2개만 크게 넣으세요.
  모든 장면은 같은 만화 세계관, 같은 캐릭터 디자인, 같은 색감과 컷아웃 질감을 유지하세요."""

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
        .replace("{voice_gender}", voice_gender)
        .replace("{voice_age}", voice_age)
        .replace("{voice_tone}", voice_tone)
        .replace("{voice_speed}", voice_speed)
        .replace("{chars_per_second}", str(duration_target["chars_per_second"]))
        .replace("{visual_style_guidelines}", visual_style_guidelines)
    )


def _speech_char_count(script: str) -> int:
    return len(re.sub(r"\s+", "", script or ""))


def _title_char_count(value: str) -> int:
    return len(re.sub(r"\s+", "", str(value or "")))


def _video_title_lengths_ok(video_title: Union[str, dict]) -> bool:
    if not isinstance(video_title, dict):
        return False
    highlight = video_title.get("highlight", "")
    rest = video_title.get("rest", "")
    return _title_char_count(highlight) == 10 and _title_char_count(rest) == 12


def _video_title_structure_ok(video_title: Union[str, dict], topic: str = "") -> bool:
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

    hashtag_line = " ".join(f"#{tag}" for tag in tags[:8])
    if not description:
        description = safe_topic or title.replace("#Shorts", "").strip()
    description = re.sub(r"\s+", " ", description).strip()
    existing_hashtags = re.findall(r"#([A-Za-z0-9가-힣_]+)", description)
    existing_hashtags = list(dict.fromkeys(existing_hashtags))
    merged_hashtags = list(dict.fromkeys(existing_hashtags + tags[:8]))
    if merged_hashtags:
        description = re.sub(r"(?:\s*#(?:[A-Za-z0-9가-힣_]+)\s*)+$", "", description).strip()
        description = f"{description}\n\n{' '.join(f'#{tag}' for tag in merged_hashtags)}".strip()

    return {
        "youtube_title": title,
        "youtube_description": description,
        "youtube_tags": tags,
    }


def _extract_json_text(text: str) -> str:
    """Extract a JSON object from agy output that may contain markdown fences."""
    raw = str(text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, flags=re.S | re.I)
    if fenced:
        return fenced.group(1).strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        return raw[start : end + 1].strip()
    return raw


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
    clean = re.sub(r"['\"“”‘’`]", "", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def _normalize_visual_prompt(value: str, topic: str, direction: str) -> str:
    clean = _strip_text_requests_from_visual_prompt(value)
    if not clean or len(clean) < 40:
        context = f"{topic} {direction}".strip()
        clean = (
            "A context-aware visual metaphor based on the full story: "
            f"{context[:160]}. Use concrete objects, action, and spatial contrast."
        )

    text_rule = (
        "South Park inspired flat cutout cartoon style. Short Korean speech bubbles, signs, labels, phone-screen text, or map labels are allowed when they improve the joke or explanation; keep text large and limited to one or two short phrases."
    )
    if "South Park" not in clean and "사우스파크" not in clean:
        clean = f"{clean}. {text_rule}"
    return clean[:900]


def _clean_visual_bible_value(value: str, fallback: str = "") -> str:
    clean = _strip_text_requests_from_visual_prompt(str(value or fallback or ""))
    clean = re.sub(r"\s+", " ", clean).strip(" ,.-")
    return clean[:260]


def _fallback_visual_bible(topic: str, direction: str, result: dict) -> dict:
    context = _clean_visual_bible_value(f"{topic}. {direction}", "the video's main topic")
    subject = _clean_visual_bible_value(result.get("subject", "knowledge short"), "knowledge short")
    return {
        "story_world": f"A consistent contemporary Korean visual story world about {context}.",
        "main_character": "The same ordinary Korean adult learner with natural black hair and realistic proportions, seen as part of the story not as a presenter.",
        "wardrobe": "Consistent simple modern clothing appropriate to the topic, with the same colors and formality level across all scenes unless the story explicitly changes it.",
        "primary_location": f"A consistent real-world setting that directly matches {subject} and the full story context, with stable lighting and recurring background layout.",
        "fixed_props": "The same key props from the topic repeated consistently with identical colors, shapes, and placement logic.",
        "continuity_notes": "Never change wardrobe, location, era, or character design between scenes unless the narration explicitly says the story moved or time passed.",
    }


def _compact_visual_bible(visual_bible: dict) -> str:
    if not isinstance(visual_bible, dict):
        return ""
    ordered_keys = ["story_world", "main_character", "wardrobe", "primary_location", "fixed_props", "continuity_notes"]
    parts = []
    for key in ordered_keys:
        value = _clean_visual_bible_value(visual_bible.get(key, ""))
        if value:
            parts.append(f"{key}: {value}")
    return " | ".join(parts)[:1200]


def _build_story_arc(scenes: list[dict]) -> str:
    pieces = []
    for scene in scenes or []:
        scene_id = scene.get("scene_id", len(pieces) + 1)
        script = re.sub(r"\([^)]*\)", "", str(scene.get("script", "")))
        script = re.sub(r"\s+", " ", script).strip(" .")
        visual = _strip_text_requests_from_visual_prompt(scene.get("blackboard_content") or scene.get("background_description") or "")
        pieces.append(f"Scene {scene_id}: narration={script[:90]}; visual_action={visual[:110]}")
    return " || ".join(pieces)[:1800]


def apply_visual_continuity_context(result: dict, topic: str = "", direction: str = "") -> dict:
    """Attach a global visual bible and full-story arc to every scene before image generation.

    Image generation still runs per scene, but each scene prompt now carries the same
    wardrobe/location/character constraints plus the whole 8/10/12-scene narrative arc.
    This prevents local prompts such as "bowing" from drifting into a hanbok scene when
    the full story is actually funeral etiquette in black mourning clothes.
    """
    if not isinstance(result, dict):
        return result
    scenes = result.get("scenes") or []
    visual_bible = result.get("visual_bible")
    if not isinstance(visual_bible, dict) or not any(str(v or "").strip() for v in visual_bible.values()):
        visual_bible = _fallback_visual_bible(topic, direction, result)
        result["visual_bible"] = visual_bible

    bible_context = _compact_visual_bible(visual_bible)
    story_arc = _build_story_arc(scenes)
    for scene in scenes:
        scene["visual_bible_context"] = bible_context
        scene["full_story_arc"] = story_arc
        base_visual = scene.get("background_description") or scene.get("blackboard_content") or ""
        scene["background_description"] = _normalize_visual_prompt(base_visual, topic, direction)
        scene["blackboard_content"] = scene["background_description"]
    return result


def _sanitize_narration_script(value: str, keep_parentheses: bool = False) -> str:
    script = str(value or "")
    script = script.replace("\r\n", "\n").replace("\r", "\n")
    if not keep_parentheses:
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


def sanitize_scene_scripts(script_data: dict, keep_parentheses: bool = False) -> dict:
    for scene in script_data.get("scenes", []):
        scene["script"] = _sanitize_narration_script(scene.get("script", ""), keep_parentheses=keep_parentheses)
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
    apply_visual_continuity_context(result, topic, direction)
    return result


async def research_topic(topic: str, direction: str = "") -> str:
    research_prompt = f"""다음 주제에 대해 내레이터 중심 지식 쇼츠 스크립트를 작성하기 위한 핵심 자료를 조사해주세요.
주제: {topic}
{f'의도/방향: {direction}' if direction else ''}
1. 팩트와 수치 2. 흥미로운 반전 포인트 3. 실생활 연결 고리를 정리해주세요."""

    try:
        return await generate_text_with_agy(
            research_prompt,
            system_instruction=(
                "당신은 한국어 쇼츠 대본 작성을 돕는 리서치 보조자입니다. "
                "웹 검색 도구가 없어도 알고 있는 범위에서 보수적으로 핵심 자료를 정리하고, "
                "불확실한 수치나 최신 규정은 단정하지 마세요."
            ),
            purpose="research",
        )
    except Exception as e:
        logger.warning(f"[Research] failed: {e}")
        return ""


async def generate_script(
    topic: str,
    tags: list[str] = None,
    direction: str = "",
    style: str = "star-instructor",
    scene_count: int = 12,
    visual_style: str = "south-park-comic",
    voice_gender: str = "여성",
    voice_age: str = "청년",
    voice_tone: str = "차분하게",
    voice_speed: str = "1.12"
) -> dict:
    if style == "ssul-shorts":
        duration_target = get_duration_target_ssul(scene_count, voice_speed)
        visual_style = "south-park-comic"
    else:
        duration_target = get_duration_target(scene_count, voice_speed)
    is_rich_input = len(direction) > 150
    
    research_data = ""
    if SCRIPT_RESEARCH_ENABLED and not is_rich_input:
        research_start = time.monotonic()
        research_data = await research_topic(topic, direction)
        logger.info("[ScriptTiming] research %.1fs chars=%s", time.monotonic() - research_start, len(research_data or ""))

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
각 blackboard_content는 전체 주제와 상황을 반영한 사우스파크풍 만화 이미지 프롬프트여야 합니다.
장면 이해를 돕는 짧은 한국어 말풍선, 간판, 지도 라벨, 휴대폰 화면 문구는 허용됩니다. 단, 핵심 문구 1~2개만 크게 쓰세요.
blackboard_content라는 이름을 쓰더라도 실제로는 장면 전체를 구성하는 메인 비주얼 설명입니다. 남자 강사, 발표 캐릭터, 칠판 중앙 배치 같은 연출은 넣지 마세요.
"""
    
    if research_data:
        user_prompt += f"\n참고 자료:\n{research_data}\n"

    last_result = None
    attempts = SCRIPT_GENERATION_ATTEMPTS
    for attempt in range(attempts):
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

        attempt_start = time.monotonic()
        response_text = await generate_text_with_agy(
            user_prompt + retry_instruction,
            system_instruction=get_system_prompt(
                style,
                scene_count,
                visual_style,
                voice_gender=voice_gender,
                voice_age=voice_age,
                voice_tone=voice_tone,
                voice_speed=voice_speed,
            ),
            response_mime_type="application/json",
            temperature=0.30 if is_rich_input else 0.45,
            purpose="script",
        )

        logger.info(
            "[ScriptTiming] script attempt=%s/%s %.1fs response_chars=%s",
            attempt + 1,
            attempts,
            time.monotonic() - attempt_start,
            len(response_text or ""),
        )

        result = _postprocess_script_result(
            json.loads(_extract_json_text(response_text)),
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
            result["tts_settings"] = {
                "gender": voice_gender,
                "age": voice_age,
                "tone": voice_tone,
                "speed": voice_speed
            }
            keep_parens = (style == "ssul-shorts")
            sanitize_scene_scripts(result, keep_parentheses=keep_parens)
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
        last_result["tts_settings"] = {
            "gender": voice_gender,
            "age": voice_age,
            "tone": voice_tone,
            "speed": voice_speed
        }
        keep_parens = (style == "ssul-shorts")
        sanitize_scene_scripts(last_result, keep_parentheses=keep_parens)
        await enrich_script_metadata(last_result, topic=topic, situation=last_result.get("situation_setting", {}).get("situation", ""))
    return last_result


async def generate_metadata_from_script(script_text: str, situation: str = "", topic: str = "") -> dict:
    metadata_prompt = f"""다음 쇼츠 대본을 분석해서 최신 유튜브 쇼츠 및 틱톡 알고리즘 트렌드를 완벽히 반영한 파괴력 있고 매력적인 형식의 메타데이터를 JSON으로 생성하세요.

조건:
- 제목은 100자 이내.
- 제목 앞부분에 핵심 키워드 1~2개를 자연스럽게 넣고, 스크롤을 바로 멈추게 하는 호기심/반전/손해회피 톤을 사용하세요.
- 제목에는 반드시 #Shorts 를 포함시키세요.
- 설명(youtube_description)의 구성:
  1. 첫 1~2문장은 대본의 핵심 반전이나 가장 킹받는/흥미로운 포인트를 담아 시청자의 눈길을 확 끌도록 자극적이지 않지만 트렌디하게 작성하세요.
  2. 본문 뒤에 1~2줄 띄우고, 이목을 끌 수 있는 **트렌디하고 강력한 해시태그 5~7개**를 달아주세요.
  3. 해시태그는 다음 3가지 유형을 믹스하여 구성하세요:
     - [트렌드/대세 태그 (1~2개)]: #shorts, #쇼츠, #인기급상승 등
     - [장르/감정 유도형 태그 (2~3개)]: 
       * 썰(Story) 대본인 경우: #썰, #공감, #사이다, #소름, #실화, #반전, #꿀잼 등 시청자 감정을 증폭하는 태그
       * 지식(Knowledge) 대본인 경우: #지식, #상식, #미스터리, #꿀팁, #알고보면, #소름주의, #정보 등 호기심과 가치를 극대화하는 태그
     - [핵심 주제 밀착형 태그 (2개)]: 대본 내용의 핵심 키워드를 반영한 구체적인 태그
- youtube_tags (태그 목록) 구성:
  - 사용자가 유튜브 검색창에 실제로 입력해 들어올 만한 **"실제 검색 유입용 롱테일 키워드"와 "최신 인기 검색어"** 8~12개를 믹스해서 리스트 형태로 작성하세요 (예: "회사 사이다 썰", "소름돋는 이야기", "반드시 알아야할 상식", "생활 꿀팁" 등). 단순 1단어 나열보다는 검색 유도형 구문 형태를 적극 반영해 주세요.
  - 중복 태그 및 영어 스팸식 키워드 도배는 금지하며, 철저하게 한국어 트렌드 톤으로 작성하세요.

출력 JSON:
{{
  "youtube_title": "제목 #Shorts",
  "youtube_description": "설명 본문\n\n#해시태그1 #해시태그2 #해시태그3",
  "youtube_tags": ["검색용 태그1", "검색용 태그2", "검색용 태그3"]
}}

주제: {topic}
상황: {situation}

대본:
{script_text}
"""
    response_text = await generate_text_with_agy(
        metadata_prompt,
        response_mime_type="application/json",
        temperature=0.35,
        purpose="metadata",
    )
    return _normalize_metadata(json.loads(_extract_json_text(response_text)), topic)
