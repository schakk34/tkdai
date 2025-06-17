import cv2
import mediapipe as mp
import numpy as np
import json
import os
from pathlib import Path
from flask import current_app

def process_video_for_ideal_data(video_path, output_json_path):
    """
    Process a video to extract pose landmarks and save them as ideal data.
    
    Args:
        video_path: Path to the input video file
        output_json_path: Path where the JSON file will be saved
    """
    print(f"Processing video: {video_path}")
    
    # Initialize MediaPipe Pose
    mp_pose = mp.solutions.pose
    pose = mp_pose.Pose(
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5
    )
    
    # Open video
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        print(f"Error: Could not open video: {video_path}")
        return
    
    # Get video properties
    fps = cap.get(cv2.CAP_PROP_FPS)
    print(f"Video FPS: {fps}")
    
    # Store pose data
    pose_data = []
    frame_count = 0
    
    print("Processing frames...")
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        
        # Get timestamp
        timestamp = frame_count / fps
        
        # Process frame with MediaPipe
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = pose.process(frame_rgb)
        
        if results.pose_landmarks:
            # Convert landmarks to list of dictionaries
            landmarks = []
            for lm in results.pose_landmarks.landmark:
                landmarks.append({
                    'x': float(lm.x),
                    'y': float(lm.y),
                    'z': float(lm.z),
                    'visibility': float(lm.visibility)
                })
            
            # Add frame data
            pose_data.append({
                'timestamp': timestamp,
                'landmarks': landmarks
            })
        
        frame_count += 1
        if frame_count % 30 == 0:  # Print progress every 30 frames
            print(f"Processed {frame_count} frames...")
    
    # Release resources
    cap.release()
    
    # Save data to JSON
    output_data = {
        'pose_data': pose_data,
        'video_info': {
            'fps': fps,
            'total_frames': frame_count
        }
    }
    
    print(f"Saving data to {output_json_path}")
    with open(output_json_path, 'w') as f:
        json.dump(output_data, f)
    
    print("Processing complete!")
    print(f"Total frames processed: {frame_count}")
    print(f"Frames with pose data: {len(pose_data)}")

if __name__ == "__main__":
    # Get the static folder path
    static_folder = os.path.join(os.path.dirname(__file__), 'static')
    data_folder = os.path.join(static_folder, 'data', 'forms', 'pose_data')
    
    # Input and output paths
    video_path = os.path.join(data_folder, 'wt_koreo.mp4')
    output_path = os.path.join(data_folder, 'wt_koreo_ideal_data.json')
    
    # Process the video
    process_video_for_ideal_data(video_path, output_path) 