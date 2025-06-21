import cv2
import mediapipe as mp
import numpy as np
import json
import os
from pathlib import Path
import subprocess
import time
from moviepy.editor import VideoFileClip, AudioFileClip, CompositeVideoClip, ImageSequenceClip
from mediapipe.framework.formats import landmark_pb2
from utils.form_utils.metrics import joint_errors, angle_errors, build_feature_vector
from flask import current_app

_mp_pose = mp.solutions.pose.Pose(min_detection_confidence=0.5, min_tracking_confidence=0.5)


_ideal_cache = None

def _load_ideal(path):
    global _ideal_cache
    if _ideal_cache is None:
        raw = json.load(open(path))
        _ideal_cache = {
           'pose_data': raw['pose_data'],
           'timestamps': np.array([f['timestamp'] for f in raw['pose_data']]),
           'landmarks': np.array([
               [[lm['x'],lm['y'],lm['z'],lm['visibility']] for lm in f['landmarks']]
               for f in raw['pose_data']
           ])
        }
    return _ideal_cache



class FormComparison:
    def __init__(self, ideal_data_path=None):
        if ideal_data_path is None:
            # Use default path in static folder
            ideal_data_path = os.path.join(current_app.static_folder, 'data', 'forms', 'pose_data', 'wt_koreo_ideal_data.json')
        
        print(f"Loading ideal pose data from {ideal_data_path}...")
        with open(ideal_data_path, 'r') as f:
            self.ideal_data = json.load(f)
        print("Ideal pose data loaded successfully")
        
        # Initialize other attributes
        self.pose = _mp_pose
        self.mp_drawing = mp.solutions.drawing_utils
        
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

        raw = json.load(open(ideal_data_path))
        self.pose_data = raw['pose_data']

        # each frame's timestamp in seconds
        self.ideal_timestamps = np.array([f['timestamp'] for f in self.pose_data])

        # each frame F, N landmarks, (x,y,z,visibility)
        self.ideal_landmarks = np.array([
            [[lm['x'], lm['y'], lm['z'], lm['visibility']]
             for lm in f['landmarks']]
            for f in self.pose_data
        ])

        # Initialize scale smoothing variables
        self.last_vertical_scale = 1.0
        self.last_horizontal_scale = 1.0
        self.smoothing_factor = 0.3  # Lower = more smoothing

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
        
        # Calculate height scale (primary scaling factor)
        user_height = abs(user_landmarks[0]['y'] - user_landmarks[27]['y'])  # Nose to right ankle
        ideal_height = abs(ideal_landmarks[0]['y'] - ideal_landmarks[27]['y'])
        height_scale = user_height / ideal_height if ideal_height > 0 else 1.0
        
        # Calculate width scale (secondary scaling factor)
        user_shoulder_width = abs(user_landmarks[11]['x'] - user_landmarks[12]['x'])  # Left to right shoulder
        ideal_shoulder_width = abs(ideal_landmarks[11]['x'] - ideal_landmarks[12]['x'])
        width_scale = user_shoulder_width / ideal_shoulder_width if ideal_shoulder_width > 0 else 1.0
        
        # Apply different scales for vertical and horizontal dimensions
        # Increase vertical scale by 20% and reduce horizontal scale
        vertical_scale = height_scale * 1  # Stretch vertically
        horizontal_scale = width_scale * 0.9  # Compress horizontally

        # Add safeguards against extreme scaling
        vertical_scale = max(0.8, min(vertical_scale, 1.8))  # Increased minimum scale
        horizontal_scale = max(0.8, min(horizontal_scale, 1.8))  # Increased minimum scale
        
        # Create aligned ideal landmarks
        aligned_ideal = []
        for lm in ideal_landmarks:
            # Skip landmarks with low visibility to prevent hallucination
            if lm['visibility'] < 0.5:
                aligned_ideal.append(lm)  # Keep original landmark if visibility is low
                continue
                
            # Scale x and y coordinates differently
            aligned_x = (lm['x'] - ideal_center[0]) * horizontal_scale + user_center[0]
            aligned_y = (lm['y'] - ideal_center[1]) * vertical_scale + user_center[1]
            aligned_z = lm['z'] * ((vertical_scale + horizontal_scale) / 2)  # Average scale for depth
            
            # Ensure coordinates stay within reasonable bounds
            aligned_x = max(0.0, min(aligned_x, 1.0))
            aligned_y = max(0.0, min(aligned_y, 1.0))
            
            aligned_ideal.append({
                'x': aligned_x,
                'y': aligned_y,
                'z': aligned_z,
                'visibility': lm['visibility']
            })
            
        return aligned_ideal

    def get_aligned_ideal(self, t_sec, user_landmarks):
        """
        t_sec: float, seconds into the user video
        user_landmarks: list of dicts (for visibility & shape reference)
        returns: list of aligned landmark dicts
        """
        # 1. Find bracketing frames
        idx = np.searchsorted(self.ideal_timestamps, t_sec)

        if idx <= 0:
            interp = self.ideal_landmarks[0]
        elif idx >= len(self.ideal_timestamps):
            interp = self.ideal_landmarks[-1]
        else:
            t0, t1 = self.ideal_timestamps[idx - 1], self.ideal_timestamps[idx]
            # weight of relative distance from t1 to t2
            w = (t_sec - t0) / (t1 - t0)
            L0 = self.ideal_landmarks[idx - 1]  # (N,4)
            L1 = self.ideal_landmarks[idx]
            # weighted average of poses
            interp = (1 - w) * L0 + w * L1  # (N,4) float array

        # 2. Convert interp into same dict list your align_poses expects:
        ideal_lms = [
            {'x': float(x), 'y': float(y), 'z': float(z), 'visibility': float(v)}
            for x, y, z, v in interp
        ]
        # 3. Now call your existing align_poses:
        return self.align_poses(user_landmarks, ideal_lms)
    
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
            for connection in mp.solutions.pose.POSE_CONNECTIONS:
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
                return None, []
                
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

            all_feature_vectors = []

            SELECTED_JOINTS = ['left_shoulder', 'right_shoulder', 'left_hip', 'right_hip', 'left_knee', 'right_knee']
            SELECTED_ANGLES = ['left_knee', 'right_knee', 'left_elbow', 'right_elbow']

            DOWNSAMPLE = (width, height)
            FRAME_SKIP = 2

            fourcc = cv2.VideoWriter_fourcc(*'avc1')
            temp_out = str(output_path) + ".novid.mp4"
            out = cv2.VideoWriter(temp_out, fourcc, fps / (FRAME_SKIP + 1), DOWNSAMPLE)

            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break

                if frame_count % (FRAME_SKIP + 1) != 0:
                    frame_count += 1
                    continue

                frame = cv2.resize(frame, DOWNSAMPLE, interpolation=cv2.INTER_LINEAR)
                
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
                    t_msec = cap.get(cv2.CAP_PROP_POS_MSEC)
                    t_sec = t_msec / 1000.0

                    # 2) Interpolate & align the ideal pose at this time
                    aligned_ideal = self.get_aligned_ideal(t_sec, user_landmarks)
                        
                    if aligned_ideal:
                        # Draw user pose in red
                        self.mp_drawing.draw_landmarks(
                            frame,
                            results.pose_landmarks,
                            mp.solutions.pose.POSE_CONNECTIONS,
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
                            mp.solutions.pose.POSE_CONNECTIONS,
                            self.ideal_drawing_spec
                        )

                        user_pts_arr = np.array([[lm['x'], lm['y']] for lm in user_landmarks])
                        ideal_pts_arr = np.array([[lm['x'], lm['y']] for lm in aligned_ideal])

                        # 2) Compute joint & angle errors
                        joint_errs = joint_errors(user_pts_arr, ideal_pts_arr, included=SELECTED_JOINTS)
                        angle_errs = angle_errors(user_pts_arr, ideal_pts_arr, included=SELECTED_ANGLES)

                        # 3) Build your timestamp (in seconds) and package into a feature vector
                        t_msec = cap.get(cv2.CAP_PROP_POS_MSEC)
                        t_sec = t_msec / 1000.0
                        fv = build_feature_vector(t_sec, joint_errs, angle_errs)

                        # 4) Append to the list
                        all_feature_vectors.append(fv)

                # Add frame number
                cv2.putText(frame, f"Frame: {frame_count}", (10, 30),
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                
                # # Convert frame to RGB for MoviePy
                # frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                # processed_frames.append(frame_rgb)

                out.write(frame)  # write BGR directly
                
                frame_count += 1
                
                # Show progress
                if frame_count % 30 == 0:  # Show every 30 frames
                    progress = (frame_count / total_frames) * 100
                    print(f"Progress: {progress:.1f}% ({frame_count}/{total_frames} frames)")
            
            print(f"Processed {frame_count} frames")

            cap.release()
            out.release()

            temp_vid_path = output_path + ".novid.mp4"
            final_vid_path = output_path

            print(f"✅ Wrote raw video frames to {temp_out}")


            
            # Add audio if provided
            if audio_path:
                audio_file = Path(audio_path)
                if audio_file.exists():
                    final = str(output_path)
                    cmd = [
                        'ffmpeg', '-y',
                        '-i', temp_out,
                        '-i', str(audio_file),
                        '-c:v', 'copy',
                        '-c:a', 'aac',
                        '-b:a', '128k',
                        '-shortest',
                        final
                    ]
                    subprocess.run(cmd, check=True)
                    os.remove(temp_out)
                    print(f"✅ Final video with audio at {final}")
                    return final, all_feature_vectors

            print(f"✅ Comparison video saved to {output_path}")

            os.rename(temp_out, str(output_path))
            return str(output_path), all_feature_vectors

        except Exception as e:
            print(f"Error processing video: {str(e)}")
            return None, []

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