// ==================== ShortsSync Web Frontend ====================
// Real-time audio fingerprinting interface with WebSocket support

// Global state
let socket = null;
let matches = [];
let lastTask = null;  // Track last task for cleanup when it completes
let config = {
    video_dir: '',
    audio_dir: '',
    fixed_tags: '#shorts',
    pool_tags: '#fyp #viral #trending #foryou #reels',
    move_files: false,
    preserve_exact_names: false
};

// ==================== Initialization ====================
document.addEventListener('DOMContentLoaded', () => {
    initializeSocket();
    loadConfig();
    attachEventListeners();
    initializeTabs();
    checkHealth();
});

// ==================== WebSocket Connection ====================
function initializeSocket() {
    // Connect to the same host and port that served this page
    const protocol = window.location.protocol === 'https:' ? 'https:' : 'http:';
    const host = window.location.hostname;
    const port = window.location.port || (protocol === 'https:' ? '443' : '80');
    const serverUrl = `${protocol}//${host}:${port}`;

    socket = io(serverUrl, {
        transports: ['websocket', 'polling']
    });

    socket.on('connect', () => {
        updateConnectionStatus(true);
        addLog('Connected to ShortsSync server', 'success');
    });

    socket.on('disconnect', () => {
        updateConnectionStatus(false);
        addLog('Disconnected from server', 'warning');
    });

    socket.on('status_update', (data) => {
        handleStatusUpdate(data);
    });

    socket.on('connect_error', (error) => {
        updateConnectionStatus(false);
        addLog('Connection error: ' + error.message, 'error');
    });
}

function updateConnectionStatus(connected) {
    const statusEl = document.getElementById('connectionStatus');
    const statusText = statusEl.querySelector('.status-text');

    if (connected) {
        statusEl.classList.add('connected');
        statusEl.classList.remove('disconnected');
        statusText.textContent = 'Connected';
    } else {
        statusEl.classList.remove('connected');
        statusEl.classList.add('disconnected');
        statusText.textContent = 'Disconnected';
    }
}

// ==================== Tabs ====================
function initializeTabs() {
    const tabButtons = document.querySelectorAll('.tab-btn');

    tabButtons.forEach(button => {
        button.addEventListener('click', () => {
            const targetTab = button.getAttribute('data-tab');

            // Remove active class from all buttons and tabs
            tabButtons.forEach(btn => btn.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));

            // Add active class to clicked button and target tab
            button.classList.add('active');
            document.getElementById(targetTab).classList.add('active');
        });
    });
}

// ==================== Event Listeners ====================
function attachEventListeners() {
    // Configuration inputs
    document.getElementById('videoDir').addEventListener('change', saveConfig);
    document.getElementById('audioDir').addEventListener('change', saveConfig);
    document.getElementById('fixedTags').addEventListener('change', saveConfig);
    document.getElementById('poolTags').addEventListener('change', saveConfig);
    document.getElementById('moveFiles').addEventListener('change', saveConfig);
    document.getElementById('preserveExact').addEventListener('change', saveConfig);

    // Action buttons
    document.getElementById('btnDownload').addEventListener('click', startDownload);
    document.getElementById('btnDownloadMP3').addEventListener('click', startMP3Download);
    document.getElementById('btnIndex').addEventListener('click', startIndexing);
    document.getElementById('btnMatch').addEventListener('click', startMatching);
    document.getElementById('btnRename').addEventListener('click', startRenaming);
    document.getElementById('btnClear').addEventListener('click', clearResults);
    document.getElementById('btnClearLog').addEventListener('click', clearLog);
    document.getElementById('btnClearLog2')?.addEventListener('click', clearLog);
    document.getElementById('btnClearLog3')?.addEventListener('click', clearLog);
}

