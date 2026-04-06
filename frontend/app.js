/**
 * AI Shorts Generator - Frontend App
 */
const API_BASE = window.location.origin;
let currentJobId = null;
let pollInterval = null;
let currentScriptData = null; // Store script data for multi-step flow

// DOM Elements
const topicInput = document.getElementById('topic-input');
const directionInput = document.getElementById('direction-input');
const tagsInput = document.getElementById('tags-input');
const generateBtn = document.getElementById('generate-btn');
const progressSection = document.getElementById('progress-section');
const inputSection = document.getElementById('input-section');
const scriptSection = document.getElementById('script-section');
const resultSection = document.getElementById('result-section');
const errorSection = document.getElementById('error-section');
const appContainer = document.getElementById('app-container');
const progressFill = document.getElementById('progress-fill');
const progressPercent = document.getElementById('progress-percent');
const progressMessage = document.getElementById('progress-message');
const videoTitle = document.getElementById('video-title');
const scenesContainer = document.getElementById('scenes-container');
const resultVideo = document.getElementById('result-video');
const downloadBtn = document.getElementById('download-btn');
const newVideoBtn = document.getElementById('new-video-btn');
const retryBtn = document.getElementById('retry-btn');
const errorMessage = document.getElementById('error-message');
const confirmActions = document.getElementById('confirm-actions');
const confirmGenerateBtn = document.getElementById('confirm-generate-btn');
const regenerateBtn = document.getElementById('regenerate-btn');
const titleEditContainer = document.getElementById('title-edit-container');
const hookTitleHighlightInput = document.getElementById('hook-title-highlight-input');
const hookTitleRestInput = document.getElementById('hook-title-rest-input');
const fullScriptPreview = document.getElementById('full-script-preview');
const fullAudioInput = document.getElementById('full-audio-input');
const fullAudioStatus = document.getElementById('full-audio-status');
const styleOptions = document.querySelectorAll('.style-option');
const sceneCountOptions = document.querySelectorAll('.scene-count-option');
const modeAiTab = document.getElementById('mode-ai-tab');
const modeManualTab = document.getElementById('mode-manual-tab');
const aiModeContent = document.getElementById('ai-mode-content');
const manualModeContent = document.getElementById('manual-mode-content');
const manualSituationInput = document.getElementById('manual-situation-input');
let selectedStyle = 'teacher-student'; // Default style
let selectedSceneCount = 12; // Default scene count
let inputMode = 'ai'; // 'ai' or 'manual'

// Login Elements
const loginOverlay = document.getElementById('login-overlay');
const loginPassword = document.getElementById('login-password');
const loginBtn = document.getElementById('login-btn');
const loginError = document.getElementById('login-error');

/**
 * Handle Login
 */
async function handleLogin() {
    const password = loginPassword.value;
    if (!password) return;

    loginBtn.disabled = true;
    loginBtn.classList.add('loading');
    loginError.classList.add('hidden');

    try {
        const response = await fetch(`${API_BASE}/api/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password }),
        });

        if (response.ok) {
            const data = await response.json();
            localStorage.setItem('auth_token', data.access_token);
            loginOverlay.classList.add('hidden');
            appContainer.classList.remove('hidden');
            console.log('[Auth] Logged in successfully');
        } else {
            loginError.classList.remove('hidden');
        }
    } catch (err) {
        console.error('[Auth] Login error:', err);
        loginError.textContent = '서버 연결 오류';
        loginError.classList.remove('hidden');
    } finally {
        loginBtn.disabled = false;
        loginBtn.classList.remove('loading');
    }
}

/**
 * Check Initial Auth
 */
async function checkAuth() {
    const token = localStorage.getItem('auth_token');
    if (!token) {
        loginOverlay.classList.remove('hidden');
        appContainer.classList.add('hidden');
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/api/auth-check`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });

        if (response.ok) {
            loginOverlay.classList.add('hidden');
            appContainer.classList.remove('hidden');
            console.log('[Auth] Session active');
        } else {
            console.warn('[Auth] Session expired');
            localStorage.removeItem('auth_token');
            loginOverlay.classList.remove('hidden');
            appContainer.classList.add('hidden');
        }
    } catch (err) {
        console.error('[Auth] Check failed:', err);
        loginOverlay.classList.remove('hidden');
    }
}

/**
 * Fetch wrapper with Auth header
 */
async function fetchWithAuth(url, options = {}) {
    const token = localStorage.getItem('auth_token');
    if (!options.headers) options.headers = {};
    if (token) {
        options.headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch(url, options);
    
    // Auto logout on 401
    if (response.status === 401) {
        console.warn('[Auth] 401 Unauthorized - logging out');
        localStorage.removeItem('auth_token');
        loginOverlay.classList.remove('hidden');
        appContainer.classList.add('hidden');
        throw new Error('인증이 만료되었습니다. 다시 로그인해주세요.');
    }
    
    return response;
}

// Event Listeners
loginBtn.addEventListener('click', handleLogin);
loginPassword.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') handleLogin();
});

// Check auth on page load
window.addEventListener('DOMContentLoaded', checkAuth);

/**
 * Update the sidebar with concatenated script content for easy copy-pasting
 */
