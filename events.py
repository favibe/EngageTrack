import uuid
import time
import cv2
import numpy as np
from datetime import datetime
from flask import request
from flask_socketio import emit, join_room

from engagement_logic import EngagementLogic
from utils import (
    get_eye_aspect_ratio,
    get_mouth_aspect_ratio,
    get_head_pose,
    timestamp
)
from config import (
    ATTENTION_YAW_THRESHOLD,
    PITCH_FOCUSED_MIN_ABS_THRESHOLD,
    HAND_RAISE_Y_THRESHOLD_FACTOR
)

# ── SHARED STATE ──────────────────────────────────────────────────────────────
sessions         = {}
session_logs     = {}
transcriptions   = {}
logics           = {}
last_transcripts = {}


def make_logger(socketio, session_id, participant_id, participant_name):
    def logger(event_type, description, timestamp=None):
        timestamp_float = timestamp if timestamp is not None else time.time()
        ts_str  = datetime.fromtimestamp(timestamp_float).strftime("%H:%M:%S")
        speech  = last_transcripts.get(participant_id, "")

        event = {
            "timestamp":        ts_str,
            "event_type":       event_type,
            "description":      description,
            "speech_context":   speech,
            "participant_id":   participant_id,
            "participant_name": participant_name
        }

        session_logs[session_id].append(event)
        socketio.emit('new_event', event, room=session_id)

    return logger


