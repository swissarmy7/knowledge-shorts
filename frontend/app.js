/**
 * AI Shorts Studio - Frontend App (YouTube Layout Edition)
 */
const APP_BASE = new URL('.', window.location.href);
let currentJobId = null;
let pollInterval = null;
let currentScriptData = null; 
let currentHistoryId = null;
const ACTIVE_JOB_STORAGE_KEY = 'active_shorts_job_id';

function buildAppUrl(path = '') {
    return new URL(String(path).replace(/^\/+/, ''), APP_BASE).toString();
}

// DOM Elements - Auth
const loginOverlay = document.getElementById('login-overlay');
const loginPassword = document.getElementById('login-password');
const loginBtn = document.getElementById('login-btn');
const loginError = document.getElementById('login-error');
const appContainer = document.getElementById('app-container');

// DOM Elements - Steps
const inputStep = document.getElementById('input-step');
const workspaceStep = document.getElementById('workspace-step');
const historySection = document.getElementById('history-section');

// DOM Elements - Inputs
const topicInput = document.getElementById('topic-input');
const directionInput = document.getElementById('direction-input');
const tagsInput = document.getElementById('tags-input');
const generateBtn = document.getElementById('generate-btn');
const sceneCountOptions = document.querySelectorAll('.scene-count-option');

// DOM Elements - Editor
const scenesContainer = document.getElementById('scenes-container');
const hookTitleHighlightInput = document.getElementById('hook-title-highlight-input');
const hookTitleRestInput = document.getElementById('hook-title-rest-input');
const subjectInput = document.getElementById('subject-input');
const scriptStats = document.getElementById('script-stats');
const youtubeTitleInput = document.getElementById('youtube-title-input');
const youtubeDescriptionInput = document.getElementById('youtube-description-input');
const youtubeTagsInput = document.getElementById('youtube-tags-input');
const fullAudioStatus = document.getElementById('full-audio-status');
const confirmGenerateBtn = document.getElementById('confirm-generate-btn');
const backToInputBtn = document.getElementById('back-to-input-btn');
const regenerateScriptBtn = document.getElementById('regenerate-script-btn');

// DOM Elements - Progress & Result
const progressSection = document.getElementById('progress-section');
const progressFill = document.getElementById('progress-fill');
const progressPercent = document.getElementById('progress-percent');
const progressMessage = document.getElementById('progress-message');
const realtimeLog = document.getElementById('realtime-log');
const logStatusDot = document.getElementById('log-status-dot');
const resultSection = document.getElementById('result-section');
const resultVideo = document.getElementById('result-video');
const resultYoutubeTitle = document.getElementById('result-youtube-title');
const resultYoutubeDescription = document.getElementById('result-youtube-description');
const resultYoutubeTags = document.getElementById('result-youtube-tags');
const copyMetaBtn = document.getElementById('copy-meta-btn');
const downloadBtn = document.getElementById('download-btn');
const youtubeUploadBtn = document.getElementById('youtube-upload-btn');
const newVideoBtn = document.getElementById('new-video-btn');
const retryBtn = document.getElementById('retry-btn');
const errorSection = document.getElementById('error-section');
const errorMessage = document.getElementById('error-message');

// DOM Elements - Nav
const navCreateBtn = document.getElementById('nav-create-btn');
const navHistoryBtn = document.getElementById('nav-history-btn');
const historyList = document.getElementById('history-list');
const historyRefreshBtn = document.getElementById('history-refresh-btn');
const logoHome = document.getElementById('logo-home');
const menuBtn = document.querySelector('.menu-btn');

let selectedSceneCount = 12;
let lastMessage = "";

/**
 * Navigation Helpers
 */
function showStep(stepId) {
    [inputStep, workspaceStep, historySection].forEach(el => el.classList.add('hidden'));
    const target = document.getElementById(stepId);
    if (target) target.classList.remove('hidden');
    
    // Update nav active state
    navCreateBtn.classList.toggle('active', stepId !== 'history-section');
    navHistoryBtn.classList.toggle('active', stepId === 'history-section');
}