function updateFullScriptSidebar() {
    if (!currentScriptData || !fullScriptPreview) return;

    const getTitleStr = (vt) => typeof vt === 'object' ? `${vt.highlight || ''} ${vt.rest || ''}`.trim() : vt;
    const title = getTitleStr(currentScriptData.video_title) || '제목 없음';
    const subject = currentScriptData.subject || '미분류';

    let fullText = `제목: ${title}\n주제: ${subject}\n\n`;
    fullText += "━━━━━━━━━━━━━━━━━━━━━━\n\n";
    fullText += currentScriptData.scenes
        .map(scene => `[${scene.character}] ${scene.script}`)
        .join('\n\n');

    fullScriptPreview.textContent = fullText;
}

/**
 * Copy the entire content from the sidebar to clipboard
 */
function copyFullScript() {
    if (!fullScriptPreview) return;
    const text = fullScriptPreview.textContent;
    navigator.clipboard.writeText(text).then(() => {
        const btn = document.querySelector('.btn-copy-all');
        const originalText = btn.textContent;
        btn.textContent = '✅ 복사됨';
        setTimeout(() => btn.textContent = originalText, 2000);
    }).catch(err => {
        console.error('Copy failed:', err);
        alert('복사 실패!');
    });
}

// Event Listeners
generateBtn.addEventListener('click', () => {
    if (inputMode === 'manual') {
        generateManualScript();
    } else {
        startScriptGeneration();
    }
});
confirmGenerateBtn.addEventListener('click', startVideoGeneration);
newVideoBtn.addEventListener('click', resetUI);
regenerateBtn.addEventListener('click', () => {
    // Reset video player to avoid showing stale content
    resultVideo.src = '';
    resultVideo.load();
    downloadBtn.href = '#';

    // Clear old job ID
    currentJobId = null;

    resultSection.classList.add('hidden');
    startVideoGeneration();
});
retryBtn.addEventListener('click', handleRetry);

// Style Selection Toggle
styleOptions.forEach(option => {
    option.addEventListener('click', () => {
        styleOptions.forEach(opt => opt.classList.remove('active'));
        option.classList.add('active');
        selectedStyle = option.dataset.style;
        console.log('[UI] Style selected:', selectedStyle);
    });
});

// Scene Count Selection
sceneCountOptions.forEach(option => {
    option.addEventListener('click', () => {
        sceneCountOptions.forEach(opt => opt.classList.remove('active'));
        option.classList.add('active');
        selectedSceneCount = parseInt(option.dataset.count);
        console.log('[UI] Scene count selected:', selectedSceneCount);
    });
});

// Input Mode Tab Toggle
[modeAiTab, modeManualTab].forEach(tab => {
    tab.addEventListener('click', () => {
        const mode = tab.dataset.mode;
        inputMode = mode;
        modeAiTab.classList.toggle('active', mode === 'ai');
        modeManualTab.classList.toggle('active', mode === 'manual');
        aiModeContent.classList.toggle('hidden', mode !== 'ai');
        manualModeContent.classList.toggle('hidden', mode !== 'manual');
        console.log('[UI] Input mode:', mode);
    });
});

topicInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') startScriptGeneration();
});

/**
 * Step 1: Generate Script only
 */
async function startScriptGeneration() {
    const topic = topicInput.value.trim();
    if (!topic) {
        topicInput.focus();
        topicInput.style.borderColor = 'var(--error)';
        setTimeout(() => topicInput.style.borderColor = '', 1500);
        return;
    }

    const tags = tagsInput.value.split(',').map(t => t.trim()).filter(t => t);
    const direction = directionInput.value.trim();

    // Disable input
    generateBtn.disabled = true;
    generateBtn.classList.add('loading');

    // Show progress
    inputSection.classList.add('hidden');
    progressSection.classList.remove('hidden');
    resultSection.classList.add('hidden');
    errorSection.classList.add('hidden');
    scriptSection.classList.add('hidden');
    resetSteps();

    try {
        console.log('[Script] Generating...', { topic });
        progressMessage.textContent = '📝 스크립트 생성 중...';
        progressFill.style.width = '20%';
        progressPercent.textContent = '20%';

        const response = await fetchWithAuth(`${API_BASE}/api/generate-script`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ topic, tags, direction, style: selectedStyle, scene_count: selectedSceneCount }),
        });

        if (!response.ok) throw new Error(`스크립트 생성 실패 (${response.status})`);

        const data = await response.json();
        if (data.error) throw new Error(data.error);

        currentScriptData = data.script_data;
        showScriptPreview(currentScriptData);

        // Hide progress and show script preview
        progressSection.classList.add('hidden');
        scriptSection.classList.remove('hidden');
    } catch (err) {
        console.error('[Script] Error:', err);
        showError(`스크립트 생성 실패: ${err.message}`);
    } finally {
        generateBtn.disabled = false;
        generateBtn.classList.remove('loading');
    }
}

/**
 * Parse character names from a situation description string
 * e.g. "고속도로에서 단속된 운전자와 경찰이 대화하는 상황" → ['운전자', '경찰']
 * Returns null if we can't parse two distinct names
 */
