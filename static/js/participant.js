let socket;
let peer;
let participantId;
let participantName;
let isAdmin = false;
let isMuted = false;

// MediaPipe
let faceMesh;
let hands;
let camera;
let currentFaceLandmarks = null;
let currentHandLandmarks = null;
let recognition;

// PeerJS
let myStream;
let peers = {};
let myVideoElement;


// ═══════════════════════════════════════════════════════════════
// STEP 1: JOIN SESSION
// ═══════════════════════════════════════════════════════════════

function joinSession() {
    const urlParams    = new URLSearchParams(window.location.search);
    const nameFromUrl  = urlParams.get('name');

    if (nameFromUrl) {
        participantName = decodeURIComponent(nameFromUrl);
    } else {
        const name = document.getElementById('name-input').value.trim();
        if (!name) {
            showError("Please enter your name.");
            return;
        }
        participantName = name;
    }

    isAdmin = urlParams.get('admin') === 'true';

    document.getElementById('join-form').style.display    = 'none';
    document.getElementById('monitor-area').style.display = 'block';
    document.getElementById('welcome-text').textContent   = `Welcome, ${participantName}!`;

    startConnection();
}

async function startConnection() {

    // Guard — prevent double connection
    if (socket) {
        console.warn('Already connected — ignoring duplicate call');
        return;
    }

    socket = io();

    socket.emit('join_session', {
        session_id: SESSION_ID,
        name:       participantName,
        is_admin:   isAdmin
    });

    socket.on('joined', async (data) => {

        // Guard — only run once
        if (participantId) {
            console.warn('Already have participantId — ignoring duplicate joined event');
            return;
        }

        participantId = data.participant_id;
        console.log('✅ Joined as:', participantName, '| pid:', participantId, '| isAdmin:', isAdmin);

        try {
            await startMedia();
            initializePeer();
            initializeMediaPipe();
            initializeSpeechRecognition();
            startSendingLandmarks();
        } catch (err) {
            console.error('❌ Session start failed:', err.message);
        }
    });

    socket.on('participant_joined', (data) => {
        if (data.participant_id !== participantId && data.peer_id) {
            connectToNewPeer(data.peer_id, data.name);
        }
    });

    socket.on('existing_participants', (list) => {
        list.forEach(p => connectToNewPeer(p.peer_id, p.name));
    });

    socket.on('participant_left', (data) => {
        if (peers[data.peer_id]) {
            peers[data.peer_id].close();
            delete peers[data.peer_id];
        }
        removeVideoElement(data.peer_id);
        removeVideoElement(data.participant_id);
    });

    socket.on('status_update', (data) => {
        updateMyStatus(data);
    });

    // ── MUTE ────────────────────────────────────────────────────
    socket.on('mute_status', (data) => {
        if (isAdmin) return;  // admin ignores mute

        isMuted = data.muted;

        if (myStream) {
            myStream.getAudioTracks().forEach(track => {
                track.enabled = !isMuted;  // false = mic off, true = mic on
            });
        }

        const statusEl = document.getElementById('mute-status');
        if (data.muted) {
            statusEl.style.background = '#DC3545';
            statusEl.textContent      = '🔇 Muted by instructor';
            if (recognition) recognition.stop();
        } else {
            statusEl.style.background = '#4CAF50';
            statusEl.textContent      = '🔊 You can speak';
            if (recognition) recognition.start();
        }
    });

    socket.on('live_transcript', (data) => {
        displayTranscript(data);
    });

    socket.on('session_ended', (data) => {
        if (camera)      camera.stop();
        if (recognition) recognition.stop();
        if (myStream)    myStream.getTracks().forEach(t => t.stop());
        window.location.href = data.redirect || '/';
    });
}


// ═══════════════════════════════════════════════════════════════
// STEP 2: START MEDIA
// ═══════════════════════════════════════════════════════════════