function resetUI() {
    if (currentScriptData && !confirm('진행 중인 작업이 사라집니다. 정말 처음으로 돌아갈까요?')) return;
    
    currentJobId = null;
    currentScriptData = null;
    currentHistoryId = null;
    if (pollInterval) clearInterval(pollInterval);
    pollInterval = null;
    
    topicInput.value = '';
    directionInput.value = '';
    tagsInput.value = '';
    hookTitleHighlightInput.value = '';
    hookTitleRestInput.value = '';
    subjectInput.value = '';
    youtubeTitleInput.value = '';
    youtubeDescriptionInput.value = '';
    youtubeTagsInput.value = '';
    resultVideo.removeAttribute('src');
    resultYoutubeTitle.textContent = '';
    resultYoutubeDescription.textContent = '';
    resultYoutubeTags.textContent = '';
    resetSteps();
    
    showStep('input-step');
    resultSection.classList.add('hidden');
    progressSection.classList.remove('hidden'); 
    errorSection.classList.add('hidden');
}

function resetGenerateButton() {
    if (!confirmGenerateBtn) return;
    confirmGenerateBtn.disabled = false;
    confirmGenerateBtn.textContent = '🎬 최종 영상 생성하기';
}

/**
 * Authentication
 */
async function handleLogin() {
    const password = loginPassword.value;
    if (!password) return;
    try {
        const response = await fetch(buildAppUrl('api/login'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password }),
        });
        if (response.ok) {
            const data = await response.json();
            localStorage.setItem('auth_token', data.access_token);
            loginOverlay.classList.add('hidden');
            appContainer.classList.remove('hidden');
            initializeAfterAuth();
        } else {
            const data = await response.json().catch(() => ({}));
            loginError.textContent = data.detail || '비밀번호가 올바르지 않습니다.';
            loginError.classList.remove('hidden');
        }
    } catch (err) {
        loginError.textContent = '서버 연결 오류';
        loginError.classList.remove('hidden');
    }
}

async function checkAuth() {
    const token = localStorage.getItem('auth_token');
    if (!token) return;
    try {
        const response = await fetch(buildAppUrl('api/auth-check'), {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (response.ok) {
            loginOverlay.classList.add('hidden');
            appContainer.classList.remove('hidden');
            initializeAfterAuth();
        }
    } catch (e) {}
}

async function initializeAfterAuth() {
    await loadHistory();
}

/**
 * Script Generation (Step 1 -> Step 2 transition)
 */
async function startScriptGeneration() {
    const topic = topicInput.value.trim();
    if (!topic) {
        topicInput.focus();
        return;
    }

    currentJobId = null;
    if (pollInterval) clearInterval(pollInterval);
    pollInterval = null;
    resetSteps();
    resultSection.classList.add('hidden');
    errorSection.classList.add('hidden');
    progressSection.classList.remove('hidden');

    generateBtn.disabled = true;
    generateBtn.textContent = '기획 중...';

    try {
        const response = await fetchWithAuth(buildAppUrl('api/generate-script'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                topic,
                tags: tagsInput.value.split(','),
                direction: directionInput.value,
                style: 'star-instructor',
                scene_count: selectedSceneCount
            }),
        });

        const data = await parseJson(response);
        if (data.error) throw new Error(data.error);

        currentScriptData = data.script_data;
        showStep('workspace-step');
        showScriptPreview(currentScriptData);
    } catch (err) {
        alert('스크립트 생성 실패: ' + err.message);
    } finally {
        generateBtn.disabled = false;
        generateBtn.textContent = '다음 단계로 ➜';
    }
}

async function regenerateScript() {
    if (!topicInput.value.trim()) {
        showStep('input-step');
        topicInput.focus();
        return;
    }

    if (currentScriptData && !confirm('현재 편집 중인 대본을 새로 생성된 대본으로 교체할까요?')) return;
    await startScriptGeneration();
}

/**
 * Editor Rendering
 */
