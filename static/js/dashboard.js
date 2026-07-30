
        const socket = io();
        const participants = {};

        socket.emit('admin_join', { session_id: SESSION_ID });

        // ── SOCKET LISTENERS ───────────────────────────────────────────

        socket.on('session_snapshot', (data) => {
            for (const [pid, info] of Object.entries(data.participants)) {
                participants[pid] = { ...info, engagement: 'Unknown' };
            }
            renderParticipants();

            for (const event of data.recent_events) {
                appendEvent(event);
            }
        });

        socket.on('participant_joined', (data) => {
            participants[data.participant_id] = {
                name: data.name,
                engagement: 'Connecting...',
                muted: false
            };
            document.getElementById('participant-count').textContent = Object.keys(participants).length;
            renderParticipants();
        });

        socket.on('participant_status', (data) => {
            if (participants[data.participant_id]) {
                participants[data.participant_id].engagement = data.engagement;
                participants[data.participant_id].pitch = data.pitch;
                participants[data.participant_id].yaw = data.yaw;
                renderParticipants();
            }
        });

        socket.on('new_event', (event) => {
            if (participants[event.participant_id]) {
                participants[event.participant_id].last_event = event.event_type;
                renderParticipants();
            }
            appendEvent(event);
        });

        socket.on('live_transcript', (data) => {
            const box = document.getElementById('transcript-box');
            
            // Remove placeholder
            const placeholder = box.querySelector('p[style*="color:#666"]');
            if (placeholder) placeholder.remove();
            
            const p = document.createElement('p');
            p.style.marginBottom = '8px';
            
            if (data.is_admin) {
                p.style.borderLeft = '3px solid #4CAF50';
                p.style.paddingLeft = '10px';
                p.style.background = '#1a2a1a';
                p.style.padding = '8px';
                p.style.borderRadius = '4px';
            }
            
            p.innerHTML = `
                <span style="color:#aaa">[${data.timestamp}]</span> 
                <strong style="color: ${data.is_admin ? '#4CAF50' : '#2196F3'};">
                    ${data.name}${data.is_admin ? ' (You)' : ''}:
                </strong> 
                ${data.text}
            `;
            
            box.insertBefore(p, box.firstChild);
            
            // Keep only last 20 messages
            while (box.children.length > 20) {
                box.removeChild(box.lastChild);
            }
        });

        socket.on('participant_left', (data) => {
            console.log('Participant left:', data);
            
            if (participants[data.participant_id]) {
                participants[data.participant_id].engagement = 'Left Session';
                renderParticipants();
            }

        socket.on('mute_status', (data) => {
            if (participants[data.participant_id]) {
                participants[data.participant_id].muted = data.muted;
                renderParticipants();
            }
        });
            
            const log = document.getElementById('event-log');
            const div = document.createElement('div');
            div.className = 'event-row';
            div.style.borderLeft = '3px solid #999';
            div.style.paddingLeft = '10px';
            div.innerHTML = `
                <strong>${new Date().toLocaleTimeString()}</strong> 
                <span style="color: #999;">📤 ${data.name} left the session</span>
            `;
            log.insertBefore(div, log.firstChild);
            
            alert(`${data.name} has left the session`);
        });

        // ── RENDER PARTICIPANTS ────────────────────────────────────────

        function renderParticipants() {
            const grid = document.getElementById('participants-grid');
            grid.innerHTML = '';

            if (Object.keys(participants).length === 0) {
                grid.innerHTML = '<p style="color: #666;">Waiting for participants to join...</p>';
                document.getElementById('participant-count').textContent = '0';
                return;
            }

            document.getElementById('participant-count').textContent = Object.keys(participants).length;

            for (const [pid, p] of Object.entries(participants)) {
                const card = document.createElement('div');
                const eng = p.engagement || 'Unknown';
                
                const hasLeft = eng === 'Left Session';
                const cardClass = hasLeft ? 'card-left' : 
                                  eng === 'Focused' ? 'card-engaged' :
                                  eng === 'Distracted' ? 'card-distracted' : '';
                const badgeClass = hasLeft ? 'badge-left' :
                                  eng === 'Focused' ? 'badge-engaged' : 'badge-distracted';

                card.className = `participant-card ${cardClass}`;
                card.id = `card-${pid}`;
                card.innerHTML = `
                    <h3 style="margin:0 0 5px 0">${p.name} ${hasLeft ? '(Left)' : ''}</h3>
                    <span class="engagement-badge ${badgeClass}">${eng}</span>
                    <div style="font-size: 11px; color: #666; margin-top: 8px;">
                        ${hasLeft ? 'No longer in session' : `Pitch: ${p.pitch || '-'}° | Yaw: ${p.yaw || '-'}°`}
                    </div>
                    
                    ${!hasLeft ? `
                        <div class="mute-control">
                            <button onclick="toggleParticipantMute('${pid}', '${p.name}')" 
                                    id="mute-btn-${pid}"
                                    style="background: ${p.muted ? '#4CAF50' : '#DC3545'};">
                                ${p.muted ? '🔇 Muted' : '🔊 Can Speak'}
                            </button>
                        </div>
                    ` : ''}
                `;
                grid.appendChild(card);
            }
        }

        // ── CONTROL FUNCTIONS ──────────────────────────────────────────

        function toggleParticipantMute(participantId, participantName) {
            const currentStatus = participants[participantId].muted || false;
            const newStatus = !currentStatus;
            
            participants[participantId].muted = newStatus;
            
            socket.emit('toggle_participant_mute', {
                session_id: SESSION_ID,
                participant_id: participantId,
                muted: newStatus
            });
            
            const btn = document.getElementById(`mute-btn-${participantId}`);
            if (btn) {
                btn.style.background = newStatus ? '#4CAF50' : '#DC3545';
                btn.textContent = newStatus ? '🔇 Muted' : '🔊 Can Speak';
            }
            
            console.log(`${participantName} has been ${newStatus ? 'muted' : 'unmuted'}`);
        }

        function muteAllParticipants() {
            for (const pid in participants) {
                if (participants[pid].engagement !== 'Left Session') {
                    participants[pid].muted = true;
                    socket.emit('toggle_participant_mute', {
                        session_id: SESSION_ID,
                        participant_id: pid,
                        muted: true
                    });
                }
            }
            renderParticipants();
            alert('All participants have been muted');
        }

        function unmuteAllParticipants() {
            for (const pid in participants) {
                if (participants[pid].engagement !== 'Left Session') {
                    participants[pid].muted = false;
                    socket.emit('toggle_participant_mute', {
                        session_id: SESSION_ID,
                        participant_id: pid,
                        muted: false
                    });
                }
            }
            renderParticipants();
            alert('All participants have been unmuted');
        }

        function joinAsParticipant() {
            // Get admin's name
            const joinUrl = `${window.location.origin}/join/${SESSION_ID}?name=${encodeURIComponent(ADMIN_NAME)}&admin=true`;
            window.open(joinUrl, '_blank');
        }

        async function endSession() {
            if (!confirm('End session and generate report?')) return;

            const response = await fetch(`/end_session/${SESSION_ID}`, { method: 'POST' });
            const data = await response.json();

            if (data.status === 'ended') {
                window.location.href = `/report/${SESSION_ID}`;
            }
        }

        // ── APPEND EVENT TO LOG ────────────────────────────────────────

        function appendEvent(event) {
            const log = document.getElementById('event-log');

            const placeholder = log.querySelector('p');
            if (placeholder) placeholder.remove();

            const div = document.createElement('div');
            const cssClass = event.event_type === 'Attention' ? 'event-attention' :
                             event.event_type === 'Fatigue' ? 'event-fatigue' :
                             event.event_type === 'Hand Motion' ? 'event-hand' : 'event-distracted';

            div.className = `event-row ${cssClass}`;
            div.innerHTML = `
                <strong>${event.timestamp}</strong> 
                [${event.participant_name}] 
                ${event.event_type}: ${event.description}
                ${event.speech_context ? `<br><span style="color:#888; font-size:12px;">Context: "${event.speech_context}"</span>` : ''}
            `;
            log.insertBefore(div, log.firstChild);
        }