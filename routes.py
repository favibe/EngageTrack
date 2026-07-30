import os
import uuid
from flask import render_template, request, jsonify, send_file
from datetime import datetime
from database import get_session, get_all_sessions, save_session
from config import OUTPUT_DIR
from utils import save_csv, generate_pdf_transcript, generate_pdf_logs, generate_engagement_graphs
from events import sessions, session_logs, transcriptions


def register_routes(app, socketio):  # ← receives socketio, no circular import


    @app.route('/')
    def index():
        return render_template('index.html')


    @app.route('/create_session', methods=['POST'])
    def create_session():
        data       = request.get_json()
        session_id = str(uuid.uuid4())[:6].upper()

        sessions[session_id] = {
            'admin_name':   data.get('admin_name',   'Admin'),
            'session_name': data.get('session_name', 'Untitled Session'),
            'created_at':   datetime.now().isoformat(),
            'participants': {},
            'status':       'active'
        }
        session_logs[session_id]   = []
        transcriptions[session_id] = []

        return jsonify({
            'session_id':    session_id,
            'join_url':      f"{request.host_url}join/{session_id}",
            'dashboard_url': f"{request.host_url}dashboard/{session_id}"
        })


    @app.route('/join/<session_id>')
    def join_page(session_id):
        if session_id not in sessions:
            return "Invalid or expired session.", 404
        return render_template('participant.html',
                               session_id=session_id,
                               session_name=sessions[session_id]['session_name'],
                               session_info=sessions[session_id])


    @app.route('/dashboard/<session_id>')
    def dashboard(session_id):
        if session_id not in sessions:
            return "Session not found.", 404
        return render_template('dashboard.html',
                               session_id=session_id,
                               session_info=sessions[session_id])


    @app.route('/end_session/<session_id>', methods=['POST'])
    def end_session(session_id):
        if session_id not in sessions:
            return jsonify({'error': 'Session not found'}), 404

        sessions[session_id]['status'] = 'ended'
        logs  = session_logs.get(session_id, [])
        trans = transcriptions.get(session_id, [])

        events_for_pdf = [
            (e['timestamp'], e['event_type'], e['description'], e['speech_context'])
            for e in logs
        ]

        save_csv(
            os.path.join(OUTPUT_DIR, f"{session_id}_engagement_log.csv"),
            events_for_pdf,
            ["Timestamp", "EventType", "Description", "SpeechContext"]
        )
        save_csv(
            os.path.join(OUTPUT_DIR, f"{session_id}_transcription.csv"),
            trans,
            ["Timestamp", "Transcription"]
        )

        try:
            generate_pdf_logs(events_for_pdf)
            generate_pdf_transcript(trans)
            generate_engagement_graphs(events_for_pdf)
        except Exception as e:
            print(f"Report generation error: {e}")

        save_session(session_id, sessions[session_id], logs, trans)

        # Use the socketio passed into register_routes — no circular import
        socketio.emit('session_ended', {'redirect': '/'}, room=session_id)

        return jsonify({'status': 'ended', 'redirect': f'/report/{session_id}'})


    @app.route('/report/<session_id>')
    def report(session_id):
        if session_id in sessions:
            logs         = session_logs.get(session_id, [])
            participants = sessions[session_id]['participants']
            session_info = sessions[session_id]
        else:
            session_data = get_session(session_id)
            if not session_data:
                return "Session not found.", 404
            logs         = session_data['events']
            participants = session_data['participants']
            session_info = session_data

        summary = {}
        for pid, pinfo in participants.items():
            p_logs = [l for l in logs if l['participant_id'] == pid]
            summary[pid] = {
                'name':              pinfo['name'],
                'distraction_count': len([l for l in p_logs if 'Distract' in l['description']]),
                'fatigue_count':     len([l for l in p_logs if l['event_type'] == 'Fatigue']),
                'hand_count':        len([l for l in p_logs if l['event_type'] == 'Hand Motion']),
                'events':            p_logs
            }

        return render_template('report.html',
                               session_id=session_id,
                               session_info=session_info,
                               summary=summary,
                               all_events=logs)


    @app.route('/history')
    def session_history():
        return render_template('history.html', sessions=get_all_sessions())


    @app.route('/download/<session_id>/engagement_log')
    def download_engagement_log(session_id):
        path = os.path.join(OUTPUT_DIR, f"{session_id}_engagement_log.csv")
        if os.path.exists(path):
            return send_file(path, as_attachment=True)
        return "File not found.", 404

    @app.route('/download/<session_id>/transcription')
    def download_transcription(session_id):
        path = os.path.join(OUTPUT_DIR, f"{session_id}_transcription.csv")
        if os.path.exists(path):
            return send_file(path, as_attachment=True)
        return "File not found.", 404

    @app.route('/download/<session_id>/engagement_pdf')
    def download_engagement_pdf(session_id):
        path = os.path.join(OUTPUT_DIR, "engagement_log_summary.pdf")
        if os.path.exists(path):
            return send_file(path, as_attachment=True)
        return "PDF not found.", 404

    @app.route('/download/<session_id>/transcription_pdf')
    def download_transcription_pdf(session_id):
        path = os.path.join(OUTPUT_DIR, "transcription_summary.pdf")
        if os.path.exists(path):
            return send_file(path, as_attachment=True)
        return "PDF not found.", 404

    @app.route('/download/<session_id>/graphs/<graph_name>')
    def download_graph(session_id, graph_name):
        path = os.path.join(OUTPUT_DIR, f"{graph_name}.png")
        if os.path.exists(path):
            return send_file(path, as_attachment=True)
        return "Graph not found.", 404