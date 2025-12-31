/**
 * SendBaba Real-Time Features v3
 * Full featured: Audio, Emoji, Contacts, Calendar, Autocomplete
 */

(function() {
    'use strict';
    
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
    
    // Sound
    let notifSound = null;
    let soundEnabled = false;
    
    // WebSocket
    let socket = null;
    
    // Emoji data
    const emojiData = {
        smileys: ['😀','😃','😄','😁','😅','😂','🤣','😊','😇','🙂','😉','😌','😍','🥰','😘','😋','😜','🤪','😎','🤩','🥳','😏','😢','😭','😤','😠','😈','💀','👻','🤖'],
        gestures: ['👋','🤚','✋','👌','✌️','🤞','🤟','🤘','🤙','👍','👎','✊','👊','👏','🙌','🤝','🙏','💪'],
        hearts: ['❤️','🧡','💛','💚','💙','💜','🖤','🤍','💔','💕','💖','💘','💝'],
        animals: ['🐱','🐶','🐭','🐹','🐰','🦊','🐻','🐼','🐨','🐯','🦁','🐮','🐷','🐸','🐵','🦄'],
        food: ['🍕','🍔','🍟','🌭','🍿','🍳','🍞','🧀','🌮','🍜','🍣','🍰','🍪','☕'],
        objects: ['💼','📁','📅','📎','🔒','🔑','💡','📱','💻','🎮','🎧']
    };
    
    // Audio state
    let mediaRecorder = null;
    let audioChunks = [];
    let isRecording = false;
    let isPaused = false;
    let recordStart = null;
    let pausedTime = 0;
    let recordInterval = null;
    let audioBlob = null;
    let audioReady = false;
    
    // Contacts cache
    let contactsCache = [];
    
    function init() {
        console.log('🚀 SendBaba Real-Time v3 initializing...');
        
        initSound();
        initSocket();
        injectUI();
        initAutocomplete();
        loadContactsCache();
        
        console.log('✅ SendBaba Real-Time ready');
    }
    
    function initSound() {
        try {
            notifSound = new Audio('/static/sounds/new-email.wav');
            notifSound.volume = 0.5;
        } catch(e) {}
        
        const enableSound = () => {
            if (!soundEnabled && notifSound) {
                notifSound.play().then(() => {
                    notifSound.pause();
                    notifSound.currentTime = 0;
                    soundEnabled = true;
                }).catch(() => {});
            }
        };
        document.addEventListener('click', enableSound, { once: true });
    }
    
    function playSound() {
        if (soundEnabled && notifSound) {
            notifSound.currentTime = 0;
            notifSound.play().catch(() => {});
        }
    }
    
    function initSocket() {
        if (typeof io === 'undefined') return;
        
        try {
            socket = io({ transports: ['websocket', 'polling'] });
            socket.on('connect', () => console.log('🟢 Connected'));
            socket.on('new_email', (data) => {
                playSound();
                if (typeof showNewEmailBanner === 'function') showNewEmailBanner(1, data);
                if (typeof loadCounts === 'function') loadCounts();
            });
            socket.on('typing', (data) => showTyping(data.from_name || data.from));
            socket.on('stop_typing', () => hideTyping());
        } catch(e) {}
    }
    
    // ========== LOAD CONTACTS ==========
    async function loadContactsCache() {
        try {
            const r = await fetch('/api/contacts', { credentials: 'same-origin' });
            const data = await r.json();
            if (data.success) {
                contactsCache = data.contacts || [];
            }
        } catch(e) {}
    }
    
    // ========== AUTOCOMPLETE ==========
    function initAutocomplete() {
        const toInput = document.getElementById('compose-to');
        if (!toInput) return;
        
        // Create autocomplete dropdown
        let dropdown = document.getElementById('email-autocomplete');
        if (!dropdown) {
            dropdown = document.createElement('div');
            dropdown.id = 'email-autocomplete';
            dropdown.className = 'email-autocomplete';
            toInput.parentNode.style.position = 'relative';
            toInput.parentNode.appendChild(dropdown);
        }
        
        toInput.addEventListener('input', debounce(async (e) => {
            const query = e.target.value.trim().toLowerCase();
            if (query.length < 1) {
                dropdown.classList.remove('open');
                return;
            }
            
            // Filter from cache first
            let matches = contactsCache.filter(c => 
                c.email.toLowerCase().includes(query) || 
                c.name.toLowerCase().includes(query)
            ).slice(0, 8);
            
            // If not enough matches, search API
            if (matches.length < 3) {
                try {
                    const r = await fetch(`/api/contacts/search?q=${encodeURIComponent(query)}`, { credentials: 'same-origin' });
                    const data = await r.json();
                    if (data.success && data.contacts) {
                        // Merge with existing matches
                        data.contacts.forEach(c => {
                            if (!matches.find(m => m.email === c.email)) {
                                matches.push(c);
                            }
                        });
                    }
                } catch(e) {}
            }
            
            if (matches.length > 0) {
                dropdown.innerHTML = matches.map(c => `
                    <div class="autocomplete-item" onclick="window.sbSelectEmail('${c.email}')">
                        <div class="autocomplete-avatar" style="background:${getColorForEmail(c.email)}">${c.name[0].toUpperCase()}</div>
                        <div class="autocomplete-info">
                            <div class="autocomplete-name">${escapeHtml(c.name)}</div>
                            <div class="autocomplete-email">${escapeHtml(c.email)}</div>
                        </div>
                    </div>
                `).join('');
                dropdown.classList.add('open');
            } else {
                dropdown.classList.remove('open');
            }
        }, 200));
        
        // Close on click outside
        document.addEventListener('click', (e) => {
            if (!e.target.closest('.email-autocomplete') && !e.target.closest('#compose-to')) {
                dropdown.classList.remove('open');
            }
        });
        
        // Keyboard navigation
        toInput.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                dropdown.classList.remove('open');
            }
        });
    }
    
    window.sbSelectEmail = function(email) {
        const input = document.getElementById('compose-to');
        if (input) {
            input.value = email;
            document.getElementById('email-autocomplete')?.classList.remove('open');
            document.getElementById('compose-subject')?.focus();
        }
    };
    
    function getColorForEmail(email) {
        const colors = ['#f86d31', '#3b82f6', '#10b981', '#8b5cf6', '#ec4899', '#f59e0b'];
        let hash = 0;
        for (let i = 0; i < email.length; i++) hash += email.charCodeAt(i);
        return colors[hash % colors.length];
    }
    
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    function debounce(func, wait) {
        let timeout;
        return function(...args) {
            clearTimeout(timeout);
            timeout = setTimeout(() => func.apply(this, args), wait);
        };
    }
    
    // ========== UI INJECTION ==========
    function injectUI() {
        // Typing indicator
        const emailList = document.getElementById('email-list');
        if (emailList && !document.getElementById('typing-indicator')) {
            const typing = document.createElement('div');
            typing.id = 'typing-indicator';
            typing.className = 'typing-indicator';
            typing.innerHTML = '<div class="typing-dots"><span></span><span></span><span></span></div><span id="typing-text">Someone is typing...</span>';
            emailList.parentNode.insertBefore(typing, emailList);
        }
        
        // Emoji & mic buttons
        const composeToolbar = document.querySelector('.compose-toolbar');
        if (composeToolbar && !document.getElementById('emoji-btn')) {
            const templateDropdown = composeToolbar.querySelector('.template-dropdown');
            
            const emojiBtn = document.createElement('button');
            emojiBtn.id = 'emoji-btn';
            emojiBtn.className = 'compose-tool';
            emojiBtn.title = 'Emoji';
            emojiBtn.innerHTML = '<i class="fas fa-smile"></i>';
            emojiBtn.onclick = toggleEmojiPicker;
            
            const micBtn = document.createElement('button');
            micBtn.id = 'mic-btn';
            micBtn.className = 'compose-tool';
            micBtn.title = 'Voice Message';
            micBtn.innerHTML = '<i class="fas fa-microphone"></i>';
            micBtn.onclick = startRecording;
            
            const emojiContainer = document.createElement('div');
            emojiContainer.className = 'emoji-picker-container';
            emojiContainer.innerHTML = `
                <div class="emoji-picker" id="emoji-picker">
                    <div class="emoji-tabs" id="emoji-tabs"></div>
                    <div class="emoji-grid" id="emoji-grid"></div>
                </div>
            `;
            
            if (templateDropdown) {
                composeToolbar.insertBefore(emojiBtn, templateDropdown);
                composeToolbar.insertBefore(micBtn, templateDropdown);
                composeToolbar.insertBefore(emojiContainer, templateDropdown);
            }
            
            const tabs = document.getElementById('emoji-tabs');
            if (tabs) {
                const tabEmojis = { smileys: '😀', gestures: '👋', hearts: '❤️', animals: '🐱', food: '🍕', objects: '💼' };
                Object.keys(tabEmojis).forEach((cat, i) => {
                    const btn = document.createElement('button');
                    btn.className = 'emoji-tab' + (i === 0 ? ' active' : '');
                    btn.textContent = tabEmojis[cat];
                    btn.onclick = () => showEmojis(cat);
                    tabs.appendChild(btn);
                });
            }
        }
        
        // Audio recorder
        const composeEditor = document.querySelector('.compose-editor');
        if (composeEditor && !document.getElementById('audio-recorder')) {
            const recorder = document.createElement('div');
            recorder.id = 'audio-recorder';
            recorder.className = 'audio-recorder';
            recorder.innerHTML = `
                <div class="record-dot"></div>
                <span class="record-time" id="record-time">00:00</span>
                <div class="record-waves"><span></span><span></span><span></span><span></span><span></span></div>
                <div class="record-controls">
                    <button class="record-btn record-pause" id="pause-btn" onclick="window.sbPauseRecording()"><i class="fas fa-pause"></i></button>
                    <button class="record-btn record-done" id="done-btn" onclick="window.sbDoneRecording()"><i class="fas fa-check"></i> Done</button>
                    <button class="record-btn record-cancel" onclick="window.sbCancelRecording()"><i class="fas fa-times"></i></button>
                </div>
            `;
            composeEditor.parentNode.insertBefore(recorder, composeEditor);
            
            const preview = document.createElement('div');
            preview.id = 'audio-preview';
            preview.className = 'audio-preview';
            preview.innerHTML = `
                <div class="audio-preview-icon"><i class="fas fa-microphone"></i></div>
                <div class="audio-preview-info">
                    <span class="audio-preview-name">Voice Message</span>
                    <span class="audio-preview-duration" id="audio-duration">00:00</span>
                </div>
                <button class="audio-preview-play" id="audio-play-btn" onclick="window.sbPlayAudio()"><i class="fas fa-play"></i></button>
                <button class="audio-preview-remove" onclick="window.sbRemoveAudio()"><i class="fas fa-times"></i></button>
            `;
            composeEditor.parentNode.insertBefore(preview, composeEditor);
        }
        
        document.addEventListener('click', (e) => {
            const picker = document.getElementById('emoji-picker');
            if (picker && !e.target.closest('.emoji-picker') && !e.target.closest('#emoji-btn')) {
                picker.classList.remove('open');
            }
        });
    }
    
    // ========== TYPING ==========
    let typingTimer = null;
    function showTyping(name) {
        const el = document.getElementById('typing-indicator');
        const txt = document.getElementById('typing-text');
        if (el && txt) {
            txt.textContent = name + ' is typing...';
            el.classList.add('show');
        }
        clearTimeout(typingTimer);
        typingTimer = setTimeout(hideTyping, 3000);
    }
    function hideTyping() {
        document.getElementById('typing-indicator')?.classList.remove('show');
    }
    
    // ========== EMOJI ==========
    function toggleEmojiPicker(e) {
        e && e.stopPropagation();
        const picker = document.getElementById('emoji-picker');
        if (picker) {
            if (!picker.classList.contains('open')) showEmojis('smileys');
            picker.classList.toggle('open');
        }
    }
    
    function showEmojis(category) {
        const grid = document.getElementById('emoji-grid');
        const tabs = document.querySelectorAll('.emoji-tab');
        const list = emojiData[category] || emojiData.smileys;
        
        if (grid) {
            grid.innerHTML = list.map(e => 
                `<button class="emoji-btn" onclick="window.sbInsertEmoji('${e}')">${e}</button>`
            ).join('');
        }
        tabs.forEach((tab, i) => {
            tab.classList.toggle('active', Object.keys(emojiData)[i] === category);
        });
    }
    
    window.sbInsertEmoji = function(emoji) {
        const ta = document.getElementById('compose-body') || document.getElementById('reply-text');
        if (!ta) return;
        const start = ta.selectionStart;
        ta.value = ta.value.substring(0, start) + emoji + ta.value.substring(ta.selectionEnd);
        ta.selectionStart = ta.selectionEnd = start + emoji.length;
        ta.focus();
        document.getElementById('emoji-picker')?.classList.remove('open');
    };
    
    // ========== AUDIO RECORDING ==========
    async function startRecording() {
        if (isRecording) return;
        
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
            audioChunks = [];
            
            mediaRecorder.ondataavailable = e => {
                if (e.data.size > 0) audioChunks.push(e.data);
            };
            
            mediaRecorder.onstop = () => {
                stream.getTracks().forEach(t => t.stop());
            };
            
            mediaRecorder.start(1000);
            isRecording = true;
            isPaused = false;
            recordStart = Date.now();
            pausedTime = 0;
            
            document.getElementById('audio-recorder').classList.add('active');
            document.getElementById('mic-btn').style.color = '#ef4444';
            updatePauseButton();
            recordInterval = setInterval(updateRecordTime, 1000);
            
        } catch(err) {
            alert('Microphone access denied. HTTPS required.');
        }
    }
    
    window.sbPauseRecording = function() {
        if (!mediaRecorder || !isRecording) return;
        
        if (isPaused) {
            mediaRecorder.resume();
            isPaused = false;
            recordStart = Date.now() - pausedTime;
            recordInterval = setInterval(updateRecordTime, 1000);
        } else {
            mediaRecorder.pause();
            isPaused = true;
            pausedTime = Date.now() - recordStart;
            clearInterval(recordInterval);
        }
        updatePauseButton();
    };
    
    function updatePauseButton() {
        const btn = document.getElementById('pause-btn');
        if (btn) {
            btn.innerHTML = isPaused ? '<i class="fas fa-play"></i>' : '<i class="fas fa-pause"></i>';
        }
    }
    
    window.sbDoneRecording = function() {
        if (!mediaRecorder || !isRecording) return;
        
        clearInterval(recordInterval);
        const finalDuration = isPaused ? pausedTime : (Date.now() - recordStart);
        const secs = Math.floor(finalDuration / 1000);
        const m = Math.floor(secs / 60).toString().padStart(2, '0');
        const s = (secs % 60).toString().padStart(2, '0');
        
        mediaRecorder.stop();
        isRecording = false;
        isPaused = false;
        
        setTimeout(() => {
            if (audioChunks.length > 0) {
                audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
                audioReady = true;
                
                document.getElementById('audio-recorder').classList.remove('active');
                document.getElementById('audio-preview').classList.add('active');
                document.getElementById('audio-duration').textContent = m + ':' + s;
                document.getElementById('mic-btn').style.color = '';
                
                if (typeof showToast === 'function') showToast('Voice ready', 'success');
            } else {
                window.sbCancelRecording();
            }
        }, 500);
    };
    
    window.sbCancelRecording = function() {
        if (mediaRecorder && isRecording) mediaRecorder.stop();
        clearInterval(recordInterval);
        isRecording = false;
        isPaused = false;
        audioChunks = [];
        audioBlob = null;
        audioReady = false;
        
        document.getElementById('audio-recorder')?.classList.remove('active');
        document.getElementById('audio-preview')?.classList.remove('active');
        document.getElementById('record-time').textContent = '00:00';
        document.getElementById('mic-btn').style.color = '';
    };
    
    window.sbRemoveAudio = function() {
        audioBlob = null;
        audioReady = false;
        document.getElementById('audio-preview')?.classList.remove('active');
    };
    
    let audioPlayer = null;
    window.sbPlayAudio = function() {
        if (!audioBlob) return;
        const btn = document.getElementById('audio-play-btn');
        
        if (audioPlayer) {
            audioPlayer.pause();
            audioPlayer = null;
            btn.innerHTML = '<i class="fas fa-play"></i>';
            return;
        }
        
        audioPlayer = new Audio(URL.createObjectURL(audioBlob));
        audioPlayer.play();
        btn.innerHTML = '<i class="fas fa-pause"></i>';
        audioPlayer.onended = () => {
            btn.innerHTML = '<i class="fas fa-play"></i>';
            audioPlayer = null;
        };
    };
    
    function updateRecordTime() {
        const secs = Math.floor((Date.now() - recordStart) / 1000);
        const m = Math.floor(secs / 60).toString().padStart(2, '0');
        const s = (secs % 60).toString().padStart(2, '0');
        document.getElementById('record-time').textContent = m + ':' + s;
    }
    
    // ========== OVERRIDE SEND EMAIL ==========
    const originalSendEmail = window.sendEmail;
    window.sendEmail = async function() {
        if (audioReady && audioBlob) {
            const to = document.getElementById('compose-to')?.value;
            const subject = document.getElementById('compose-subject')?.value || '🎤 Voice Message';
            const body = document.getElementById('compose-body')?.value || '';
            
            if (!to) {
                if (typeof showToast === 'function') showToast('Enter recipient', 'error');
                return;
            }
            
            const reader = new FileReader();
            reader.onloadend = async () => {
                try {
                    const r = await fetch('/api/send', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        credentials: 'same-origin',
                        body: JSON.stringify({
                            to: to,
                            subject: subject,
                            body: body + (body ? '\n\n' : '') + '🎤 Voice message attached',
                            has_audio: true,
                            audio_data: reader.result.split(',')[1]
                        })
                    });
                    const data = await r.json();
                    if (data.success) {
                        if (typeof showToast === 'function') showToast('Sent!', 'success');
                        window.sbCancelRecording();
                        if (typeof closeCompose === 'function') closeCompose();
                        if (typeof loadFolder === 'function') loadFolder('sent');
                    } else {
                        if (typeof showToast === 'function') showToast(data.error || 'Failed', 'error');
                    }
                } catch(e) {
                    if (typeof showToast === 'function') showToast('Failed', 'error');
                }
            };
            reader.readAsDataURL(audioBlob);
        } else if (originalSendEmail) {
            return originalSendEmail.apply(this, arguments);
        }
    };
    
    // ========== DRAFT ==========
    window.saveDraft = async function() {
        const to = document.getElementById('compose-to')?.value || '';
        const subject = document.getElementById('compose-subject')?.value || '';
        const body = document.getElementById('compose-body')?.value || '';
        
        if (!to && !subject && !body) {
            if (typeof showToast === 'function') showToast('Nothing to save', 'info');
            return;
        }
        
        try {
            const r = await fetch('/api/send', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'same-origin',
                body: JSON.stringify({ to, subject, body, draft: true })
            });
            const data = await r.json();
            if (data.success) {
                if (typeof showToast === 'function') showToast('Draft saved', 'success');
                if (typeof loadCounts === 'function') loadCounts();
            }
        } catch(e) {}
    };
    
    // ========== CONTACTS PANEL ==========
    window.loadContacts = async function() {
        const container = document.getElementById('contacts-content');
        if (!container) return;
        
        container.innerHTML = '<p style="text-align:center;color:#6b7280;padding:20px;">Loading...</p>';
        
        try {
            const r = await fetch('/api/contacts', { credentials: 'same-origin' });
            const data = await r.json();
            
            if (data.success && data.contacts && data.contacts.length > 0) {
                container.innerHTML = data.contacts.map(c => `
                    <div class="contact-item" onclick="window.sbComposeToContact('${c.email}')">
                        <div class="contact-avatar" style="background:${getColorForEmail(c.email)}">${c.name[0].toUpperCase()}</div>
                        <div class="contact-info">
                            <div class="contact-name">${escapeHtml(c.name)}</div>
                            <div class="contact-email">${escapeHtml(c.email)}</div>
                        </div>
                        <span class="contact-count">${c.count}</span>
                    </div>
                `).join('');
            } else {
                container.innerHTML = '<p style="text-align:center;color:#6b7280;padding:20px;">No contacts yet. Send some emails!</p>';
            }
        } catch(e) {
            container.innerHTML = '<p style="text-align:center;color:#ef4444;padding:20px;">Failed to load</p>';
        }
    };
    
    window.sbComposeToContact = function(email) {
        if (typeof openCompose === 'function') openCompose();
        setTimeout(() => {
            const input = document.getElementById('compose-to');
            if (input) input.value = email;
        }, 100);
    };
    
    // ========== CALENDAR PANEL ==========
    window.renderCalendar = async function() {
        const container = document.getElementById('calendar-content');
        if (!container) return;
        
        const now = new Date();
        const monthNames = ['January','February','March','April','May','June','July','August','September','October','November','December'];
        const daysInMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
        const firstDay = new Date(now.getFullYear(), now.getMonth(), 1).getDay();
        
        let html = `
            <div style="text-align:center;margin-bottom:16px;">
                <h4 style="font-size:16px;font-weight:600;margin:0;">${monthNames[now.getMonth()]} ${now.getFullYear()}</h4>
            </div>
            <div style="display:grid;grid-template-columns:repeat(7,1fr);gap:2px;text-align:center;font-size:11px;margin-bottom:8px;">
                <div style="color:#6b7280;font-weight:600;">S</div>
                <div style="color:#6b7280;font-weight:600;">M</div>
                <div style="color:#6b7280;font-weight:600;">T</div>
                <div style="color:#6b7280;font-weight:600;">W</div>
                <div style="color:#6b7280;font-weight:600;">T</div>
                <div style="color:#6b7280;font-weight:600;">F</div>
                <div style="color:#6b7280;font-weight:600;">S</div>
            </div>
            <div style="display:grid;grid-template-columns:repeat(7,1fr);gap:2px;">
        `;
        
        for (let i = 0; i < firstDay; i++) {
            html += '<div style="padding:8px;"></div>';
        }
        
        for (let d = 1; d <= daysInMonth; d++) {
            const isToday = d === now.getDate();
            html += `<div style="padding:8px;text-align:center;border-radius:6px;cursor:pointer;${isToday ? 'background:#f86d31;color:white;font-weight:600;' : ''}" onclick="window.sbShowDate(${d})">${d}</div>`;
        }
        
        html += '</div>';
        
        // Load events
        try {
            const r = await fetch('/api/calendar/events', { credentials: 'same-origin' });
            const data = await r.json();
            if (data.success && data.events && data.events.length > 0) {
                html += '<div style="margin-top:16px;border-top:1px solid #e5e7eb;padding-top:12px;"><h5 style="font-size:13px;font-weight:600;margin:0 0 8px 0;">Upcoming</h5>';
                data.events.slice(0, 5).forEach(e => {
                    html += `<div style="padding:8px;background:#f9fafb;border-radius:6px;margin-bottom:6px;font-size:12px;">
                        <div style="font-weight:500;">${escapeHtml(e.title)}</div>
                        <div style="color:#6b7280;">${e.date || ''} ${e.time || ''}</div>
                    </div>`;
                });
                html += '</div>';
            }
        } catch(e) {}
        
        container.innerHTML = html;
    };
    
    window.sbShowDate = function(day) {
        if (typeof showToast === 'function') showToast('Date: ' + day, 'info');
    };
    
    // ========== FILES PANEL ==========
    window.loadFiles = async function() {
        const container = document.getElementById('files-content');
        if (!container) return;
        
        container.innerHTML = '<p style="text-align:center;color:#6b7280;padding:20px;">Loading...</p>';
        
        try {
            const r = await fetch('/api/files', { credentials: 'same-origin' });
            const data = await r.json();
            
            if (data.success && data.files && data.files.length > 0) {
                container.innerHTML = data.files.map(f => {
                    const icon = f.type?.includes('image') ? 'fa-image' : 
                                f.type?.includes('pdf') ? 'fa-file-pdf' : 
                                f.type?.includes('word') ? 'fa-file-word' : 'fa-file';
                    const size = f.size ? (f.size > 1024*1024 ? (f.size/1024/1024).toFixed(1) + ' MB' : (f.size/1024).toFixed(1) + ' KB') : '';
                    return `
                        <div class="file-item" onclick="window.open('/api/attachment/${f.id}')">
                            <i class="fas ${icon}" style="font-size:24px;color:#6b7280;"></i>
                            <div class="file-info">
                                <div class="file-name">${escapeHtml(f.name)}</div>
                                <div class="file-size">${size}</div>
                            </div>
                        </div>
                    `;
                }).join('');
            } else {
                container.innerHTML = '<p style="text-align:center;color:#6b7280;padding:20px;">No files yet</p>';
            }
        } catch(e) {
            container.innerHTML = '<p style="text-align:center;color:#ef4444;padding:20px;">Failed to load</p>';
        }
    };
    
})();