// ==================== Configuration Management ====================
function loadConfig() {
    // Load from localStorage if available
    const saved = localStorage.getItem('shortsync_config');
    if (saved) {
        config = JSON.parse(saved);
        document.getElementById('videoDir').value = config.video_dir || '';
        document.getElementById('audioDir').value = config.audio_dir || '';
        document.getElementById('fixedTags').value = config.fixed_tags || '#shorts';
        document.getElementById('poolTags').value = config.pool_tags || '#fyp #viral #trending';
        document.getElementById('moveFiles').checked = config.move_files || false;
        document.getElementById('preserveExact').checked = config.preserve_exact_names || false;
    }

    // Fetch from server
    fetch('/api/config')
        .then(res => res.json())
        .then(data => {
            if (data.config) {
                // Populate with server defaults if not in localStorage
                if (!saved) {
                    document.getElementById('videoDir').value = data.config.video_dir || '';
                    document.getElementById('audioDir').value = data.config.audio_dir || '';
                    document.getElementById('fixedTags').value = data.config.fixed_tags || '#shorts';
                    document.getElementById('poolTags').value = data.config.pool_tags || '';
                }
                // Always update MP3 audio dir field
                document.getElementById('mp3AudioDir').value = data.config.audio_dir || 'Not configured';
            }
        })
        .catch(err => {
            addLog('Error loading config: ' + err.message, 'error');
        });
}

function saveConfig() {
    config.video_dir = document.getElementById('videoDir').value.trim();
    config.audio_dir = document.getElementById('audioDir').value.trim();
    config.fixed_tags = document.getElementById('fixedTags').value.trim();
    config.pool_tags = document.getElementById('poolTags').value.trim();
    config.move_files = document.getElementById('moveFiles').checked;
    config.preserve_exact_names = document.getElementById('preserveExact').checked;

    // Save to localStorage
    localStorage.setItem('shortsync_config', JSON.stringify(config));
    addLog('Configuration saved', 'info');
}

// ==================== Health Check ====================
function checkHealth() {
    fetch('/api/health')
        .then(res => res.json())
        .then(data => {
            if (data.status === 'healthy') {
                addLog('Server health check: OK', 'success');
                if (!data.dependencies.fpcalc) {
                    addLog('Warning: fpcalc not found. Install chromaprint.', 'warning');
                }
            }
        })
        .catch(err => {
            addLog('Health check failed: ' + err.message, 'error');
        });
}

// ==================== Download ====================
function startDownload() {
    const url = document.getElementById('downloadUrl').value.trim();
    const outputDir = document.getElementById('downloadOutputDir').value.trim();
    const format = document.getElementById('downloadFormat').value;

    if (!url) {
        alert('Please enter a video URL');
        return;
    }

    const btnDownload = document.getElementById('btnDownload');
    btnDownload.disabled = true;
    btnDownload.innerHTML = '<svg class="spinner" width="20" height="20" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" fill="none" stroke-dasharray="60" stroke-dashoffset="20"/></svg> Downloading...';

    addLog('Starting download...', 'info');

    fetch('/api/download', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            url: url,
            output_dir: outputDir || './downloads',
            format: format
        })
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            addLog('Download started successfully', 'success');
        } else {
            addLog('Download failed: ' + (data.error || 'Unknown error'), 'error');
            resetDownloadButton();
        }
    })
    .catch(err => {
        addLog('Error starting download: ' + err.message, 'error');
        resetDownloadButton();
    });
}

function resetDownloadButton() {
    const btnDownload = document.getElementById('btnDownload');
    btnDownload.disabled = false;
    btnDownload.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3" stroke-width="2"/></svg> Start Download';
}

// ==================== MP3 Download ====================
function startMP3Download() {
    const urlsText = document.getElementById('mp3UrlsInput').value.trim();
    
    if (!urlsText) {
        alert('Please enter at least one URL');
        return;
    }

    // Parse URLs and optional filenames
    const lines = urlsText.split('\n').filter(line => line.trim());
    const urlsData = [];
    
    for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) continue;
        
        const parts = trimmed.split(/\s+/);
        const url = parts[0];
        const filename = parts.length > 1 ? parts.slice(1).join(' ') : '';
        
        urlsData.push({ url, filename });
    }

    if (urlsData.length === 0) {
        alert('Please enter at least one valid URL');
        return;
    }

    const btnDownloadMP3 = document.getElementById('btnDownloadMP3');
    btnDownloadMP3.disabled = true;
    btnDownloadMP3.innerHTML = '<svg class="spinner" width="20" height="20" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" fill="none" stroke-dasharray="60" stroke-dashoffset="20"/></svg> Downloading MP3s...';

    // Show progress section
    const progressSection = document.getElementById('mp3ProgressSection');
    const progressFill = document.getElementById('mp3ProgressFill');
    const progressText = document.getElementById('mp3ProgressText');
    
    progressSection.style.display = 'block';
    progressFill.style.width = '0%';
    progressText.textContent = `0 / ${urlsData.length}`;

    addLog(`Starting MP3 download of ${urlsData.length} item(s)...`, 'info');

    fetch('/api/download_mp3', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ urls: urlsData })
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            addLog(`MP3 download started: ${data.count} item(s)`, 'success');
        } else {
            addLog('MP3 download failed: ' + (data.error || 'Unknown error'), 'error');
            resetMP3DownloadButton();
        }
    })
    .catch(err => {
        addLog('Error starting MP3 download: ' + err.message, 'error');
        resetMP3DownloadButton();
    });
}