function showScriptPreview(scriptData) {
    if (!scriptData) return;
    resetGenerateButton();
    
    // Populate Title Card
    if (typeof scriptData.video_title === 'object') {
        hookTitleHighlightInput.value = scriptData.video_title.highlight || '';
        hookTitleRestInput.value = scriptData.video_title.rest || '';
    }
    subjectInput.value = scriptData.subject || '';
    youtubeTitleInput.value = scriptData.youtube_title || '';
    youtubeDescriptionInput.value = scriptData.youtube_description || '';
    youtubeTagsInput.value = (scriptData.youtube_tags || []).join(', ');
    if (scriptData.full_audio_path) {
        fullAudioStatus.querySelector('.status-filename').textContent = scriptData.full_audio_path.split('/').pop();
        fullAudioStatus.classList.remove('hidden');
    } else {
        fullAudioStatus.classList.add('hidden');
    }

    // Render Scenes
    scenesContainer.innerHTML = scriptData.scenes.map((scene, idx) => {
        const imageOverlay = (scene.overlays || []).find(ov => ov.type === 'image');
        const assetPath = imageOverlay ? imageOverlay.content : null;

        return `
        <div class="scene-item">
            <div class="scene-number">${scene.scene_id}</div>
            
            <div class="editor-label">🎙️ 강사 내레이션</div>
            <textarea class="scene-script-edit" oninput="handleScriptEdit(event, ${idx})">${scene.script || ''}</textarea>
            <div class="scene-script-meta">
                <span id="scene-char-count-${idx}" class="scene-char-count"></span>
            </div>

            <div class="editor-label">🖍️ 칠판 연출 AI 힌트 (글자 없는 이미지)</div>
            <textarea class="scene-bg-edit" oninput="handleBgEdit(event, ${idx})">${scene.background_description || ''}</textarea>

            <div class="scene-overlay-section">
                <div class="editor-label">🖼️ 오버레이 (칠판 영역)</div>
                <div class="overlay-visualizer">
                    <div class="blackboard-zone">
                        <div id="preview-${idx}">
                            ${assetPath ? `<img src="${buildAppUrl(`output/${assetPath}`)}" class="overlay-preview-img">` : '<span style="opacity:0.3; font-size:10px;">칠판 영역</span>'}
                        </div>
                    </div>
                </div>
                <div style="display:flex; gap:8px;">
                    <label class="btn-yt-action btn-sm">
                        📁 업로드 <input type="file" style="display:none" onchange="handleFileUpload(event, ${idx})">
                    </label>
                    <button class="btn-yt-action btn-sm" onclick="handleAiImageGenerate(${idx})">🎨 AI 생성</button>
                    ${assetPath ? `<button class="btn-yt-action btn-sm border" onclick="removeAsset(${idx})">🗑️ 제거</button>` : ''}
                </div>
                <div id="ai-preview-container-${idx}" class="hidden" style="margin-top:10px;"></div>
            </div>
        </div>
        `;
    }).join('');

    updateScriptStats();
}

function countSpeechChars(text = '') {
    return String(text).replace(/\s+/g, '').length;
}

function updateScriptStats() {
    if (!currentScriptData) {
        if (scriptStats) scriptStats.textContent = '';
        return;
    }

    const target = currentScriptData.duration_target || {};
    const scenes = currentScriptData.scenes || [];
    const totalChars = scenes.reduce((sum, scene) => sum + countSpeechChars(scene.script || ''), 0);
    currentScriptData.speech_char_count = totalChars;

    if (scriptStats) {
        const minTotal = target.min_total_chars || 0;
        const maxTotal = target.max_total_chars || 0;
        const minScene = target.min_scene_chars || 0;
        const maxScene = target.max_scene_chars || 0;
        const totalStatus = totalChars > maxTotal ? '조금 김' : totalChars < minTotal ? '조금 짧음' : '적정';
        scriptStats.innerHTML = `
            총 대본 글자수 <strong>${totalChars}자</strong> / 권장 ${minTotal}~${maxTotal}자 (${totalStatus})<br>
            장면당 권장 글자수 ${minScene}~${maxScene}자
        `;
    }

    scenes.forEach((scene, idx) => {
        const el = document.getElementById(`scene-char-count-${idx}`);
        if (!el) return;
        const chars = countSpeechChars(scene.script || '');
        const maxScene = target.max_scene_chars || 0;
        const minScene = target.min_scene_chars || 0;
        el.textContent = `현재 ${chars}자 / 권장 ${minScene}~${maxScene}자`;
        el.classList.toggle('over', !!maxScene && chars > maxScene);
    });
}