function parseCharactersFromSituation(situation) {
    if (!situation) return null;

    // 1. Try to match specific "Name (A): Description" and "Name (B): Description" pattern
    // This handles the format you provided: "지수 (A): 30대 직장인..."
    const profileA = situation.match(/([가-힣\w\s]+)\s*\(A\)\s*:\s*([^\n]+)/i);
    const profileB = situation.match(/([가-힣\w\s]+)\s*\(B\)\s*:\s*([^\n]+)/i);

    if (profileA && profileB) {
        console.log(`[Manual] Parsed detailed profiles: A='${profileA[1]}', B='${profileB[1]}'`);
        return {
            charA: { name: profileA[1].trim(), description: profileA[2].trim() },
            charB: { name: profileB[1].trim(), description: profileB[2].trim() }
        };
    }

    // 2. Fallback to simple conjunction parser
    const separators = /와\s*|과\s*|이랑\s*|랑\s*|및\s*|그리고\s*|、|,/;
    const cleaned = situation
        .replace(/이?가\s*(대화|등장|나오|이야기|토론|논쟁|싸움|조우|상담|설명).*$/u, '')
        .replace(/하는\s*(상황|장면|설정).*$/u, '')
        .replace(/의\s*(대화|이야기).*$/u, '')
        .replace(/^[^\s]+에서\s+/, '')
        .trim();

    const parts = cleaned.split(separators).map(p => p.trim()).filter(p => p.length > 0 && p.length <= 15);
    
    if (parts.length >= 2) {
        const nameA = parts[partNumA || 0]; // Note: partNumA isn't defined here in original, 
        const nameB = parts[partNumB || 1]; // using 0 and 1 as defaults
        if (nameA && nameB && nameA !== nameB) {
            console.log(`[Manual] Parsed simple characters: A='${nameA}', B='${nameB}'`);
            return {
                charA: { name: nameA, description: `${nameA} character in the following situation: ${situation}` },
                charB: { name: nameB, description: `${nameB} character in the following situation: ${situation}` }
            };
        }
    }

    return null;
}

/**
 * Build a sensible background_description from the situation text
 */
function buildBackgroundDescription(situation) {
    if (!situation) return 'A simple clean background suitable for educational content';
    return `Scene from the following situation: ${situation}. Realistic and appropriate setting for this interaction.`;
}

/**
 * Manual Script Mode: Generate empty script data structure
 * Creates the same data shape as AI-generated scripts but with blank dialogue
 */
function generateManualScript() {
    const isTeacherStudent = selectedStyle === 'teacher-student';
    const situation = manualSituationInput ? manualSituationInput.value.trim() : '';

    // --- Try to extract character names from situation description ---
    const parsed = parseCharactersFromSituation(situation);

    let charA_Data, charB_Data;
    if (parsed) {
        charA_Data = parsed.charA;
        charB_Data = parsed.charB;
        // Ensure some basic style description if the parsed one is short
        if (charA_Data.description.length < 15) charA_Data.description = `${charA_Data.name} character in: ${situation}`;
        if (charB_Data.description.length < 15) charB_Data.description = `${charB_Data.name} character in: ${situation}`;
    } else if (isTeacherStudent) {
        charA_Data = { name: '전문가 (A)', description: 'A energetic and smart young professional in their late 20s or early 30s with a trendy business-casual look' };
        charB_Data = { name: '학습자 (B)', description: 'A curious university student or young office worker in their 20s with a casual, energetic appearance' };
    } else {
        charA_Data = { name: '전문가 A', description: 'Expert A: smart professional in their 30s with energetic and modern style' };
        charB_Data = { name: 'Expert B', description: 'Expert B: intelligent and enthusiastic professional in their 30s' };
    }

    const bgDescription = buildBackgroundDescription(situation);

    const charA = {
        id: 'char_a',
        name: charA_Data.name,
        description: charA_Data.description,
        voice_category: 'female',
        age_group: 'young-adult',
        color: '#7c5cff'
    };
    const charB = {
        id: 'char_b',
        name: charB_Data.name,
        description: charB_Data.description,
        voice_category: 'male',
        age_group: 'young-adult',
        color: '#5c9cff'
    };

    const scenes = [];
    for (let i = 0; i < selectedSceneCount; i++) {
        const isCharA = i % 2 === 0;
        scenes.push({
            scene_id: i + 1,
            character_id: isCharA ? 'char_a' : 'char_b',
            character: isCharA ? charA.name : charB.name,
            background: situation ? `${charA_Data.name}와 ${charB_Data.name}의 상황` : '배경',
            background_description: bgDescription,
            motion: '기본 동작',
            script: '',
            duration: 5,
            overlays: []
        });
    }

    currentScriptData = {
        video_title: { highlight: '', rest: '' },
        youtube_title: '',
        youtube_description: '',
        youtube_tags: [],
        core_knowledge: '',
        situation_setting: { time_period: '', situation: situation, concept: '' },
        characters: [charA, charB],
        scenes: scenes,
        _manual_situation: situation
    };

    // Show script preview
    inputSection.classList.add('hidden');
    showScriptPreview(currentScriptData);
    scriptSection.classList.remove('hidden');
    console.log(`[Manual] Created empty script with ${selectedSceneCount} scenes, charA='${charA.name}', charB='${charB.name}', situation: '${situation}'`);
}

/**
 * Swap the first-speaker / second-speaker assignment in all scenes
 * (toggle which character speaks at even positions vs odd positions)
 */
function swapSpeakerOrder() {
    if (!currentScriptData || !currentScriptData.scenes) return;

    const chars = currentScriptData.characters;
    if (!chars || chars.length < 2) return;

    const [charA, charB] = chars;

    currentScriptData.scenes = currentScriptData.scenes.map((scene) => {
        const isA = scene.character_id === charA.id;
        return {
            ...scene,
            character_id: isA ? charB.id : charA.id,
            character: isA ? charB.name : charA.name,
        };
    });

    // Re-render the scene list
    showScriptPreview(currentScriptData);
    console.log('[Manual] Speaker order swapped');
}

/**
 * Step 2: Confirm Script and Generate Visuals/Video
 */