async function startMedia() {
    try {
        myStream = await navigator.mediaDevices.getUserMedia({
            video: { width: 640, height: 480 },
            audio: {
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl:  true
            }
        });

        console.log('✅ Camera and mic started');
        addVideoStream('me', myStream, `${participantName} (You)`, true);
        document.getElementById('mediapipe-video').srcObject = myStream;

    } catch (err) {
        console.error('❌ Camera/mic error:', err.name, err.message);

        // Show clear error on page
        document.getElementById('video-grid').innerHTML = `
            <div style="color:#f44336; padding:20px; background:#1a0000;
                        border-radius:8px; border:1px solid #f44336; width:100%;">
                <strong>❌ Camera/Microphone Blocked</strong><br><br>
                To fix this:<br>
                1. Click the 🔒 lock icon in your browser address bar<br>
                2. Set Camera and Microphone to <strong>Allow</strong><br>
                3. Refresh this page
            </div>
        `;
        throw new Error('Media access denied');
    }
}


// ═══════════════════════════════════════════════════════════════
// STEP 3: PEERJS
// ═══════════════════════════════════════════════════════════════

function initializePeer() {
    peer = new Peer(participantId);

    peer.on('open', (id) => {
        console.log('✅ PeerJS ready:', id);
        socket.emit('peer_ready', {
            session_id:     SESSION_ID,
            participant_id: participantId,
            peer_id:        id,
            name:           participantName
        });
    });

    peer.on('call', (call) => {
        call.answer(myStream);
        call.on('stream', (remoteStream) => {
            addVideoStream(
                call.peer,
                remoteStream,
                call.metadata?.name || 'Participant',
                false
            );
            peers[call.peer] = call;
        });
    });

    peer.on('error', (err) => {
        console.error('❌ PeerJS error:', err.type, err.message);
    });
}

function connectToNewPeer(peerId, peerName) {
    if (peers[peerId]) return;

    const call = peer.call(peerId, myStream, {
        metadata: { name: participantName }
    });

    call.on('stream', (remoteStream) => {
        addVideoStream(peerId, remoteStream, peerName, false);
        peers[peerId] = call;
    });

    call.on('close', () => removeVideoElement(peerId));
}


// ═══════════════════════════════════════════════════════════════
// STEP 4: VIDEO TILES
// ═══════════════════════════════════════════════════════════════

function addVideoStream(peerId, stream, name, isMe) {
    if (document.getElementById(`video-container-${peerId}`)) return;

    const container       = document.createElement('div');
    container.className   = 'video-container';
    container.id          = `video-container-${peerId}`;

    const video           = document.createElement('video');
    video.srcObject       = stream;
    video.autoplay        = true;
    video.playsInline     = true;
    if (isMe) video.muted = true;  // no echo from own video

    const label           = document.createElement('div');
    label.className       = 'video-label';
    label.textContent     = name;

    const status          = document.createElement('div');
    status.className      = 'video-status status-focused';
    status.id             = `status-${peerId}`;
    status.textContent    = isMe ? 'Tracking...' : '';

    container.appendChild(video);
    container.appendChild(label);
    container.appendChild(status);

    document.getElementById('video-grid').appendChild(container);

    if (isMe) myVideoElement = container;
}

function removeVideoElement(peerId) {
    const el = document.getElementById(`video-container-${peerId}`);
    if (el) el.remove();
}

function updateMyStatus(data) {
    const statusEl = document.getElementById('status-me');
    if (statusEl) {
        statusEl.textContent = data.engagement;
        statusEl.className   = data.engagement === 'Focused'
            ? 'video-status status-focused'
            : 'video-status status-distracted';
    }
}


// ═══════════════════════════════════════════════════════════════
// STEP 5: MEDIAPIPE
// ═══════════════════════════════════════════════════════════════