// ========== LIVE CHAT FEATURE ==========

(function() {
    let currentChatUser = null;
    let chatMessages = [];
    
    // Add switch button to compose modal when it opens
    function addChatSwitchToCompose() {
        const composeHeader = document.querySelector('.compose-header');
        if (!composeHeader || document.getElementById('chat-switch')) return;
        
        const switchDiv = document.createElement('div');
        switchDiv.className = 'compose-mode-switch';
        switchDiv.innerHTML = `
            <label>
                <span>💬 Live Chat</span>
                <div class="switch-toggle" id="chat-switch" onclick="window.toggleLiveChat()"></div>
            </label>
        `;
        
        const closeBtn = composeHeader.querySelector('.compose-close');
        if (closeBtn) {
            composeHeader.insertBefore(switchDiv, closeBtn);
        }
    }
    
    // Create live chat window
    function createChatWindow() {
        if (document.getElementById('live-chat-overlay')) return;
        
        const overlay = document.createElement('div');
        overlay.id = 'live-chat-overlay';
        overlay.className = 'chat-overlay';
        overlay.onclick = (e) => {
            if (e.target === overlay) closeLiveChat();
        };
        
        const chatWindow = document.createElement('div');
        chatWindow.id = 'live-chat-window';
        chatWindow.className = 'live-chat-window';
        chatWindow.innerHTML = `
            <div class="chat-header">
                <div class="chat-header-avatar" id="chat-avatar">?</div>
                <div class="chat-header-info">
                    <div class="chat-header-name" id="chat-recipient-name">Select Contact</div>
                    <div class="chat-header-status">
                        <span class="online-dot"></span>
                        <span id="chat-status-text">Online</span>
                    </div>
                </div>
                <div class="chat-header-actions">
                    <button class="chat-header-btn" onclick="window.showChatUsers()" title="Contacts"><i class="fas fa-users"></i></button>
                    <button class="chat-header-btn" onclick="window.closeLiveChat()" title="Close"><i class="fas fa-times"></i></button>
                </div>
            </div>
            <div class="chat-users-list" id="chat-users-list"></div>
            <div class="chat-messages" id="chat-messages">
                <div class="chat-date-divider"><span>Today</span></div>
                <div class="chat-typing" id="chat-typing">
                    <span></span><span></span><span></span>
                </div>
            </div>
            <div class="chat-input-area">
                <button class="chat-input-btn" onclick="window.chatEmoji()"><i class="fas fa-smile"></i></button>
                <div class="chat-input-wrapper">
                    <input type="text" class="chat-input" id="chat-input" placeholder="Type a message" onkeypress="if(event.key==='Enter')window.sendChatMessage()">
                </div>
                <button class="chat-input-btn" onclick="window.chatAttach()"><i class="fas fa-paperclip"></i></button>
                <button class="chat-send-btn" onclick="window.sendChatMessage()"><i class="fas fa-paper-plane"></i></button>
            </div>
        `;
        
        document.body.appendChild(overlay);
        document.body.appendChild(chatWindow);
    }
    
    // Toggle live chat
    window.toggleLiveChat = function() {
        const toggle = document.getElementById('chat-switch');
        if (toggle) {
            toggle.classList.toggle('active');
            if (toggle.classList.contains('active')) {
                openLiveChat();
            }
        }
    };
    
    // Open live chat window
    function openLiveChat() {
        createChatWindow();
        
        // Get recipient from compose
        const toInput = document.getElementById('compose-to');
        if (toInput && toInput.value) {
            setCurrentChatUser(toInput.value);
        }
        
        document.getElementById('live-chat-overlay').classList.add('open');
        document.getElementById('live-chat-window').classList.add('open');
        document.getElementById('chat-input').focus();
        
        // Load contacts
        loadChatContacts();
        
        // Connect to socket for this chat
        if (typeof socket !== 'undefined' && socket) {
            socket.emit('join_chat', { with: currentChatUser });
        }
    }
    
    // Close live chat
    window.closeLiveChat = function() {
        document.getElementById('live-chat-overlay')?.classList.remove('open');
        document.getElementById('live-chat-window')?.classList.remove('open');
        document.getElementById('chat-switch')?.classList.remove('active');
    };
    
    // Set current chat user
    function setCurrentChatUser(email) {
        currentChatUser = email;
        const name = email.split('@')[0].replace(/[._]/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
        document.getElementById('chat-recipient-name').textContent = name;
        document.getElementById('chat-avatar').textContent = name[0].toUpperCase();
        document.getElementById('chat-avatar').style.background = getColorForEmail(email);
        document.getElementById('chat-users-list').classList.remove('open');
        
        // Load chat history
        loadChatHistory(email);
    }
    
    // Load contacts for chat
    async function loadChatContacts() {
        try {
            const r = await fetch('/api/contacts', { credentials: 'same-origin' });
            const data = await r.json();
            
            const container = document.getElementById('chat-users-list');
            if (data.success && data.contacts && data.contacts.length > 0) {
                container.innerHTML = data.contacts.slice(0, 10).map(c => `
                    <div class="chat-user-item" onclick="window.selectChatUser('${c.email}')">
                        <div class="chat-user-avatar" style="background:${getColorForEmail(c.email)}">${c.name[0].toUpperCase()}</div>
                        <div class="chat-user-info">
                            <div class="chat-user-name">${escapeHtml(c.name)}</div>
                            <div class="chat-user-email">${escapeHtml(c.email)}</div>
                        </div>
                    </div>
                `).join('');
            } else {
                container.innerHTML = '<div style="padding:20px;text-align:center;color:#667781;">No contacts yet</div>';
            }
        } catch(e) {
            console.log('Error loading contacts:', e);
        }
    }
    
    // Show chat users list
    window.showChatUsers = function() {
        document.getElementById('chat-users-list').classList.toggle('open');
    };
    
    // Select chat user
    window.selectChatUser = function(email) {
        setCurrentChatUser(email);
    };
    
    // Load chat history
    async function loadChatHistory(email) {
        const container = document.getElementById('chat-messages');
        const typing = document.getElementById('chat-typing');
        
        // Clear existing messages except typing indicator
        container.innerHTML = '<div class="chat-date-divider"><span>Today</span></div>';
        container.appendChild(typing);
        
        try {
            const r = await fetch(`/api/chat/history?with=${encodeURIComponent(email)}`, { credentials: 'same-origin' });
            const data = await r.json();
            
            if (data.success && data.messages) {
                data.messages.forEach(msg => {
                    addChatMessage(msg.content, msg.sent_by_me, msg.time, false);
                });
            }
        } catch(e) {
            // No history yet - that's fine
        }
        
        scrollChatToBottom();
    }
    
    // Add message to chat
    function addChatMessage(content, isSent, time, animate = true) {
        const container = document.getElementById('chat-messages');
        const typing = document.getElementById('chat-typing');
        
        const msg = document.createElement('div');
        msg.className = `chat-message ${isSent ? 'sent' : 'received'}`;
        if (animate) msg.style.animation = 'chatSlideIn 0.2s ease';
        
        const timeStr = time || new Date().toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});
        
        msg.innerHTML = `
            ${escapeHtml(content)}
            <div class="chat-message-time">
                ${timeStr}
                ${isSent ? '<i class="fas fa-check-double chat-message-status"></i>' : ''}
            </div>
        `;
        
        container.insertBefore(msg, typing);
        scrollChatToBottom();
    }
    
    // Send chat message
    window.sendChatMessage = async function() {
        const input = document.getElementById('chat-input');
        const content = input.value.trim();
        
        if (!content || !currentChatUser) return;
        
        input.value = '';
        
        // Add message to UI immediately
        addChatMessage(content, true);
        
        // Send via WebSocket for real-time
        if (typeof socket !== 'undefined' && socket) {
            socket.emit('chat_message', {
                to: currentChatUser,
                content: content
            });
        }
        
        // Also save via API
        try {
            await fetch('/api/chat/send', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'same-origin',
                body: JSON.stringify({
                    to: currentChatUser,
                    content: content
                })
            });
        } catch(e) {
            console.log('Error saving message:', e);
        }
    };
    
    // Receive chat message (called from socket)
    window.receiveChatMessage = function(data) {
        if (data.from === currentChatUser) {
            addChatMessage(data.content, false, data.time);
            // Play sound
            if (typeof playSound === 'function') playSound();
        }
    };
    
    // Show typing indicator
    window.showChatTyping = function(from) {
        if (from === currentChatUser) {
            document.getElementById('chat-typing')?.classList.add('show');
            setTimeout(() => {
                document.getElementById('chat-typing')?.classList.remove('show');
            }, 3000);
        }
    };
    
    // Chat emoji
    window.chatEmoji = function() {
        const emojis = ['😀','😊','👍','❤️','🎉','✨','🔥','💯','👏','🙏','😂','🤔','👀','💪','🙌','😍','🥰','😘'];
        const input = document.getElementById('chat-input');
        input.value += emojis[Math.floor(Math.random() * emojis.length)];
        input.focus();
    };
    
    // Chat attachment
    window.chatAttach = function() {
        if (typeof showToast === 'function') {
            showToast('File sharing coming soon!', 'info');
        }
    };
    
    // Scroll chat to bottom
    function scrollChatToBottom() {
        const container = document.getElementById('chat-messages');
        if (container) {
            container.scrollTop = container.scrollHeight;
        }
    }
    
    // Helper functions
    function getColorForEmail(email) {
        const colors = ['#f86d31', '#3b82f6', '#10b981', '#8b5cf6', '#ec4899', '#f59e0b', '#06b6d4'];
        let hash = 0;
        for (let i = 0; i < email.length; i++) hash += email.charCodeAt(i);
        return colors[hash % colors.length];
    }
    
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    // Watch for compose modal opening
    const observer = new MutationObserver((mutations) => {
        mutations.forEach((mutation) => {
            if (mutation.type === 'attributes' && mutation.attributeName === 'class') {
                const modal = document.getElementById('compose-modal');
                if (modal && modal.classList.contains('active')) {
                    setTimeout(addChatSwitchToCompose, 100);
                }
            }
        });
    });
    
    // Start observing
    setTimeout(() => {
        const modal = document.getElementById('compose-modal');
        if (modal) {
            observer.observe(modal, { attributes: true });
        }
    }, 1000);
    
    // Listen for socket chat events
    if (typeof socket !== 'undefined' && socket) {
        socket.on('chat_message', (data) => {
            window.receiveChatMessage(data);
        });
        
        socket.on('chat_typing', (data) => {
            window.showChatTyping(data.from);
        });
    }
    
})();