async function startVideoGeneration() {
    if (!currentScriptData) return;

    confirmGenerateBtn.disabled = true;
    confirmGenerateBtn.classList.add('loading');

    // Show progress section - DON'T hide script section
    progressSection.classList.remove('hidden');
    confirmActions.classList.add('hidden'); // Hide confirm buttons during generation
    resetSteps();
    progressMessage.textContent = '🚀 영상 제작 시작...';

    try {
        // Auto-generate metadata if description is empty (manual script mode)
        if (!currentScriptData.youtube_description) {
            const scriptText = currentScriptData.scenes
                .map(scene => `[${scene.character}] ${scene.script}`)
                .filter(line => line.trim().length > 3)
                .join('\n');
            
            if (scriptText.length > 10) {
                console.log('[Metadata] Generating metadata from manual script...');
                progressMessage.textContent = '📝 설명 및 태그 생성 중...';
                progressFill.style.width = '5%';
                progressPercent.textContent = '5%';

                try {
                    const metaResponse = await fetchWithAuth(`${API_BASE}/api/generate-metadata`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            script_text: scriptText,
                            situation: currentScriptData._manual_situation || ''
                        }),
                    });

                    if (metaResponse.ok) {
                        const metaData = await metaResponse.json();
                        if (metaData.metadata) {
                            currentScriptData.youtube_title = metaData.metadata.youtube_title || '';
                            currentScriptData.youtube_description = metaData.metadata.youtube_description || '';
                            currentScriptData.youtube_tags = metaData.metadata.youtube_tags || [];
                            if (metaData.metadata.video_title && (!currentScriptData.video_title.highlight && !currentScriptData.video_title.rest)) {
                                currentScriptData.video_title = metaData.metadata.video_title;
                                // Update title inputs if visible
                                if (hookTitleHighlightInput) hookTitleHighlightInput.value = metaData.metadata.video_title.highlight || '';
                                if (hookTitleRestInput) hookTitleRestInput.value = metaData.metadata.video_title.rest || '';
                            }
                            console.log('[Metadata] Generated:', metaData.metadata.youtube_title);
                        }
                    }
                } catch (metaErr) {
                    console.warn('[Metadata] Could not generate metadata:', metaErr);
                    // Continue with video generation even if metadata fails
                }
            }
        }

        console.log('[Video] Starting generation...');
        progressMessage.textContent = '🚀 영상 제작 시작...';
        const response = await fetchWithAuth(`${API_BASE}/api/generate-video`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ script_data: currentScriptData }),
        });

        if (!response.ok) throw new Error(`영상 생성 요청 실패 (${response.status})`);

        const data = await response.json();
        currentJobId = data.job_id;

        // Start polling
        pollStatus();
        pollInterval = setInterval(pollStatus, 2000);
    } catch (err) {
        console.error('[Video] Error:', err);
        showError(`영상 제작 실패: ${err.message}`);
    } finally {
        confirmGenerateBtn.disabled = false;
        confirmGenerateBtn.classList.remove('loading');
    }
}

/**
 * Upload the generated video to YouTube
 */
async function uploadToYoutube(jobId) {
    const btn = document.getElementById('youtube-upload-btn');
    const statusDiv = document.getElementById('upload-status');

    if (!jobId) {
        alert("Job ID가 없습니다. 영상을 먼저 생성해주세요.");
        return;
    }
    const originalContent = btn.innerHTML;
    btn.innerHTML = '<span class="spinner"></span> 업로드 중...';
    statusDiv.textContent = '🚀 유튜브 API로 전송 중입니다. 브라우저 창을 닫지 마세요...';
    statusDiv.classList.remove('hidden');
    statusDiv.className = 'upload-status info';

    try {
        const response = await fetchWithAuth('/api/upload-youtube', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                job_id: jobId,
                title: currentScriptData.youtube_title || ((typeof currentScriptData.video_title === 'object' ? `${currentScriptData.video_title.highlight} ${currentScriptData.video_title.rest}` : currentScriptData.video_title) + " #Shorts"),
                description: currentScriptData.youtube_description || "AI로 자동 생성된 지식 쇼츠입니다. #AI #Knowledge #Shorts",
                tags: currentScriptData.youtube_tags || ["AI", "Shorts", "Knowledge"]
            })
        });

        const result = await response.json();

        if (result.status === 'success') {
            statusDiv.innerHTML = `✅ 업로드 성공! <a href="https://youtu.be/${result.video_id}" target="_blank" class="yt-link">유튜브에서 보기</a>`;
            statusDiv.className = 'upload-status success';
            btn.innerHTML = '✅ 업로드 완료';
        } else {
            throw new Error(result.error || '업로드 중 오류가 발생했습니다.');
        }
    } catch (err) {
        console.error('YouTube Upload Error:', err);
        statusDiv.textContent = '❌ 업로드 실패: ' + err.message;
        statusDiv.className = 'upload-status error';
        btn.disabled = false;
        btn.innerHTML = '📹 다시 시도';
    }
}

async function pollStatus() {
    if (!currentJobId) return;

    try {
        const response = await fetchWithAuth(`${API_BASE}/api/status/${currentJobId}`);
        if (!response.ok) return;

        const data = await response.json();
        updateProgress(data);

        if (data.status === 'completed') {
            clearInterval(pollInterval);
            pollInterval = null;
            showResult(data);
        } else if (data.status === 'error') {
            clearInterval(pollInterval);
            pollInterval = null;
            showError(data.message);
        }
    } catch (err) {
        console.error('[Poll] Error:', err);
    }
}

