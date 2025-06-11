import cv2
import mediapipe as mp
import numpy as np
import time

class PracticeStudio:
    def __init__(self, movement_type=0, rep_duration=4, rest_duration=2):
        self.movement_type = movement_type
        self.rep_duration = rep_duration
        self.rest_duration = rest_duration

        # Initialize MediaPipe with optimized settings
        self.mp_drawing = mp.solutions.drawing_utils
        self.mp_pose = mp.solutions.pose
        self.pose = self.mp_pose.Pose(
            static_image_mode=False,
            model_complexity=1,  # Use medium complexity model
            smooth_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )

        # Try multiple camera indices
        self.video = None
        for i in range(2):  # Try camera indices 0 and 1
            self.video = cv2.VideoCapture(i)
            if self.video.isOpened():
                print(f"Successfully opened camera {i}")
                # Set camera properties for better performance
                self.video.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                self.video.set(cv2.CAP_PROP_FPS, 30)
                self.video.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                self.video.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                break
            else:
                print(f"Failed to open camera {i}")
                if self.video:
                    self.video.release()

        if self.video is None or not self.video.isOpened():
            print("Warning: No camera available. Using fallback mode.")
            self.fallback_frame = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(self.fallback_frame, "No camera access", (50, 240), 
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

        self.start_time = time.time()
        self.counter = 0
        self.stage = None
        self.last_process_time = 0
        self.process_interval = 1.0 / 15  # Process every 15 frames
        self.last_results = None

        # Set movement name based on type
        if self.movement_type == 1:  # Front Kick
            self.movement_name = "Front Kick"
        elif self.movement_type == 2:  # Roundhouse Kick
            self.movement_name = "Roundhouse Kick"
        elif self.movement_type == 3:  # Basic Punches
            self.movement_name = "Basic Punch"
        elif self.movement_type == 4:  # Poomsae
            self.movement_name = "Poomsae"
        else:  # Default to front kick
            self.movement_name = "Front Kick"

    def __del__(self):
        if self.video and self.video.isOpened():
            self.video.release()

    def get_frame(self):
        """Processes each frame with real-time feedback for Taekwondo techniques."""
        if not hasattr(self, 'video') or not self.video or not self.video.isOpened():
            ret, jpeg = cv2.imencode('.jpg', self.fallback_frame)
            return jpeg.tobytes() if ret else None

        ret, frame = self.video.read()
        if not ret:
            return None

        # Flip the frame horizontally for mirror effect
        frame = cv2.flip(frame, 1)
        
        current_time = time.time()
        should_process = (current_time - self.last_process_time) >= self.process_interval

        if should_process:
            self.last_process_time = current_time
            # Process frame for pose detection
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            self.last_results = self.pose.process(frame_rgb)
        
        elapsed_time = current_time - self.start_time
        cycle_time = self.rep_duration + self.rest_duration
        cycle_progress = elapsed_time % cycle_time
        is_resting = cycle_progress >= self.rep_duration

        # Timer Display
        if is_resting:
            remaining_time_display = f"Rest... {max(0, self.rest_duration - (cycle_progress - self.rep_duration)):.1f}s"
            technique_feedback = "Prepare for next movement"
            form_feedback = ""
        else:
            remaining_time_display = f"Timer: {max(0, self.rep_duration - cycle_progress):.1f}s"
            technique_feedback = "Maintain good form"
            form_feedback = "Practice Mode"

        # Add overlays
        cv2.putText(frame, f"{self.movement_name} Practice", (30, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        cv2.putText(frame, remaining_time_display, (30, 70), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        if technique_feedback:
            cv2.putText(frame, technique_feedback, (30, 110), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        if form_feedback:
            cv2.putText(frame, form_feedback, (30, 150), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

        # Draw pose landmarks only if we processed this frame
        if should_process and self.last_results and self.last_results.pose_landmarks:
            self.mp_drawing.draw_landmarks(frame, self.last_results.pose_landmarks, self.mp_pose.POSE_CONNECTIONS)

        # Encode and return the frame
        ret, jpeg = cv2.imencode('.jpg', frame)
        return jpeg.tobytes() if ret else None

# Usage
if __name__ == "__main__":
    processor = PracticeStudio(movement_type=1)
    processor.plot_movement_trajectory()