function resetMP3DownloadButton() {
    const btnDownloadMP3 = document.getElementById('btnDownloadMP3');
    btnDownloadMP3.disabled = false;
    btnDownloadMP3.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3" stroke-width="2"/></svg> Download MP3s';
    
    // Hide progress section
    const progressSection = document.getElementById('mp3ProgressSection');
    if (progressSection) {
        progressSection.style.display = 'none';
    }
}

// ==================== Indexing ====================
function startIndexing() {
    saveConfig();

    if (!config.audio_dir) {
        alert('Please enter the reference audio directory');
        return;
    }

    const btnIndex = document.getElementById('btnIndex');
    btnIndex.disabled = true;
    btnIndex.innerHTML = '<svg class="spinner" width="20" height="20" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" fill="none" stroke-dasharray="60" stroke-dashoffset="20"/></svg> Indexing...';

    // Show progress section
    const progressSection = document.getElementById('indexProgressSection');
    const progressFill = document.getElementById('indexProgressFill');
    const progressText = document.getElementById('indexProgressText');
    
    if (progressSection) {
        progressSection.style.display = 'block';
        progressFill.style.width = '0%';
        progressText.textContent = '0 / 0';
    }

    addLog('Starting reference audio indexing...', 'info');

    fetch('/api/reference/index', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ audio_dir: config.audio_dir })
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            addLog('Indexing started successfully', 'success');
        } else {
            addLog('Indexing failed: ' + (data.error || 'Unknown error'), 'error');
            resetIndexButton();
        }
    })
    .catch(err => {
        addLog('Error starting indexing: ' + err.message, 'error');
        resetIndexButton();
    });
}

function resetIndexButton() {
    const btnIndex = document.getElementById('btnIndex');
    btnIndex.disabled = false;
    btnIndex.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M9 18l6-6-6-6" stroke-width="2" stroke-linecap="round"/></svg> Start Indexing';
    
    // Hide progress section
    const progressSection = document.getElementById('indexProgressSection');
    if (progressSection) {
        progressSection.style.display = 'none';
    }
}

// ==================== Matching ====================
function startMatching() {
    saveConfig();

    if (!config.video_dir) {
        alert('Please enter the video source directory');
        return;
    }

    const btnMatch = document.getElementById('btnMatch');
    btnMatch.disabled = true;
    btnMatch.innerHTML = '<svg class="spinner" width="20" height="20" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" fill="none" stroke-dasharray="60" stroke-dashoffset="20"/></svg> Matching...';

    addLog('Starting video matching...', 'info');

    fetch('/api/videos/match', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            video_dir: config.video_dir,
            fixed_tags: config.fixed_tags,
            pool_tags: config.pool_tags,
            preserve_exact_names: config.preserve_exact_names
        })
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            addLog('Matching started successfully', 'success');
        } else {
            addLog('Matching failed: ' + (data.error || 'Unknown error'), 'error');
            resetMatchButton();
        }
    })
    .catch(err => {
        addLog('Error starting matching: ' + err.message, 'error');
        resetMatchButton();
    });
}

function resetMatchButton() {
    const btnMatch = document.getElementById('btnMatch');
    btnMatch.disabled = false;
    btnMatch.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"><circle cx="11" cy="11" r="8" stroke-width="2"/><path d="M21 21l-4.35-4.35" stroke-width="2" stroke-linecap="round"/></svg> Start Matching';
}

// ==================== Renaming ====================
function startRenaming() {
    if (matches.length === 0) {
        alert('No matches to rename');
        return;
    }

    if (!confirm(`Rename ${matches.length} files?`)) {
        return;
    }

    const btnRename = document.getElementById('btnRename');
    btnRename.disabled = true;
    btnRename.innerHTML = '<svg class="spinner" width="20" height="20" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" fill="none" stroke-dasharray="60" stroke-dashoffset="20"/></svg> Renaming...';

    addLog('Starting rename operation...', 'info');

    fetch('/api/videos/rename', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            video_dir: config.video_dir,
            move_files: config.move_files
        })
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            addLog('Rename operation started', 'success');
        } else {
            addLog('Rename failed: ' + (data.error || 'Unknown error'), 'error');
            resetRenameButton();
        }
    })
    .catch(err => {
        addLog('Error starting rename: ' + err.message, 'error');
        resetRenameButton();
    });
}