/**
 * Final Video Generation
 */
async function startVideoGeneration() {
    if (!currentScriptData) return;

    if (pollInterval) clearInterval(pollInterval);
    pollInterval = null;
    currentJobId = null;

    confirmGenerateBtn.disabled = true;
    confirmGenerateBtn.textContent = '영상 제작 요청 중...';
    
    resultSection.classList.add('hidden');
    errorSection.classList.add('hidden');
    progressSection.classList.remove('hidden');
    resetSteps();

    try {
        const response = await fetchWithAuth(buildAppUrl('api/generate-video'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ script_data: currentScriptData }),
        });
        const data = await parseJson(response);
        if (data.error || !data.job_id) {
            throw new Error(data.error || '영상 작업을 시작하지 못했습니다.');
        }
        currentJobId = data.job_id;
        
        pollStatus();
        pollInterval = setInterval(pollStatus, 2000);
    } catch (err) {
        showError(err.message);
    }
}

/**
 * Polling & Progress
 */
async function pollStatus() {
    if (!currentJobId) return;
    try {
        const response = await fetchWithAuth(buildAppUrl(`api/status/${encodeURIComponent(currentJobId)}`));
        if (!response.ok) return;
        const data = await parseJson(response);
        updateProgress(data);
        if (data.status === 'completed') {
            clearInterval(pollInterval);
            pollInterval = null;
            showResult(data);
            loadHistory();
        } else if (data.status === 'error') {
            clearInterval(pollInterval);
            pollInterval = null;
            showError(data.message);
        }
    } catch (e) {
        console.error('Polling error:', e);
    }
}

function updateProgress(data) {
    const { progress, message, status, logs } = data;
    if (progressFill) progressFill.style.width = `${progress}%`;
    if (progressPercent) progressPercent.textContent = `${progress}%`;
    if (progressMessage) progressMessage.textContent = message;

    if (logs && realtimeLog) {
        realtimeLog.innerHTML = logs.map(l => `<div class="log-line">${l}</div>`).join('');
        realtimeLog.scrollTop = realtimeLog.scrollHeight;
    }
    
    if (logStatusDot) {
        logStatusDot.className = (status === 'pending' || status.includes('generating') || status === 'composing_video') ? 'dot active' : 'dot';
    }
    
    // Update pipe items
    document.querySelectorAll('.pipe-item').forEach(item => {
        const step = item.dataset.step;
        const isActive = (step === 'script' && status.includes('script')) ||
                         (step === 'images' && status.includes('images')) ||
                         (step === 'narration' && status.includes('narration')) ||
                         (step === 'video' && (status === 'composing_video' || status === 'completed'));
        item.classList.toggle('active', isActive);
    });
}

function showResult(data) {
    resetGenerateButton();
    progressSection.classList.add('hidden');
    resultSection.classList.remove('hidden');
    resultVideo.src = buildAppUrl(String(data.video_url || '').replace(/^\/+/, ''));
    resultVideo.load();
    downloadBtn.href = buildAppUrl(`api/download/${encodeURIComponent(`shorts_${data.job_id}.mp4`)}`);
    youtubeUploadBtn.onclick = () => uploadToYoutube(data.job_id);
    if (currentScriptData) {
        resultYoutubeTitle.textContent = currentScriptData.youtube_title || '';
        resultYoutubeDescription.textContent = currentScriptData.youtube_description || '';
        resultYoutubeTags.textContent = (currentScriptData.youtube_tags || [])
            .map((tag) => `#${String(tag).replace(/^#+/, '')}`)
            .join(' ');
    }
}

