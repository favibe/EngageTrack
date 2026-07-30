# utils.py

import os
import csv
from datetime import datetime
import math
import numpy as np
import cv2
from fpdf import FPDF
import matplotlib
matplotlib.use('Agg') # Use non-interactive backend for matplotlib
import matplotlib.pyplot as plt # Import matplotlib for plotting

# Import OUTPUT_DIR from config
from config import OUTPUT_DIR

def timestamp():
    """Returns current time in HH:MM:SS format."""
    return datetime.now().strftime("%H:%M:%S")

def save_csv(filename, rows, headers):
    """Saves data to a CSV file with given headers."""
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

def generate_pdf_transcript(transcriptions):
    """Generates a PDF of all transcriptions."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", size=12)
    pdf.multi_cell(0, 10, "Lecture Transcriptions\n\n")
    pdf.set_left_margin(10)
    pdf.set_right_margin(10)
    page_width = pdf.w - pdf.l_margin - pdf.r_margin

    for ts, text in transcriptions:
        if text.strip():
            pdf.multi_cell(page_width, 12, f"[{ts}] {text}")
            pdf.ln(5)
        else:
            pdf.multi_cell(page_width, 12, f"[{ts}] (No speech detected)")
            pdf.ln(5)
    pdf.output(os.path.join(OUTPUT_DIR, "transcription_summary.pdf"))

def generate_pdf_logs(events):
    """Generates a PDF summary of all logged events."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", size=12)
    pdf.multi_cell(0, 10, "Engagement Log Summary\n\n")
    pdf.set_left_margin(10)
    pdf.set_right_margin(10)
    page_width = pdf.w - pdf.l_margin - pdf.r_margin

    for ts, event_type, description, speech_context in events:
        log_entry = f"[{ts}] {event_type}: {description}"
        if speech_context:
            log_entry += f"\n    Speech Context: \"{speech_context}\""
        if log_entry.strip():
            pdf.multi_cell(page_width, 12, log_entry)
            pdf.ln(5)
        else:
            pdf.multi_cell(page_width, 12, f"[{ts}] (Empty Log Entry)")
            pdf.ln(5)
    pdf.output(os.path.join(OUTPUT_DIR, "engagement_log_summary.pdf"))

def generate_engagement_graphs(events):
    """
    Generates and saves graphs for attention, fatigue, and hand motion.
    """
    # Parse event data for plotting
    attention_data = [] # (datetime_obj, is_focused_int)
    fatigue_yawns = []  # (datetime_obj)
    fatigue_blinks = [] # (datetime_obj)
    hand_raised = []    # (datetime_obj)
    hand_detected = []  # (datetime_obj)

    for ts_str, event_type, description, _ in events:
        # Convert timestamp string to datetime object
        dt_obj = datetime.strptime(ts_str, "%H:%M:%S").time() # Get time object
        # To plot, we need a full datetime object, so we'll use a dummy date
        dummy_date = datetime(2000, 1, 1)
        full_dt_obj = datetime.combine(dummy_date, dt_obj)

        if event_type == "Attention":
            is_focused = 1 if description == "Focused" else 0
            attention_data.append((full_dt_obj, is_focused))
        elif event_type == "Fatigue":
            if "Yawning" in description:
                fatigue_yawns.append(full_dt_obj)
            elif "Blink" in description:
                fatigue_blinks.append(full_dt_obj)
        elif event_type == "Hand Motion":
            if "Hand Raised" in description:
                hand_raised.append(full_dt_obj)
            elif "Hand Detected" in description:
                hand_detected.append(full_dt_obj)

    # --- Plotting Attention Over Time ---
    if attention_data:
        times = [item[0] for item in attention_data]
        states = [item[1] for item in attention_data]

        plt.figure(figsize=(12, 6))
        plt.step(times, states, where='post', color='green', label='Focused')
        
        # Highlight distracted periods
        distracted_times = [t for t, s in attention_data if s == 0]
        distracted_states = [s for t, s in attention_data if s == 0]
        
        # Iterate through attention data to find segments of distraction
        distraction_segments = []
        start_distraction = None
        for i in range(len(attention_data)):
            current_time, current_state = attention_data[i]
            if current_state == 0 and start_distraction is None:
                start_distraction = current_time
            elif current_state == 1 and start_distraction is not None:
                distraction_segments.append((start_distraction, current_time))
                start_distraction = None
        # If distraction extends to the end of the session
        if start_distraction is not None:
            distraction_segments.append((start_distraction, times[-1]))

        for start, end in distraction_segments:
            plt.axvspan(start, end, color='red', alpha=0.2, label='Distracted' if start == distraction_segments[0][0] else "") # Label only once

        plt.title('Student Attention Over Time')
        plt.xlabel('Time')
        plt.ylabel('Attention State (1=Focused, 0=Distracted)')
        plt.yticks([0, 1], ['Distracted', 'Focused'])
        plt.grid(True, linestyle='--', alpha=0.7)
        plt.legend()
        plt.tight_layout()
        plt.savefig(os.path.join(OUTPUT_DIR, "attention_over_time.png"))
        plt.close()

    # --- Plotting Fatigue Events ---
    if fatigue_yawns or fatigue_blinks:
        plt.figure(figsize=(12, 4))
        if fatigue_yawns:
            plt.scatter(fatigue_yawns, [1] * len(fatigue_yawns), color='orange', marker='o', label='Yawn Detected')
        if fatigue_blinks:
            plt.scatter(fatigue_blinks, [0] * len(fatigue_blinks), color='purple', marker='x', label='Blink Fatigue')
        
        plt.title('Fatigue Events Over Time')
        plt.xlabel('Time')
        plt.ylabel('Event Type')
        plt.yticks([0, 1], ['Blink Fatigue', 'Yawn Detected'])
        plt.grid(True, linestyle='--', alpha=0.7)
        plt.legend()
        plt.tight_layout()
        plt.savefig(os.path.join(OUTPUT_DIR, "fatigue_events.png"))
        plt.close()

    # --- Plotting Hand Motion Events ---
    if hand_raised or hand_detected:
        plt.figure(figsize=(12, 4))
        if hand_raised:
            plt.scatter(hand_raised, [1] * len(hand_raised), color='blue', marker='^', label='Hand Raised')
        if hand_detected:
            plt.scatter(hand_detected, [0] * len(hand_detected), color='cyan', marker='s', label='Hand Detected (Frequent)')
        
        plt.title('Hand Motion Events Over Time')
        plt.xlabel('Time')
        plt.ylabel('Event Type')
        plt.yticks([0, 1], ['Hand Detected', 'Hand Raised'])
        plt.grid(True, linestyle='--', alpha=0.7)
        plt.legend()
        plt.tight_layout()
        plt.savefig(os.path.join(OUTPUT_DIR, "hand_motion_events.png"))
        plt.close()