function resetRenameButton() {
    const btnRename = document.getElementById('btnRename');
    btnRename.disabled = false;
    btnRename.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"><polyline points="20 6 9 17 4 12" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg> Commit Rename';
}

// ==================== Status Updates ====================
function handleStatusUpdate(data) {
    const { is_processing, current_task, progress, total, message } = data;

    // Track current task for cleanup
    if (current_task) {
        lastTask = current_task;
    }

    // Update progress card
    const progressCard = document.getElementById('progressCard');
    if (is_processing) {
        progressCard.style.display = 'block';
        document.getElementById('progressMessage').textContent = message;

        if (total > 0) {
            const percentage = Math.round((progress / total) * 100);
            document.getElementById('progressFill').style.width = percentage + '%';
            document.getElementById('progressText').textContent = `${progress} / ${total}`;
        }
    } else {
        progressCard.style.display = 'none';
    }

    // Log message
    if (message) {
        let logType = 'info';
        if (message.includes('✅') || message.includes('complete') || message.includes('success')) {
            logType = 'success';
        } else if (message.includes('❌') || message.includes('Error')) {
            logType = 'error';
        } else if (message.includes('⚠️') || message.includes('Warning')) {
            logType = 'warning';
        }
        addLog(message, logType);
    }

    // Task-specific cleanup when processing completes
    if (!is_processing && lastTask) {
        if (lastTask === 'downloading') {
            resetDownloadButton();
        } else if (lastTask === 'downloading_mp3') {
            resetMP3DownloadButton();
            // Also update MP3 progress bar if exists
            const mp3ProgressFill = document.getElementById('mp3ProgressFill');
            const mp3ProgressText = document.getElementById('mp3ProgressText');
            if (mp3ProgressFill && total > 0) {
                mp3ProgressFill.style.width = '100%';
                mp3ProgressText.textContent = `${total} / ${total}`;
            }
        } else if (lastTask === 'indexing') {
            // Update indexing progress bar to 100%
            const indexProgressFill = document.getElementById('indexProgressFill');
            const indexProgressText = document.getElementById('indexProgressText');
            if (indexProgressFill && total > 0) {
                indexProgressFill.style.width = '100%';
                indexProgressText.textContent = `${total} / ${total}`;
            }
            resetIndexButton();
            fetchReferenceCount();
            // Enable match button after successful indexing
            document.getElementById('btnMatch').disabled = false;
        } else if (lastTask === 'matching') {
            resetMatchButton();
            fetchMatches();
        } else if (lastTask === 'renaming') {
            resetRenameButton();
            clearResults();
        }
        lastTask = null;  // Clear after handling
    }
    
    // Update MP3 progress bar during download
    if (current_task === 'downloading_mp3' && total > 0) {
        const mp3ProgressFill = document.getElementById('mp3ProgressFill');
        const mp3ProgressText = document.getElementById('mp3ProgressText');
        if (mp3ProgressFill && mp3ProgressText) {
            const percentage = Math.round((progress / total) * 100);
            mp3ProgressFill.style.width = percentage + '%';
            mp3ProgressText.textContent = `${progress} / ${total}`;
        }
    }
    
    // Update indexing progress bar during indexing
    if (current_task === 'indexing' && total > 0) {
        const indexProgressFill = document.getElementById('indexProgressFill');
        const indexProgressText = document.getElementById('indexProgressText');
        if (indexProgressFill && indexProgressText) {
            const percentage = Math.round((progress / total) * 100);
            indexProgressFill.style.width = percentage + '%';
            indexProgressText.textContent = `${progress} / ${total}`;
        }
    }
}

// ==================== Fetch Data ====================
function fetchReferenceCount() {
    fetch('/api/reference/list')
        .then(res => res.json())
        .then(data => {
            document.getElementById('indexedCount').textContent = data.count || 0;
            addLog(`Indexed ${data.count} reference files`, 'success');
        })
        .catch(err => {
            addLog('Error fetching reference count: ' + err.message, 'error');
        });
}