function showError(msg) {
    resetGenerateButton();
    progressSection.classList.add('hidden');
    errorSection.classList.remove('hidden');
    errorMessage.textContent = msg;
}

function resetSteps() {
    if (progressFill) progressFill.style.width = '0%';
    if (progressPercent) progressPercent.textContent = '0%';
    if (progressMessage) progressMessage.textContent = '준비 중...';
    if (realtimeLog) realtimeLog.innerHTML = '';
    if (logStatusDot) logStatusDot.className = 'dot';
}

/**
 * Event Handlers (Global Scope for inline HTML calls)
 */
async function fetchWithAuth(url, options = {}) {
    const token = localStorage.getItem('auth_token');
    if (!options.headers) options.headers = {};
    if (token) options.headers['Authorization'] = `Bearer ${token}`;
    let res;
    try {
        res = await fetch(url, options);
    } catch (networkErr) {
        throw new Error('서버 연결 실패. 백엔드 서버가 실행 중인지 확인해주세요.');
    }
    if (res.status === 401) {
        localStorage.removeItem('auth_token');
        loginOverlay.classList.remove('hidden');
        appContainer.classList.add('hidden');
        throw new Error('인증이 만료되었습니다. 다시 로그인해주세요.');
    }
    return res;
}

/** JSON 파싱 실패 시 HTML(502/서버오류) 여부를 감지해 명확한 메시지로 변환 */
async function parseJson(res) {
    const ct = res.headers.get('content-type') || '';
    if (!ct.includes('json')) {
        throw new Error(`서버 오류 (HTTP ${res.status}). 서버가 재시작 중이거나 일시적 오류가 발생했습니다. 잠시 후 다시 시도해주세요.`);
    }
    return res.json();
}

window.handleScriptEdit = (e, idx) => {
    if (!currentScriptData) return;
    currentScriptData.scenes[idx].script = e.target.value;
    updateScriptStats();
};
window.handleBgEdit = (e, idx) => { if(currentScriptData) currentScriptData.scenes[idx].background_description = e.target.value; };
window.handleTitleEdit = () => {
    if (!currentScriptData) return;
    if (typeof currentScriptData.video_title !== 'object' || currentScriptData.video_title === null) {
        currentScriptData.video_title = { highlight: '', rest: '' };
    }
    currentScriptData.video_title.highlight = hookTitleHighlightInput.value;
    currentScriptData.video_title.rest = hookTitleRestInput.value;
    currentScriptData.subject = subjectInput.value;
};
window.handleMetadataEdit = () => {
    if (!currentScriptData) return;
    currentScriptData.youtube_title = youtubeTitleInput.value.trim();
    currentScriptData.youtube_description = youtubeDescriptionInput.value.trim();
    currentScriptData.youtube_tags = youtubeTagsInput.value
        .split(',')
        .map((tag) => tag.trim())
        .filter(Boolean);
};
window.copyFullScript = () => {
    if (!currentScriptData) return;
    const text = currentScriptData.scenes.map(s => `[내레이션] ${s.script}`).join('\n\n');
    navigator.clipboard.writeText(text).then(() => alert('복사되었습니다.'));
};

async function handleFullAudioUpload(event) {
    const file = event.target.files[0];
    if (!file || !currentScriptData) return;

    const formData = new FormData();
    formData.append('file', file);

    try {
        const res = await fetchWithAuth(buildAppUrl('api/upload-asset'), { method: 'POST', body: formData });
        const data = await res.json();
        if (data.error) throw new Error(data.error);

        currentScriptData.full_audio_path = data.path;
        fullAudioStatus.querySelector('.status-filename').textContent = file.name;
        fullAudioStatus.classList.remove('hidden');
    } catch (e) {
        alert('음성 파일 업로드 실패: ' + e.message);
    }
}