def register_events(socketio):

    @socketio.on('join_session')
    def handle_join(data):
        session_id = data['session_id']
        name       = data['name'].strip()

        if session_id not in sessions:
            emit('error', {'message': 'Invalid session ID'})
            return

        participant_id = str(uuid.uuid4())[:8]

        sessions[session_id]['participants'][participant_id] = {
            'name':      name,
            'joined_at': datetime.now().isoformat(),
            'status':    'active',
            'peer_id':   None,
            'muted':     False
        }

        logic_key         = f"{session_id}_{participant_id}"
        logics[logic_key] = EngagementLogic(
            make_logger(socketio, session_id, participant_id, name)
        )
        last_transcripts[participant_id] = ""

        join_room(session_id)

        emit('joined', {
            'participant_id': participant_id,
            'name':           name,
            'message':        f'Welcome {name}!'
        })


    @socketio.on('peer_ready')
    def handle_peer_ready(data):
        session_id     = data['session_id']
        participant_id = data['participant_id']
        peer_id        = data['peer_id']
        name           = data['name']

        if session_id not in sessions: return
        if participant_id not in sessions[session_id]['participants']: return

        sessions[session_id]['participants'][participant_id]['peer_id'] = peer_id

        # Send existing participants to the new joiner
        existing = [
            {'participant_id': pid, 'peer_id': p['peer_id'], 'name': p['name']}
            for pid, p in sessions[session_id]['participants'].items()
            if pid != participant_id and p.get('peer_id')
        ]
        emit('existing_participants', existing)

        # Tell everyone else about the new joiner
        emit('participant_joined', {
            'participant_id': participant_id,
            'peer_id':        peer_id,
            'name':           name
        }, room=session_id, include_self=False)


    @socketio.on('landmarks_data')
    def handle_landmarks(data):
        session_id     = data['session_id']
        participant_id = data['participant_id']
        logic_key      = f"{session_id}_{participant_id}"

        if logic_key not in logics: return

        logic          = logics[logic_key]
        face_landmarks = data.get('face_landmarks')
        hand_landmarks = data.get('hand_landmarks')

        if face_landmarks and len(face_landmarks) >= 468:

            class LM:
                def __init__(self, d):
                    self.x, self.y, self.z = d['x'], d['y'], d['z']

            lm   = [LM(p) for p in face_landmarks]
            W, H = 640, 480

            def coords(idxs):
                return [(int(lm[i].x * W), int(lm[i].y * H)) for i in idxs]

            ear = (get_eye_aspect_ratio(coords([362,385,387,263,373,380])) +
                   get_eye_aspect_ratio(coords([33,160,158,133,153,144]))) / 2.0
            mar =  get_mouth_aspect_ratio(coords([61,81,13,311,402,14]))

            try:
                pitch, yaw, roll = get_head_pose(lm, (H, W, 3))
            except Exception:
                pitch, yaw, roll = 0, 0, 0

            logic.detect_and_register_blink(ear)
            logic.detect_and_register_yawn(mar)

            is_focused = (abs(yaw)   <= ATTENTION_YAW_THRESHOLD and
                          abs(pitch) >= PITCH_FOCUSED_MIN_ABS_THRESHOLD)
            logic.update_attention(is_focused, pitch, yaw)

            engagement = "Focused" if is_focused else "Distracted"

            emit('status_update', {
                'engagement': engagement,
                'ear':        round(ear,   3),
                'mar':        round(mar,   3),
                'pitch':      round(pitch, 1),
                'yaw':        round(yaw,   1)
            })

            emit('participant_status', {
                'participant_id': participant_id,
                'engagement':     engagement,
                'pitch':          round(pitch, 1),
                'yaw':            round(yaw,   1)
            }, room=session_id)

        # ── HAND — only process when a hand is actually detected ──────────────
        # Previously this called register_hand_event even with no hand visible
        # which caused continuous "Hand Detected" spam in the event log
        if hand_landmarks:
            wrist_y = hand_landmarks[0]['y']
            eye_y   = ((face_landmarks[33]['y'] + face_landmarks[263]['y']) / 2
                       if face_landmarks else 0.5)
            is_hand_raised = wrist_y < eye_y * HAND_RAISE_Y_THRESHOLD_FACTOR
            hand_std       = abs(wrist_y - 0.5)
            logic.register_hand_event(is_hand_raised, hand_std)
        # If no hand visible — do nothing, no event logged


    @socketio.on('transcript_update')
    def handle_transcript(data):
        session_id     = data['session_id']
        participant_id = data['participant_id']
        text           = data.get('text', '').strip()
        is_admin       = data.get('is_admin', False)
        speaker_name   = data.get('name', '?')

        # Debug — check Flask terminal to confirm who is sending transcripts
        print(f">>> TRANSCRIPT from '{speaker_name}' "
              f"(pid:{participant_id}, admin:{is_admin}): {text}")

        if not text: return

        last_transcripts[participant_id] = text
        ts = timestamp()

        transcriptions[session_id].append((ts, f"[{speaker_name}] {text}"))

        emit('live_transcript', {
            'participant_id': participant_id,
            'name':           speaker_name,
            'text':           text,
            'timestamp':      ts,
            'is_admin':       is_admin
        }, room=session_id)


    @socketio.on('admin_join')
    def handle_admin_join(data):
        session_id = data['session_id']
        join_room(session_id)
        emit('session_snapshot', {
            'participants':  sessions.get(session_id, {}).get('participants', {}),
            'recent_events': session_logs.get(session_id, [])[-30:]
        })


    @socketio.on('toggle_participant_mute')
    def handle_toggle_mute(data):
        session_id     = data['session_id']
        participant_id = data['participant_id']

        if session_id not in sessions: return
        if participant_id not in sessions[session_id]['participants']: return

        current   = sessions[session_id]['participants'][participant_id].get('muted', False)
        new_muted = not current
        sessions[session_id]['participants'][participant_id]['muted'] = new_muted

        # Emit to whole room — participant.js filters by participant_id
        emit('mute_status', {
            'participant_id': participant_id,
            'muted':          new_muted
        }, room=session_id)


    @socketio.on('participant_leaving')
    def handle_participant_leaving(data):
        session_id     = data['session_id']
        participant_id = data['participant_id']
        name           = data.get('name', 'Unknown')
        peer_id        = data.get('peer_id')

        if session_id not in sessions: return
        if participant_id not in sessions[session_id]['participants']: return

        sessions[session_id]['participants'][participant_id].update({
            'status':  'left',
            'left_at': datetime.now().isoformat()
        })

        emit('participant_left', {
            'participant_id': participant_id,
            'peer_id':        peer_id,
            'name':           name
        }, room=session_id)