function fetchMatches() {
    fetch('/api/matches')
        .then(res => res.json())
        .then(data => {
            matches = data.matches || [];
            document.getElementById('matchCount').textContent = matches.length;
            displayResults(matches);
            addLog(`Found ${matches.length} matches`, 'success');
        })
        .catch(err => {
            addLog('Error fetching matches: ' + err.message, 'error');
        });
}

// ==================== Display Results ====================
function displayResults(matchList) {
    const resultsCard = document.getElementById('resultsCard');
    const resultsContainer = document.getElementById('resultsContainer');

    if (matchList.length === 0) {
        resultsCard.style.display = 'none';
        return;
    }

    resultsCard.style.display = 'block';
    resultsContainer.innerHTML = '';

    matchList.forEach((match, index) => {
        const confidence = (match.confidence * 100).toFixed(1);
        let confidenceClass = 'high';
        if (match.confidence < 0.7) confidenceClass = 'low';
        else if (match.confidence < 0.9) confidenceClass = 'medium';

        const resultItem = document.createElement('div');
        resultItem.className = 'result-item';
        resultItem.innerHTML = `
            <div class="result-header">
                <strong>Match #${index + 1}</strong>
                <span class="result-confidence ${confidenceClass}">
                    ${confidence}% confidence
                </span>
            </div>
            <div class="result-files">
                <div class="result-file original">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                        <path d="M13 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V9z" stroke-width="2"/>
                        <polyline points="13 2 13 9 20 9" stroke-width="2"/>
                    </svg>
                    <span>${escapeHtml(match.original)}</span>
                </div>
                <div class="result-file new">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                        <polyline points="20 6 9 17 4 12" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                    <span>${escapeHtml(match.new_name)}</span>
                </div>
            </div>
            <div style="margin-top: 8px; font-size: 12px; color: var(--text-secondary);">
                Matched: ${escapeHtml(match.matched_ref)} (BER: ${match.ber.toFixed(3)})
            </div>
        `;
        resultsContainer.appendChild(resultItem);
    });
}

// ==================== Clear Functions ====================
function clearResults() {
    matches = [];
    document.getElementById('matchCount').textContent = '0';
    document.getElementById('resultsCard').style.display = 'none';
    addLog('Results cleared', 'info');
}

function clearLog() {
    const logContainer1 = document.getElementById('logContainer');
    const logContainer2 = document.getElementById('logContainer2');
    const logContainer3 = document.getElementById('logContainer3');

    if (logContainer1) logContainer1.innerHTML = '';
    if (logContainer2) logContainer2.innerHTML = '';
    if (logContainer3) logContainer3.innerHTML = '';

    addLog('Log cleared', 'info');
}

// ==================== Logging ====================
function addLog(message, type = 'info') {
    const timestamp = new Date().toLocaleTimeString('en-US', { hour12: false });

    const logEntry = document.createElement('div');
    logEntry.className = `log-entry log-${type}`;
    logEntry.innerHTML = `
        <span class="log-time">[${timestamp}]</span>
        <span class="log-message">${escapeHtml(message)}</span>
    `;

    // Add to all log containers (match tab, download tab, and mp3 tab)
    const logContainer1 = document.getElementById('logContainer');
    const logContainer2 = document.getElementById('logContainer2');
    const logContainer3 = document.getElementById('logContainer3');

    if (logContainer1) {
        logContainer1.appendChild(logEntry.cloneNode(true));
        logContainer1.scrollTop = logContainer1.scrollHeight;
    }

    if (logContainer2) {
        logContainer2.appendChild(logEntry.cloneNode(true));
        logContainer2.scrollTop = logContainer2.scrollHeight;
    }

    if (logContainer3) {
        logContainer3.appendChild(logEntry.cloneNode(true));
        logContainer3.scrollTop = logContainer3.scrollHeight;
    }
}

// ==================== Utility Functions ====================
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ==================== About Dialog ====================
document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('aboutLink')?.addEventListener('click', (e) => {
        e.preventDefault();
        alert(`ShortsSync Web Interface v1.0

AI-Powered Audio Fingerprinting for Short-Form Video Management

Features:
• Chromaprint audio fingerprinting
• Real-time WebSocket updates
• Batch video processing
• Smart tag generation
• Duplicate detection

Built with Flask, Socket.IO, and modern web technologies.

© 2025 ShortsSync`);
    });
});
