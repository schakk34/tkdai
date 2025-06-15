import cv2
import mediapipe as mp
import numpy as np
import json
from pathlib import Path
import time

class KoryoDataExtractor:
    def __init__(self, video_path):
        self.video_path = video_path
        self.mp_pose = mp.solutions.pose
        self.pose = self.mp_pose.Pose(
            static_image_mode=False,
            model_complexity=2,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        
    def process_video(self):
        cap = cv2.VideoCapture(str(self.video_path))
        if not cap.isOpened():
            print(f"Error: Could not open video file {self.video_path}")
            return False
            
        frame_count = 0
        pose_data = []
        fps = cap.get(cv2.CAP_PROP_FPS)
        print(f"Video FPS: {fps}")
        
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
                
            # Convert BGR to RGB
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Process frame
            results = self.pose.process(frame_rgb)
            
            if results.pose_landmarks:
                # Extract landmarks
                landmarks = []
                for landmark in results.pose_landmarks.landmark:
                    landmarks.append({
                        'x': landmark.x,
                        'y': landmark.y,
                        'z': landmark.z,
                        'visibility': landmark.visibility
                    })
                
                # Store frame data
                pose_data.append({
                    'frame': frame_count,
                    'timestamp': frame_count / fps,
                    'landmarks': landmarks
                })
            
            frame_count += 1
            
            # Show progress
            if frame_count % 30 == 0:  # Show every 30 frames
                print(f"Processed {frame_count} frames...")
        
        cap.release()
        
        # Save data
        output_data = {
            'video_metadata': {
                'filename': str(self.video_path),
                'total_frames': frame_count,
                'fps': fps,
                'extraction_date': time.strftime('%Y-%m-%d %H:%M:%S')
            },
            'pose_data': pose_data
        }
        
        self.save_data(output_data)
        print(f"Total frames processed: {frame_count}")
        print(f"Total pose data frames: {len(pose_data)}")
        return True
        
    def save_data(self, data):
        output_path = Path('static/koryo_ideal_data.json')
        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"Saved pose data to {output_path}")

def main():
    video_path = Path('static/koreoideal.mp4')
    if not video_path.exists():
        print(f"Error: Video file not found at {video_path}")
        return
        
    extractor = KoryoDataExtractor(video_path)
    if extractor.process_video():
        print("Successfully processed video and extracted pose data")
    else:
        print("Failed to process video")

if __name__ == '__main__':
    main() 