function updateProgress(data) {
    const { progress, message, status } = data;
    progressFill.style.width = `${progress}%`;
    progressPercent.textContent = `${progress}%`;
    progressMessage.textContent = message;

    updateStep('script', status, ['generating_script']);
    updateStep('images', status, ['generating_images']);
    updateStep('narration', status, ['generating_narration']);
    updateStep('video', status, ['composing_video', 'completed']);
}

function updateStep(stepName, currentStatus, activeStatuses) {
    const stepEl = document.querySelector(`.step[data-step="${stepName}"]`);
    if (!stepEl) return;

    const statusOrder = ['pending', 'generating_script', 'generating_images', 'generating_narration', 'composing_video', 'completed'];
    const currentIndex = statusOrder.indexOf(currentStatus);
    const stepStatuses = activeStatuses.map(s => statusOrder.indexOf(s));

    if (currentIndex > Math.max(...stepStatuses)) {
        stepEl.classList.remove('active');
        stepEl.classList.add('completed');
    } else if (activeStatuses.includes(currentStatus)) {
        stepEl.classList.add('active');
        stepEl.classList.remove('completed');
    }
}

function showScriptPreview(scriptData) {
    scriptSection.classList.remove('hidden');
    confirmActions.classList.remove('hidden');

    // Setup Hook Title Editor
    if (scriptData.video_title && hookTitleHighlightInput && hookTitleRestInput && titleEditContainer) {
        if (typeof scriptData.video_title === 'object') {
            hookTitleHighlightInput.value = scriptData.video_title.highlight || '';
            hookTitleRestInput.value = scriptData.video_title.rest || '';
        } else {
            const parts = scriptData.video_title.split(' ');
            hookTitleHighlightInput.value = parts[0] || '';
            hookTitleRestInput.value = parts.slice(1).join(' ');
            // Convert to object so edits work correctly
            scriptData.video_title = { highlight: parts[0] || '', rest: parts.slice(1).join(' ') };
        }
        titleEditContainer.classList.remove('hidden');

        // ADDED: Sync edits back to scriptData
        hookTitleHighlightInput.oninput = (e) => handleTitleEdit(e, 'highlight');
        hookTitleRestInput.oninput = (e) => handleTitleEdit(e, 'rest');
    }

    // Setup Subject Input
    const subjectInput = document.getElementById('subject-input');
    if (subjectInput) {
        subjectInput.value = scriptData.subject || '지식';
        // ADDED: Sync edits back to scriptData
        subjectInput.oninput = (e) => handleSubjectEdit(e);
    }

    // Show/hide speaker swap button (only for manual mode)
    const swapBtn = document.getElementById('btn-swap-speakers');
    if (swapBtn) {
        if (inputMode === 'manual') {
            swapBtn.classList.remove('hidden');
        } else {
            swapBtn.classList.add('hidden');
        }
    }

    scenesContainer.innerHTML = scriptData.scenes.map((scene, idx) => {
        const imageOverlay = (scene.overlays || []).find(ov => ov.type === 'image');
        const assetPath = imageOverlay ? imageOverlay.content : null;

        return `
        <div class="scene-item" 
            data-scene-idx="${idx}" 
            ondragover="handleDragOver(event)" 
            ondragleave="handleDragLeave(event)" 
            ondrop="handleDrop(event, ${idx})">
            <div class="scene-number">${scene.scene_id}</div>
            <div class="scene-details">
                <div class="scene-meta">
                    <span class="scene-tag">👤 ${scene.character}</span>
                    <span class="scene-tag">🏠 ${scene.background}</span>
                    <span class="scene-tag">🎭 ${scene.motion}</span>
                </div>
                <textarea class="scene-script-edit" 
                    oninput="handleScriptEdit(event, ${idx})"
                    onpaste="handlePaste(event, ${idx})"
                    placeholder="이 장면의 대사...">${scene.script || ''}</textarea>

                <!-- Scene Asset Controls -->
                <div class="scene-upload-group">
                    <label class="upload-label">
                        <span class="upload-icon">📁</span>
                        <span class="upload-text">오버레이 사진 업로드 (또는 대사창에 붙여넣기)</span>
                        <input type="file" accept="image/*,.gif" onchange="handleFileUpload(event, ${idx})">
                    </label>
                    <div class="uploaded-preview" id="preview-${idx}" ${assetPath ? 'style="display:block"' : ''}>
                        ${assetPath ? `<img src="${API_BASE}/output/${assetPath}"><button class="remove-upload" onclick="removeAsset(${idx})">×</button>` : ''}
                    </div>
                </div>

                <!-- AI Image Generation -->
                <div class="scene-ai-image-group">
                    <div class="ai-image-header">
                        <span class="ai-image-icon">🎨</span>
                        <span>AI 오버레이 이미지 생성</span>
                    </div>
                    <div class="ai-image-input-row">
                        <input type="text" class="ai-image-prompt" id="prompt-${idx}" 
                            placeholder="그림 설명을 입력하세요"
                            value="">
                        <button class="btn-ai-generate" onclick="handleAiImageGenerate(${idx})">생성</button>
                    </div>
                    <div id="ai-preview-container-${idx}" class="ai-image-preview hidden">
                        <!-- AI Generated Preview -->
                    </div>
                </div>

                <div class="scene-footer">
                    <span class="scene-duration">⏱ ${scene.duration || scene.durationInSeconds || 5}초</span>
                </div>
            </div>
        </div>
    `;
    }).join('');

    updateFullScriptSidebar();
}

/**
 * Handle scene-specific asset upload (called by file input)
 */
