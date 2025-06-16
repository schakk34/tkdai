import cv2
import mediapipe as mp
import numpy as np
import json
from pathlib import Path
import time

class WhiteBeltForm:
    def __init__(self):
        self.mp_pose = mp.solutions.pose
        self.pose = self.mp_pose.Pose(
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        self.mp_drawing = mp.solutions.drawing_utils
        
        # Load reference poses
        with open('reference_poses.json', 'r') as f:
            self.reference_poses = json.load(f)
            
        # Sort poses by number
        self.pose_sequence = sorted(
            self.reference_poses.keys(),
            key=lambda x: int(x.replace('white', ''))
        )
        
        # Load reference images
        self.reference_images = {}
        for pose_name in self.pose_sequence:
            img_path = Path('data/white_belt') / f"{pose_name}.png"
            if not img_path.exists():
                img_path = Path('data/white_belt') / f"{pose_name}.jpg"
            if img_path.exists():
                img = cv2.imread(str(img_path))
                if img is not None:
                    # Resize reference image to a standard size
                    img = cv2.resize(img, (320, 240))  # Adjust size as needed
                    self.reference_images[pose_name] = img
        
        self.current_pose_index = 0
        self.pose_confirmed = False
        self.confirmation_frames = 0
        self.required_confirmation_frames = 10  # Number of frames to confirm a pose
        self.last_confirmation_time = 0  # Track when pose was last confirmed
        self.confirmation_display_duration = 2.0  # Duration to show confirmation in seconds
        self.auto_advance_delay = 3.0  # Delay before advancing to next pose
        self.pose_completed = False  # Track if current pose is completed
        
    def calculate_pose_similarity(self, current_landmarks, reference_landmarks):
        """Calculate similarity between current pose and reference pose."""
        similarity_score = 0
        total_landmarks = len(current_landmarks)
        
        for i in range(total_landmarks):
            current_lm = current_landmarks[i]
            reference_lm = reference_landmarks[i]
            
            # Only consider landmarks with good visibility
            if current_lm['visibility'] > 0.7 and reference_lm['visibility'] > 0.7:
                # Calculate Euclidean distance between landmarks
                distance = np.sqrt(
                    (current_lm['x'] - reference_lm['x'])**2 +
                    (current_lm['y'] - reference_lm['y'])**2
                )
                # Convert distance to similarity score (1 - normalized distance)
                similarity_score += 1 - min(distance, 1.0)
                
        # Normalize score
        return similarity_score / total_landmarks if total_landmarks > 0 else 0
    
    def process_frame(self, frame):
        """Process a frame and return the annotated frame with pose feedback."""
        # Convert frame to RGB for MediaPipe
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.pose.process(frame_rgb)
        
        # Convert back to BGR for OpenCV
        annotated_frame = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
        
        # Get current target pose
        current_pose_name = self.pose_sequence[self.current_pose_index]
        
        # Create the combined frame with reference image
        frame_height, frame_width = annotated_frame.shape[:2]
        ref_height = frame_height // 4  # Reference image will take up 1/4 of the height
        ref_width = int(ref_height * 4/3)  # Maintain 4:3 aspect ratio
        
        # Create a black background for the reference image
        ref_background = np.zeros((ref_height, ref_width, 3), dtype=np.uint8)
        
        # If we have a reference image for the current pose, display it
        if current_pose_name in self.reference_images:
            ref_img = self.reference_images[current_pose_name]
            ref_img = cv2.resize(ref_img, (ref_width, ref_height))
            # Place the reference image in the top-right corner
            annotated_frame[0:ref_height, frame_width-ref_width:frame_width] = ref_img
        
        if results.pose_landmarks:
            # Draw pose landmarks
            self.mp_drawing.draw_landmarks(
                annotated_frame,
                results.pose_landmarks,
                self.mp_pose.POSE_CONNECTIONS
            )
            
            # Convert current pose to our format
            current_landmarks = []
            for lm in results.pose_landmarks.landmark:
                current_landmarks.append({
                    'x': float(lm.x),
                    'y': float(lm.y),
                    'z': float(lm.z),
                    'visibility': float(lm.visibility)
                })
            
            # Get reference landmarks
            reference_landmarks = self.reference_poses[current_pose_name]
            
            # Calculate similarity
            similarity = self.calculate_pose_similarity(current_landmarks, reference_landmarks)
            
            current_time = time.time()
            
            # Update pose confirmation
            if similarity > 0.75:  # Threshold for pose recognition
                self.confirmation_frames += 1
                if self.confirmation_frames >= self.required_confirmation_frames and not self.pose_completed:
                    self.pose_confirmed = True
                    self.pose_completed = True
                    self.last_confirmation_time = current_time
            else:
                self.confirmation_frames = 0
            
            # Auto-advance to next pose after delay
            if self.pose_completed and (current_time - self.last_confirmation_time) >= self.auto_advance_delay:
                if self.current_pose_index < len(self.pose_sequence) - 1:
                    self.current_pose_index += 1
                    self.pose_confirmed = False
                    self.pose_completed = False
                    self.confirmation_frames = 0
                
            # Add visual feedback
            feedback_text = f"Current Pose: {current_pose_name}"
            cv2.putText(annotated_frame, feedback_text, (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            
            similarity_text = f"Similarity: {similarity:.2f}"
            cv2.putText(annotated_frame, similarity_text, (10, 70),
                       cv2.FONT_HERSHEY_SIMPLEX, 1, 
                       (0, 255, 0) if similarity > 0.75 else (0, 0, 255), 2)
            
            progress_text = f"Progress: {self.current_pose_index + 1}/{len(self.pose_sequence)}"
            cv2.putText(annotated_frame, progress_text, (10, 110),
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            
            # Show pose confirmation message only for 2 seconds
            if self.pose_confirmed and (current_time - self.last_confirmation_time) <= self.confirmation_display_duration:
                cv2.putText(annotated_frame, "POSE CONFIRMED!", (10, 150),
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            
            # Show countdown to next pose
            if self.pose_completed and self.current_pose_index < len(self.pose_sequence) - 1:
                time_left = self.auto_advance_delay - (current_time - self.last_confirmation_time)
                if time_left > 0:
                    countdown_text = f"Next pose in: {time_left:.1f}s"
                    cv2.putText(annotated_frame, countdown_text, (10, 190),
                               cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
        
        return annotated_frame
    
    def next_pose(self):
        """Move to the next pose if available."""
        if self.current_pose_index < len(self.pose_sequence) - 1:
            self.current_pose_index += 1
            self.pose_confirmed = False
            self.pose_completed = False
            self.confirmation_frames = 0
            return True
        return False
    
    def get_current_pose_name(self):
        """Get the name of the current target pose."""
        return self.pose_sequence[self.current_pose_index]
    
    def is_form_completed(self):
        """Check if all poses have been completed."""
        return (self.current_pose_index == len(self.pose_sequence) - 1 and 
                self.pose_confirmed) 