function removeFullAudio() {
    if (!currentScriptData) return;
    delete currentScriptData.full_audio_path;
    fullAudioStatus.classList.add('hidden');
}

async function handleFileUpload(event, idx) {
    const file = event.target.files[0];
    if (!file) return;
    const formData = new FormData();
    formData.append('file', file);
    try {
        const res = await fetchWithAuth(buildAppUrl('api/upload-asset'), { method: 'POST', body: formData });
        const data = await res.json();
        updateSceneOverlay(idx, data.path);
    } catch (e) { alert('업로드 실패'); }
}

function updateSceneOverlay(idx, path) {
    if(!currentScriptData.scenes[idx].overlays) currentScriptData.scenes[idx].overlays = [];
    currentScriptData.scenes[idx].overlays = [{ type: 'image', content: path, position: 'blackboard', startTime: 0, duration: 5 }];
    showScriptPreview(currentScriptData);
}

window.removeAsset = (idx) => {
    currentScriptData.scenes[idx].overlays = [];
    showScriptPreview(currentScriptData);
};

async function uploadToYoutube(jobId) {
    const statusDiv = document.getElementById('upload-status');
    statusDiv.classList.remove('hidden');
    statusDiv.textContent = '⏳ 업로드 중...';
    try {
        const res = await fetchWithAuth(buildAppUrl('api/upload-youtube'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                job_id: jobId,
                title: currentScriptData.youtube_title || "Shorts",
                description: currentScriptData.youtube_description || "",
                tags: currentScriptData.youtube_tags || []
            })
        });
        const data = await parseJson(res);
        statusDiv.textContent = data.status === 'success' ? '✅ 업로드 완료!' : '❌ 실패: ' + data.error;
    } catch (e) { statusDiv.textContent = '❌ 오류 발생'; }
}

async function loadHistory() {
    try {
        const res = await fetchWithAuth(buildAppUrl('api/history'));
        const items = await parseJson(res);
        historyList.innerHTML = items.length ? items.map(item => `
            <div class="history-item">
                <div class="history-thumb"><video src="${buildAppUrl(String(item.video_url || '').replace(/^\/+/, ''))}" preload="metadata"></video></div>
                <div class="history-info">
                    <div class="history-title">${item.youtube_title || item.topic || '제목 없음'}</div>
                    <div class="history-actions">
                        <button class="btn-yt-action btn-sm" onclick="openHistoryItem('${item.id}')">보기</button>
                        <button class="btn-yt-action btn-sm" onclick="copyHistoryMeta('${item.id}', 'title')">제목 복사</button>
                        <button class="btn-yt-action btn-sm" onclick="copyHistoryMeta('${item.id}', 'description')">설명 복사</button>
                        <button class="btn-yt-action btn-sm" onclick="copyHistoryMeta('${item.id}', 'tags')">태그 복사</button>
                        <button class="btn-yt-action btn-sm border" onclick="deleteHistoryItem('${item.id}')">삭제</button>
                        <a href="${buildAppUrl(`api/download/${encodeURIComponent(`shorts_${item.job_id}.mp4`)}`)}" class="btn-yt-action btn-sm">다운로드</a>
                    </div>
                </div>
            </div>
        `).join('') : '<div style="grid-column:1/-1; text-align:center; padding:100px; color:#aaa;">보관함이 비어있습니다.</div>';
    } catch (e) { historyList.innerHTML = '보관함을 불러오지 못했습니다.'; }
}

async function openHistoryItem(id) {
    try {
        const res = await fetchWithAuth(buildAppUrl(`api/history/${encodeURIComponent(id)}`));
        const item = await parseJson(res);
        currentScriptData = item.script_data;
        showStep('workspace-step');
        showScriptPreview(currentScriptData);
        showResult({ job_id: item.job_id, video_url: item.video_url });
    } catch (e) { alert('항목을 열 수 없습니다.'); }
}