async function handleFileUpload(event, sceneIdx) {
    const file = event.target.files[0];
    if (!file) return;
    await uploadFileObject(file, sceneIdx);
}

/**
 * Handle clipboard paste events (pasting images)
 */
async function handlePaste(event, sceneIdx) {
    const clipboardData = event.clipboardData || (window.event && window.event.clipboardData);
    if (!clipboardData) return;
    
    const items = clipboardData.items;
    let imageFile = null;

    for (const item of items) {
        if (item.type.indexOf('image') !== -1) {
            imageFile = item.getAsFile();
            break;
        }
    }

    if (imageFile) {
        // We found an image! Upload it.
        console.log(`[Paste] Image detected for scene ${sceneIdx}`);
        await uploadFileObject(imageFile, sceneIdx);
    }
}

/**
 * Handle Drag & Drop events
 */
function handleDragOver(event) {
    event.preventDefault();
    event.stopPropagation();
    event.currentTarget.classList.add('drag-over');
}

function handleDragLeave(event) {
    event.preventDefault();
    event.stopPropagation();
    event.currentTarget.classList.remove('drag-over');
}

async function handleDrop(event, sceneIdx) {
    event.preventDefault();
    event.stopPropagation();
    event.currentTarget.classList.remove('drag-over');

    const file = event.dataTransfer.files[0];
    if (file && file.type.startsWith('image/')) {
        console.log(`[Drop] Image detected for scene ${sceneIdx}`);
        await uploadFileObject(file, sceneIdx);
    }
}

/**
 * Core upload logic used by both file input and clipboard paste
 */
async function uploadFileObject(file, sceneIdx) {
    if (!file) return;

    // Show immediate loading indicator in preview area
    const previewDiv = document.getElementById(`preview-${sceneIdx}`);
    previewDiv.style.display = 'block';
    previewDiv.innerHTML = `<div class="upload-loading">⏳ 업로드 중...</div>`;

    try {
        const formData = new FormData();
        formData.append('file', file);

        const response = await fetchWithAuth(`${API_BASE}/api/upload-asset`, {
            method: 'POST',
            body: formData,
        });

        if (!response.ok) throw new Error('업로드 실패');
        const data = await response.json();

        // Update overlays array in currentScriptData
        if (!currentScriptData.scenes[sceneIdx].overlays) {
            currentScriptData.scenes[sceneIdx].overlays = [];
        }
        currentScriptData.scenes[sceneIdx].overlays = currentScriptData.scenes[sceneIdx].overlays.filter(ov => ov.type !== 'image');
        currentScriptData.scenes[sceneIdx].overlays.push({
            type: 'image',
            content: data.path,
            position: 'center',
            startTime: 0,
            duration: currentScriptData.scenes[sceneIdx].duration || 5
        });

        // Update Preview UI
        previewDiv.innerHTML = `
            <img src="${API_BASE}/output/${data.path}">
            <button class="remove-upload" onclick="removeAsset(${sceneIdx})">×</button>
        `;
        console.log(`[Upload] Success: ${data.path} for scene ${sceneIdx}`);
    } catch (err) {
        previewDiv.style.display = 'none';
        previewDiv.innerHTML = '';
        alert('업로드 오류: ' + err.message);
    }
}

/**
 * Handle AI image generation for a specific scene
 */
async function handleAiImageGenerate(sceneIdx) {
    const promptInput = document.getElementById(`prompt-${sceneIdx}`);
    const prompt = promptInput.value.trim();
    if (!prompt && !currentScriptData.scenes[sceneIdx].script) {
        alert('이미지 설명이나 스크립트 대사가 필요합니다.');
        return;
    }

    const btn = event.target;
    const originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = '...';

    const previewContainer = document.getElementById(`ai-preview-container-${sceneIdx}`);
    previewContainer.classList.remove('hidden');
    previewContainer.innerHTML = '<div class="ai-image-loading">🎨 생성 중...</div>';

    try {
        const response = await fetchWithAuth(`${API_BASE}/api/generate-image`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                prompt: prompt || 'Detail related to the dialogue',
                scene_script: currentScriptData.scenes[sceneIdx].script + " (Situation: " + (currentScriptData._manual_situation || "") + ")"
            }),
        });

        if (!response.ok) throw new Error('이미지 생성 실패');
        const data = await response.json();

        previewContainer.innerHTML = `
            <img src="${API_BASE}/output/${data.path}">
            <div class="ai-preview-actions">
                <button class="btn-ai-use" onclick="useAiImage(${sceneIdx}, '${data.path}')">사용하기</button>
                <button class="btn-ai-regenerate" onclick="handleAiImageGenerate(${sceneIdx})">다시생성</button>
                <button class="btn-ai-cancel" onclick="hideAiPreview(${sceneIdx})">취소</button>
            </div>
        `;
    } catch (err) {
        previewContainer.innerHTML = `<div class="error-text">❌ 오류: ${err.message}</div>`;
        setTimeout(() => previewContainer.classList.add('hidden'), 3000);
    } finally {
        btn.disabled = false;
        btn.textContent = originalText;
    }
}