function initializeMediaPipe() {
    faceMesh = new FaceMesh({
        locateFile: (file) =>
            `https://cdn.jsdelivr.net/npm/@mediapipe/face_mesh@0.4/${file}`
    });
    faceMesh.setOptions({
        maxNumFaces:            1,
        refineLandmarks:        true,
        minDetectionConfidence: 0.5,
        minTrackingConfidence:  0.5
    });
    faceMesh.onResults((results) => {
        currentFaceLandmarks = results.multiFaceLandmarks?.[0]
            ? results.multiFaceLandmarks[0].map(lm => ({
                x: lm.x, y: lm.y, z: lm.z
              }))
            : null;
    });

    hands = new Hands({
        locateFile: (file) =>
            `https://cdn.jsdelivr.net/npm/@mediapipe/hands/${file}`
    });
    hands.setOptions({
        maxNumHands:            1,
        modelComplexity:        0,
        minDetectionConfidence: 0.5,
        minTrackingConfidence:  0.5
    });
    hands.onResults((results) => {
        currentHandLandmarks = results.multiHandLandmarks?.[0]
            ? results.multiHandLandmarks[0].map(lm => ({
                x: lm.x, y: lm.y, z: lm.z
              }))
            : null;
    });

    const videoEl = document.getElementById('mediapipe-video');
    camera = new Camera(videoEl, {
        onFrame: async () => {
            await faceMesh.send({ image: videoEl });
            await hands.send({   image: videoEl });
        },
        width: 640, height: 480
    });
    camera.start();
}

function startSendingLandmarks() {
    let lastSendTime = 0;
    setInterval(() => {
        const now = Date.now();
        if (now - lastSendTime < 500)              return;
        if (!socket || !participantId)             return;
        if (!currentFaceLandmarks)                 return;

        socket.emit('landmarks_data', {
            session_id:     SESSION_ID,
            participant_id: participantId,
            face_landmarks: currentFaceLandmarks,
            hand_landmarks: currentHandLandmarks
        });

        lastSendTime = now;
    }, 200);
}


// ═══════════════════════════════════════════════════════════════
// STEP 6: SPEECH RECOGNITION
// ═══════════════════════════════════════════════════════════════

function initializeSpeechRecognition() {
    const SpeechRecognition =
        window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
        console.warn('⚠️ Speech recognition not supported in this browser');
        return;
    }

    recognition                = new SpeechRecognition();
    recognition.continuous     = true;
    recognition.interimResults = true;
    recognition.lang           = 'en-GB';

    recognition.onresult = (event) => {

        // ── DEBUG — check browser console ───────────────────────
        console.log('🎤 Speech fired | name:', participantName,
                    '| pid:', participantId, '| isAdmin:', isAdmin);

        if (isMuted && !isAdmin) return;

        let finalTranscript   = '';
        let interimTranscript = '';

        for (let i = event.resultIndex; i < event.results.length; i++) {
            const text = event.results[i][0].transcript.trim();
            if (event.results[i].isFinal) {
                finalTranscript += text + ' ';
            } else {
                interimTranscript += text;
            }
        }

        const feed = document.getElementById('transcript-feed');

        // ── INTERIM — grey italic text while speaking ────────────
        let interimEl = document.getElementById('interim-transcript');

        if (interimTranscript) {
            if (!interimEl) {
                interimEl                    = document.createElement('div');
                interimEl.id                 = 'interim-transcript';
                interimEl.style.color        = '#888';
                interimEl.style.fontStyle    = 'italic';
                interimEl.style.padding      = '4px 8px';
                interimEl.style.borderLeft   = '2px solid #555';
                interimEl.style.marginBottom = '4px';

                // Remove placeholder if still there
                const placeholder = feed.querySelector('p');
                if (placeholder) placeholder.remove();

                feed.insertBefore(interimEl, feed.firstChild);
            }
            interimEl.textContent = `${participantName}: ${interimTranscript}...`;
        }

        // ── FINAL — send to server ───────────────────────────────
        if (finalTranscript.trim()) {

            if (interimEl) interimEl.remove();

            console.log('📤 Sending transcript:', finalTranscript.trim(),
                        '| as:', participantName, '| pid:', participantId);

            socket.emit('transcript_update', {
                session_id:     SESSION_ID,
                participant_id: participantId,
                name:           participantName,
                text:           finalTranscript.trim(),
                is_admin:       isAdmin
            });
        }
    };

    recognition.onerror = (e) => {
        if (e.error !== 'no-speech') {
            console.warn('⚠️ Speech error:', e.error);
        }
    };

    recognition.onend = () => {
        // Auto-restart unless muted or session ended
        if (participantId && (!isMuted || isAdmin)) {
            recognition.start();
        }
    };

    recognition.start();
    console.log('✅ Speech recognition started for:', participantName);
}