# ========== FACIAL LANDMARK UTILITIES ==========
def euclidean_distance(p1, p2):
    """Calculates Euclidean distance between two 2D points."""
    return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)

def get_eye_aspect_ratio(eye_landmarks):
    """Calculates EAR for a single eye given 6 landmarks."""
    # Vertical distances
    A = euclidean_distance(eye_landmarks[1], eye_landmarks[5])
    B = euclidean_distance(eye_landmarks[2], eye_landmarks[4])
    # Horizontal distance
    C = euclidean_distance(eye_landmarks[0], eye_landmarks[3])
    return (A + B) / (2.0 * C) if C != 0 else 0

def get_mouth_aspect_ratio(mouth_landmarks):
    """Calculates MAR for the mouth given 6 landmarks."""
    # Vertical distances
    A = euclidean_distance(mouth_landmarks[1], mouth_landmarks[5])
    B = euclidean_distance(mouth_landmarks[2], mouth_landmarks[4])
    # Horizontal distance
    C = euclidean_distance(mouth_landmarks[0], mouth_landmarks[3])
    return (A + B) / (2.0 * C) if C != 0 else 0

def get_head_pose(face_landmarks, image_shape):
    """
    Estimates head pose (pitch, yaw, roll) from face landmarks.
    Returns angles in degrees.
    """
    img_h, img_w, _ = image_shape
    # 2D image points from MediaPipe (normalized to image size)
    # Using specific landmarks for pose estimation
    # Nose tip, Chin, Left eye corner, Right eye corner, Left mouth corner, Right mouth corner
    image_points = np.array([
        (face_landmarks[1].x * img_w, face_landmarks[1].y * img_h),    # Nose tip
        (face_landmarks[152].x * img_w, face_landmarks[152].y * img_h), # Chin
        (face_landmarks[33].x * img_w, face_landmarks[33].y * img_h),   # Left eye corner
        (face_landmarks[263].x * img_w, face_landmarks[263].y * img_h), # Right eye corner
        (face_landmarks[61].x * img_w, face_landmarks[61].y * img_h),   # Left mouth corner
        (face_landmarks[291].x * img_w, face_landmarks[291].y * img_h)  # Right mouth corner
    ], dtype="double")

    # 3D model points (arbitrary but consistent model of a human head)
    model_points = np.array([
        (0.0, 0.0, 0.0),             # Nose tip
        (0.0, -330.0, -65.0),        # Chin
        (-225.0, 170.0, -135.0),     # Left eye corner
        (225.0, 170.0, -135.0),      # Right eye corner
        (-150.0, -150.0, -125.0),    # Left mouth corner
        (150.0, -150.0, -125.0)      # Right mouth corner
    ])

    # Camera internals (assuming a generic webcam)
    focal_length = img_w
    center = (img_w / 2, img_h / 2)
    camera_matrix = np.array([
        [focal_length, 0, center[0]],
        [0, focal_length, center[1]],
        [0, 0, 1]
    ], dtype="double")

    dist_coeffs = np.zeros((4, 1)) # No distortion assumed

    # Solve for pose
    (success, rotation_vector, translation_vector) = cv2.solvePnP(
        model_points, image_points, camera_matrix, dist_coeffs, flags=cv2.SOLVEPNP_ITERATIVE)

    # Convert rotation vector to rotation matrix
    rmat, jacobian = cv2.Rodrigues(rotation_vector)

    # Get angles
    angles, mtxR, mtxQ, Qx, Qy, Qz = cv2.RQDecomp3x3(rmat)
    
    x = angles[0] # Pitch
    y = angles[1] # Yaw
    z = angles[2] # Roll

    return x, y, z # Pitch, Yaw, Roll in degrees