function useAiImage(sceneIdx, imagePath) {
    if (!currentScriptData.scenes[sceneIdx].overlays) {
        currentScriptData.scenes[sceneIdx].overlays = [];
    }
    currentScriptData.scenes[sceneIdx].overlays = currentScriptData.scenes[sceneIdx].overlays.filter(ov => ov.type !== 'image');
    currentScriptData.scenes[sceneIdx].overlays.push({
        type: 'image',
        content: imagePath,
        position: 'center',
        startTime: 0,
        duration: currentScriptData.scenes[sceneIdx].duration || 5
    });

    const previewDiv = document.getElementById(`preview-${sceneIdx}`);
    previewDiv.style.display = 'block';
    previewDiv.innerHTML = `
        <img src="${API_BASE}/output/${imagePath}">
        <button class="remove-upload" onclick="removeAsset(${sceneIdx})">×</button>
    `;
    hideAiPreview(sceneIdx);
}

function hideAiPreview(sceneIdx) {
    document.getElementById(`ai-preview-container-${sceneIdx}`).classList.add('hidden');
}

function removeAsset(sceneIdx) {
    if (currentScriptData && currentScriptData.scenes[sceneIdx] && currentScriptData.scenes[sceneIdx].overlays) {
        currentScriptData.scenes[sceneIdx].overlays = currentScriptData.scenes[sceneIdx].overlays.filter(ov => ov.type !== 'image');
    }
    const previewDiv = document.getElementById(`preview-${sceneIdx}`);
    previewDiv.style.display = 'none';
    previewDiv.innerHTML = '';
}

/**
 * Copy text from input/textarea to clipboard
 * Improved for mobile/iOS compatibility
 */
function copyToClipboard(elementId) {
    const el = document.getElementById(elementId);
    if (!el) return;
    
    const text = el.value || el.textContent;
    const btn = el.nextElementSibling;

    // Use modern Clipboard API if available
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(() => {
            showCopyFeedback(btn);
        }).catch(err => {
            console.error('[Copy] Clipboard API failed:', err);
            fallbackCopy(el, btn);
        });
    } else {
        fallbackCopy(el, btn);
    }
}

/**
 * Fallback copy method for older environmental or restricted contexts
 */
function fallbackCopy(el, btn) {
    try {
        // For iOS/Mobile: need to handle readonly and selection carefully
        const isReadOnly = el.hasAttribute('readonly');
        if (isReadOnly) el.removeAttribute('readonly');
        
        el.select();
        el.setSelectionRange(0, 99999);
        
        const successful = document.execCommand('copy');
        
        if (isReadOnly) el.setAttribute('readonly', true);
        
        if (successful) {
            showCopyFeedback(btn);
        } else {
            throw new Error('execCommand returned false');
        }
    } catch (err) {
        console.error('[Copy] Fallback failed:', err);
        alert('복사에 실패했습니다. 내용을 직접 선택해서 복사해주세요.');
    }
}

/**
 * Show visual feedback after successful copy
 */
function showCopyFeedback(btn) {
    if (!btn) return;
    const originalText = btn.textContent;
    btn.textContent = '✅ 복사됨';
    btn.classList.add('copied');
    setTimeout(() => {
        btn.textContent = originalText;
        btn.classList.remove('copied');
    }, 2000);
}

function handleTitleEdit(event, part) {
    if (currentScriptData) {
        if (typeof currentScriptData.video_title !== 'object') {
            currentScriptData.video_title = { highlight: '', rest: currentScriptData.video_title };
        }
        if (part === 'highlight') {
            currentScriptData.video_title.highlight = event.target.value;
        } else if (part === 'rest') {
            currentScriptData.video_title.rest = event.target.value;
        }
        updateFullScriptSidebar();
    }
}

function handleSubjectEdit(event) {
    if (currentScriptData) {
        currentScriptData.subject = event.target.value;
        updateFullScriptSidebar();
    }
}

function handleScriptEdit(event, idx) {
    if (currentScriptData && currentScriptData.scenes[idx]) {
        const text = event.target.value;
        currentScriptData.scenes[idx].script = text;
        
        // Update background context for manual mode if the script changed
        if (inputMode === 'manual' || !currentScriptData.scenes[idx].background_description) {
            const situation = currentScriptData._manual_situation || "";
            const charName = currentScriptData.scenes[idx].character;
            currentScriptData.scenes[idx].background_description = 
                `Scene with ${charName} in the following situation: ${situation}. ` +
                (text.trim() ? `Specific interaction: ${text.substring(0, 100)}. ` : "") +
                `Realistic and appropriate educational animation setting.`;
        }

        updateFullScriptSidebar();
    }
}

async function handleFullAudioUpload(event) {
    const file = event.target.files[0];
    if (!file) return;

    try {
        const formData = new FormData();
        formData.append('file', file);

        const response = await fetchWithAuth(`${API_BASE}/api/upload-asset`, {
            method: 'POST',
            body: formData,
        });

        if (!response.ok) throw new Error('오디오 업로드 실패');
        const data = await response.json();

        if (currentScriptData) {
            currentScriptData.full_audio_path = data.path;
        }

        const statusDiv = document.getElementById('full-audio-status');
        if (statusDiv) {
            statusDiv.classList.remove('hidden');
            statusDiv.querySelector('.status-filename').textContent = file.name;
        }
    } catch (err) {
        alert('오디오 업로드 오류: ' + err.message);
    }
}

function removeFullAudio() {
    if (currentScriptData) {
        delete currentScriptData.full_audio_path;
    }
    const statusDiv = document.getElementById('full-audio-status');
    if (statusDiv) {
        statusDiv.classList.add('hidden');
    }
    const fileInput = document.getElementById('full-audio-input');
    if (fileInput) {
        fileInput.value = '';
    }
}