// ═══════════════════════════════════════════════════════════════
// TRANSCRIPT DISPLAY — shown to everyone from server broadcast
// ═══════════════════════════════════════════════════════════════

function displayTranscript(data) {
    const feed = document.getElementById('transcript-feed');

    // Remove placeholder
    const placeholder = feed.querySelector('p');
    if (placeholder) placeholder.remove();

    // Remove interim when final arrives from server
    const interimEl = document.getElementById('interim-transcript');
    if (interimEl) interimEl.remove();

    const entry = document.createElement('div');
    entry.style.marginBottom = '10px';
    entry.style.padding      = '8px';
    entry.style.borderRadius = '4px';
    entry.style.paddingLeft  = '10px';

    if (data.is_admin) {
        // Instructor — green
        entry.style.background = '#1a2a1a';
        entry.style.borderLeft = '3px solid #4CAF50';
    } else {
        // Participant — blue, clearly visible
        entry.style.background = '#1a1a2e';
        entry.style.borderLeft = '3px solid #2196F3';
    }

    entry.innerHTML = `
        <span style="color:#888; font-size:12px;">[${data.timestamp}]</span>
        <strong style="color:${data.is_admin ? '#4CAF50' : '#2196F3'};">
            ${data.name}${data.is_admin ? ' (Instructor)' : ''}:
        </strong>
        <span style="color:#ddd;"> "${data.text}"</span>
    `;

    feed.insertBefore(entry, feed.firstChild);

    // Cap at 20 entries
    while (feed.children.length > 20) feed.removeChild(feed.lastChild);

    // Highlight speaker video tile for 2 seconds
    const tile = document.getElementById(`video-container-${data.participant_id}`);
    if (tile) {
        tile.classList.add('speaking');
        setTimeout(() => tile.classList.remove('speaking'), 2000);
    }
}


// ═══════════════════════════════════════════════════════════════
// STEP 7: LEAVE SESSION
// ═══════════════════════════════════════════════════════════════

function leaveSession() {
    if (confirm('Are you sure you want to leave?')) {
        if (camera)      camera.stop();
        if (recognition) recognition.stop();
        if (myStream)    myStream.getTracks().forEach(t => t.stop());
        if (peer)        peer.destroy();

        socket.emit('participant_leaving', {
            session_id:     SESSION_ID,
            participant_id: participantId,
            name:           participantName,
            peer_id:        peer?.id
        });

        socket.disconnect();
        window.location.href = '/';
    }
}

window.addEventListener('beforeunload', () => {
    if (socket && participantId) {
        socket.emit('participant_leaving', {
            session_id:     SESSION_ID,
            participant_id: participantId,
            name:           participantName,
            peer_id:        peer?.id
        });
    }
});

function showError(msg) {
    const el         = document.getElementById('join-error');
    el.textContent   = msg;
    el.style.display = 'block';
}

// Auto-join if coming from admin dashboard link
window.addEventListener('DOMContentLoaded', () => {
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('admin') === 'true' && urlParams.get('name')) {
        joinSession();
    }
});