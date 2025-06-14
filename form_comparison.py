import cv2
import mediapipe as mp
import numpy as np
import json
from pathlib import Path
import time
from moviepy.editor import VideoFileClip, AudioFileClip, CompositeVideoClip, ImageSequenceClip
from mediapipe.framework.formats import landmark_pb2

class FormComparison:
    def __init__(self, ideal_data_path='koryo_ideal_data.json'):
        self.mp_pose = mp.solutions.pose
        self.pose = self.mp_pose.Pose(
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        self.mp_drawing = mp.solutions.drawing_utils
        
        # Load ideal pose data
        print(f"Loading ideal pose data from {ideal_data_path}...")
        with open(ideal_data_path, 'r') as f:
            self.ideal_data = json.load(f)
            
        # Print diagnostic information
        print(f"Loaded ideal pose data:")
        print(f"- Number of frames: {len(self.ideal_data['pose_data'])}")
        print(f"- First frame timestamp: {self.ideal_data['pose_data'][0]['timestamp']}")
        print(f"- Last frame timestamp: {self.ideal_data['pose_data'][-1]['timestamp']}")
        print(f"- Time duration: {self.ideal_data['pose_data'][-1]['timestamp'] - self.ideal_data['pose_data'][0]['timestamp']:.2f} seconds")
        
        # Drawing specifications
        self.ideal_drawing_spec = self.mp_drawing.DrawingSpec(
            color=(0, 255, 0),  # Green for ideal pose
            thickness=2,
            circle_radius=2
        )
        self.user_drawing_spec = self.mp_drawing.DrawingSpec(
            color=(0, 0, 255),  # Red for user pose
            thickness=2,
            circle_radius=2
        )
    
    def is_valid_point(self, x, y, frame_shape):
        """Check if a point is within the frame bounds."""
        return (0 <= x < frame_shape[1] and 0 <= y < frame_shape[0])
    
    def align_poses(self, user_landmarks, ideal_landmarks):
        """Align ideal pose with user's position and scale."""
        if not user_landmarks or not ideal_landmarks:
            return None
            
        # Get user's center point (using hips as reference)
        user_center = np.array([
            (user_landmarks[23]['x'] + user_landmarks[24]['x']) / 2,  # Average of left and right hip
            (user_landmarks[23]['y'] + user_landmarks[24]['y']) / 2
        ])
        
        # Get ideal pose center
        ideal_center = np.array([
            (ideal_landmarks[23]['x'] + ideal_landmarks[24]['x']) / 2,
            (ideal_landmarks[23]['y'] + ideal_landmarks[24]['y']) / 2
        ])
        
        # Calculate scale based on height (using nose to ankle distance)
        user_height = abs(user_landmarks[0]['y'] - user_landmarks[27]['y'])  # Nose to right ankle
        ideal_height = abs(ideal_landmarks[0]['y'] - ideal_landmarks[27]['y'])
        scale = user_height / ideal_height if ideal_height > 0 else 1.0
        
        # Create aligned ideal landmarks
        aligned_ideal = []
        for lm in ideal_landmarks:
            # Scale and translate the landmark
            aligned_x = (lm['x'] - ideal_center[0]) * scale + user_center[0]
            aligned_y = (lm['y'] - ideal_center[1]) * scale + user_center[1]
            aligned_z = lm['z'] * scale  # Scale depth as well
            
            aligned_ideal.append({
                'x': aligned_x,
                'y': aligned_y,
                'z': aligned_z,
                'visibility': lm['visibility']
            })
            
        return aligned_ideal
    
    def draw_landmarks(self, frame, landmarks, color):
        """Draw landmarks using OpenCV."""
        try:
            h, w = frame.shape[:2]
            
            # Draw points
            for landmark in landmarks:
                try:
                    x = int(landmark['x'] * w)
                    y = int(landmark['y'] * h)
                    
                    # Ensure coordinates are within bounds
                    x = max(0, min(x, w-1))
                    y = max(0, min(y, h-1))
                    
                    cv2.circle(frame, (x, y), 2, color, -1)
                except Exception as e:
                    print(f"Error drawing point: {str(e)}")
                    continue
            
            # Draw connections
            for connection in self.mp_pose.POSE_CONNECTIONS:
                try:
                    start_idx = connection[0]
                    end_idx = connection[1]
                    
                    if start_idx >= len(landmarks) or end_idx >= len(landmarks):
                        continue
                    
                    start_point = landmarks[start_idx]
                    end_point = landmarks[end_idx]
                    
                    start_x = int(start_point['x'] * w)
                    start_y = int(start_point['y'] * h)
                    end_x = int(end_point['x'] * w)
                    end_y = int(end_point['y'] * h)
                    
                    # Ensure coordinates are within bounds
                    start_x = max(0, min(start_x, w-1))
                    start_y = max(0, min(start_y, h-1))
                    end_x = max(0, min(end_x, w-1))
                    end_y = max(0, min(end_y, h-1))
                    
                    cv2.line(frame, (start_x, start_y), (end_x, end_y), color, 2)
                except Exception as e:
                    print(f"Error drawing connection: {str(e)}")
                    continue
        except Exception as e:
            print(f"Error in draw_landmarks: {str(e)}")
    
    def process_user_video(self, user_video_path, output_path, audio_path=None):
        """Process user video and create comparison visualization."""
        try:
            # First, get the total number of frames
            temp_cap = cv2.VideoCapture(str(user_video_path))
            total_frames = int(temp_cap.get(cv2.CAP_PROP_FRAME_COUNT))
            temp_cap.release()
            
            print(f"Input video has {total_frames} frames")
            
            cap = cv2.VideoCapture(str(user_video_path))
            if not cap.isOpened():
                print(f"❌ Error: Could not open user video: {user_video_path}")
                return False
                
            # Get video properties
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            
            print(f"Video properties: {width}x{height} @ {fps}fps")
            
            # Store processed frames
            processed_frames = []
            frame_count = 0
            ideal_frame_index = 0
            
            print("🔍 Processing user video...")
            
            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break
                
                # Process frame with MediaPipe
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = self.pose.process(frame_rgb)
                
                if results.pose_landmarks:
                    # Convert user landmarks to our format
                    user_landmarks = []
                    for lm in results.pose_landmarks.landmark:
                        user_landmarks.append({
                            'x': float(lm.x),
                            'y': float(lm.y),
                            'z': float(lm.z),
                            'visibility': float(lm.visibility)
                        })
                    
                    # Get corresponding ideal frame
                    if ideal_frame_index < len(self.ideal_data['pose_data']):
                        ideal_frame = self.ideal_data['pose_data'][ideal_frame_index]
                        ideal_landmarks = ideal_frame['landmarks']
                        
                        # Align ideal pose with user
                        aligned_ideal = self.align_poses(user_landmarks, ideal_landmarks)
                        
                        if aligned_ideal:
                            # Draw user pose in red
                            self.mp_drawing.draw_landmarks(
                                frame,
                                results.pose_landmarks,
                                self.mp_pose.POSE_CONNECTIONS,
                                self.user_drawing_spec
                            )
                            
                            # Create MediaPipe landmarks for aligned ideal pose
                            ideal_landmarks_mp = landmark_pb2.NormalizedLandmarkList()
                            for lm in aligned_ideal:
                                landmark = ideal_landmarks_mp.landmark.add()
                                landmark.x = lm['x']
                                landmark.y = lm['y']
                                landmark.z = lm['z']
                                landmark.visibility = lm['visibility']
                            
                            # Draw aligned ideal pose in green
                            self.mp_drawing.draw_landmarks(
                                frame,
                                ideal_landmarks_mp,
                                self.mp_pose.POSE_CONNECTIONS,
                                self.ideal_drawing_spec
                            )
                            
                            # Update ideal frame index
                            ideal_frame_index = (ideal_frame_index + 1) % len(self.ideal_data['pose_data'])
                
                # Add frame number
                cv2.putText(frame, f"Frame: {frame_count}", (10, 30),
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                
                # Convert frame to RGB for MoviePy
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                processed_frames.append(frame_rgb)
                
                frame_count += 1
                
                # Show progress
                if frame_count % 30 == 0:  # Show every 30 frames
                    progress = (frame_count / total_frames) * 100
                    print(f"Progress: {progress:.1f}% ({frame_count}/{total_frames} frames)")
            
            cap.release()
            
            print(f"Processed {frame_count} frames")
            
            if not processed_frames:
                print("No frames were processed successfully")
                return False
            
            # Create video from processed frames
            print("Creating video from processed frames...")
            clip = ImageSequenceClip(processed_frames, fps=fps)
            
            # Add audio if provided
            if audio_path and Path(audio_path).exists():
                print("🎵 Adding audio track...")
                audio = AudioFileClip(audio_path)
                
                # Trim audio to match video length if needed
                if audio.duration > clip.duration:
                    audio = audio.subclip(0, clip.duration)
                
                # Combine video and audio
                clip = clip.set_audio(audio)
            
            # Write the final video
            print("Writing final video...")
            clip.write_videofile(
                output_path,
                codec='libx264',
                audio_codec='aac' if audio_path else None
            )
            
            # Clean up
            clip.close()
            if audio_path and Path(audio_path).exists():
                audio.close()
            
            print(f"✅ Comparison video saved to {output_path}")
            return True
            
        except Exception as e:
            print(f"Error processing video: {str(e)}")
            return False

def main():
    print("\n=== Starting Form Comparison ===")
    print("Initializing FormComparison class...")
    comparator = FormComparison()
    print("\n=== Processing Video ===")
    comparator.process_user_video(
        user_video_path='static/user_koryo.mp4',
        output_path='static/comparison_output.mp4',
        audio_path='static/koryo_rhythm.mp3'
    )
    print("\n=== Done ===")

if __name__ == "__main__":
    main() 