// Make globally accessible
window.handleScriptEdit = handleScriptEdit;
window.handleTitleEdit = handleTitleEdit;
window.handleSubjectEdit = handleSubjectEdit;
window.handleFullAudioUpload = handleFullAudioUpload;
window.removeFullAudio = removeFullAudio;
window.handleFileUpload = handleFileUpload;
window.handleAiImageGenerate = handleAiImageGenerate;
window.useAiImage = useAiImage;
window.hideAiPreview = hideAiPreview;
window.removeAsset = removeAsset;
window.copyFullScript = copyFullScript;
window.copyToClipboard = copyToClipboard;
window.swapSpeakerOrder = swapSpeakerOrder;

function showResult(data) {
    resultSection.classList.remove('hidden');
    progressSection.classList.add('hidden');

    // Scroll to result
    resultSection.scrollIntoView({ behavior: 'smooth' });

    const videoUrl = `${API_BASE}${data.video_url}`;
    resultVideo.src = videoUrl;
    resultVideo.load();

    // Position YouTube Upload button inside result-actions
    const resultActions = resultSection.querySelector('.result-actions');
    let uploadBtn = document.getElementById('youtube-upload-btn');

    if (!uploadBtn) {
        uploadBtn = document.createElement('button');
        uploadBtn.id = 'youtube-upload-btn';
        uploadBtn.className = 'btn btn-secondary youtube-btn';
        uploadBtn.innerHTML = '<span class="btn-icon">📹</span> YouTube에 업로드';
        resultActions.appendChild(uploadBtn);

        const statusDiv = document.createElement('div');
        statusDiv.id = 'upload-status';
        statusDiv.className = 'upload-status hidden';
        resultSection.appendChild(statusDiv);

        uploadBtn.onclick = () => uploadToYoutube(data.job_id);
    } else {
        uploadBtn.disabled = false;
        uploadBtn.innerHTML = '<span class="btn-icon">📹</span> YouTube에 업로드';
        document.getElementById('upload-status').classList.add('hidden');
        uploadBtn.onclick = () => uploadToYoutube(data.job_id);
    }

    // Populate YouTube Metadata Section
    const youtubeMetaSection = document.getElementById('youtube-meta-section');
    const ytTitleInput = document.getElementById('yt-meta-title');
    const ytDescTextarea = document.getElementById('yt-meta-desc');

    if (currentScriptData) {
        const getTitleStr = (vt) => typeof vt === 'object' ? `${vt.highlight || ''} ${vt.rest || ''}`.trim() : vt;
        const defaultTitle = getTitleStr(currentScriptData.video_title) + " #Shorts";
        ytTitleInput.value = currentScriptData.youtube_title || defaultTitle;

        const desc = currentScriptData.youtube_description || "";
        const tags = (currentScriptData.youtube_tags || []).map(t => `#${t.replace(/\s+/g, '')}`).join(' ');
        ytDescTextarea.value = `${desc}\n\n${tags}`;

        // Sync metadata edits back to scriptData
        ytTitleInput.oninput = (e) => { currentScriptData.youtube_title = e.target.value; };
        ytDescTextarea.oninput = (e) => { 
            // Simple logic: split back into description and tags (heuristic)
            const fullText = e.target.value;
            const parts = fullText.split('\n\n');
            currentScriptData.youtube_description = parts[0] || '';
            // We don't necessarily need to parse tags back perfectly as the whole description is what matters for YT upload here
        };

        youtubeMetaSection.classList.remove('hidden');
    }

    resultVideo.play().catch(e => console.warn('Auto-play failed:', e));

    // Use the download-specific API endpoint to force download on mobile
    const filename = `shorts_${currentJobId}.mp4`;
    downloadBtn.href = `${API_BASE}/api/download/${filename}`;
    downloadBtn.download = filename;
    
    generateBtn.disabled = false;
    generateBtn.classList.remove('loading');
}

function showError(msg) {
    errorSection.classList.remove('hidden');
    progressSection.classList.add('hidden');
    errorMessage.textContent = msg;
    generateBtn.disabled = false;
    generateBtn.classList.remove('loading');
}

function resetSteps() {
    document.querySelectorAll('.step').forEach(el => el.classList.remove('active', 'completed'));
    progressFill.style.width = '0%';
    progressPercent.textContent = '0%';
    progressMessage.textContent = '준비 중...';
}

function handleRetry() {
    errorSection.classList.add('hidden');
    if (currentScriptData) {
        console.log('[Retry] Retrying video generation from existing script...');
        startVideoGeneration();
    } else {
        console.log('[Retry] No script data, resetting to start.');
        resetUI();
    }
}

function resetUI() {
    currentJobId = null;
    currentScriptData = null;
    if (pollInterval) {
        clearInterval(pollInterval);
        pollInterval = null;
    }
    inputSection.classList.remove('hidden');
    progressSection.classList.add('hidden');
    resultSection.classList.add('hidden');
    errorSection.classList.add('hidden');
    scriptSection.classList.add('hidden');
    confirmActions.classList.add('hidden');
    generateBtn.disabled = false;
    generateBtn.classList.remove('loading');
    topicInput.value = '';
    directionInput.value = '';
    tagsInput.value = '';
    // Reset input mode to AI
    inputMode = 'ai';
    modeAiTab.classList.add('active');
    modeManualTab.classList.remove('active');
    aiModeContent.classList.remove('hidden');
    manualModeContent.classList.add('hidden');
    // Reset scene count to 12
    selectedSceneCount = 12;
    sceneCountOptions.forEach(opt => {
        opt.classList.toggle('active', opt.dataset.count === '12');
    });
    topicInput.focus();
}