async function deleteHistoryItem(id) {
    if (!confirm('정말 삭제하시겠습니까?')) return;
    try {
        await fetchWithAuth(buildAppUrl(`api/history/${encodeURIComponent(id)}/delete`), { method: 'POST' });
        loadHistory();
    } catch (e) { alert('삭제 실패'); }
}

async function copyHistoryMeta(id, field) {
    try {
        const res = await fetchWithAuth(buildAppUrl(`api/history/${encodeURIComponent(id)}`));
        const item = await parseJson(res);
        const text = field === 'title'
            ? item.youtube_title
            : field === 'tags'
                ? (item.youtube_tags || []).join(', ')
                : item.youtube_description;
        if (!text) {
            alert('복사할 내용이 없습니다.');
            return;
        }
        await navigator.clipboard.writeText(text);
        alert('복사되었습니다.');
    } catch (e) {
        alert('복사 실패');
    }
}

/**
 * AI Image Generation for overlays
 */
async function handleAiImageGenerate(idx) {
    const imagePrompt = window.prompt(`오버레이 이미지 설명을 입력하세요.`, currentScriptData.scenes[idx].background_description);
    if (!imagePrompt) return;
    
    const container = document.getElementById(`ai-preview-container-${idx}`);
    container.classList.remove('hidden');
    container.innerHTML = '<div style="padding:20px; text-align:center; color:var(--accent-yellow);">🎨 AI 이미지 생성 중...</div>';

    try {
        const res = await fetchWithAuth(buildAppUrl('api/generate-image'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prompt: imagePrompt, scene_script: currentScriptData.scenes[idx].script })
        });
        const data = await parseJson(res);
        if (data.error) throw new Error(data.error);
        updateSceneOverlay(idx, data.path);
        container.classList.add('hidden');
    } catch (e) { alert('이미지 생성 실패: ' + e.message); container.classList.add('hidden'); }
}

/**
 * Event Listeners Initial Bindings
 */
loginBtn.addEventListener('click', handleLogin);
loginPassword.addEventListener('keydown', (e) => { if(e.key === 'Enter') handleLogin(); });
navCreateBtn.addEventListener('click', () => showStep('input-step'));
navHistoryBtn.addEventListener('click', () => { showStep('history-section'); loadHistory(); });
historyRefreshBtn.addEventListener('click', loadHistory);
logoHome.addEventListener('click', resetUI);
generateBtn.addEventListener('click', startScriptGeneration);
backToInputBtn.addEventListener('click', () => showStep('input-step'));
regenerateScriptBtn.addEventListener('click', regenerateScript);
confirmGenerateBtn.addEventListener('click', startVideoGeneration);
newVideoBtn.addEventListener('click', resetUI);
retryBtn.addEventListener('click', startVideoGeneration);
copyMetaBtn.addEventListener('click', async () => {
    if (!currentScriptData) return;
    const text = [
        currentScriptData.youtube_title || '',
        '',
        currentScriptData.youtube_description || '',
        '',
        (currentScriptData.youtube_tags || []).map((tag) => `#${String(tag).replace(/^#+/, '')}`).join(' '),
    ].join('\n').trim();
    await navigator.clipboard.writeText(text);
    alert('메타데이터를 복사했습니다.');
});
menuBtn.addEventListener('click', () => alert('메뉴 기능은 준비 중입니다.'));

sceneCountOptions.forEach(opt => {
    opt.onclick = () => {
        sceneCountOptions.forEach(o => o.classList.remove('active'));
        opt.classList.add('active');
        selectedSceneCount = parseInt(opt.dataset.count);
        console.log('Selected count:', selectedSceneCount);
    };
});

window.onload = checkAuth;
window.openHistoryItem = openHistoryItem;
window.deleteHistoryItem = deleteHistoryItem;
window.copyHistoryMeta = copyHistoryMeta;
window.handleAiImageGenerate = handleAiImageGenerate;
window.handleFileUpload = handleFileUpload;
window.handleFullAudioUpload = handleFullAudioUpload;
window.removeFullAudio = removeFullAudio;
