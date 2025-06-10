import os
import cv2
import mediapipe as mp
import numpy as np
import re
import time
from scipy.interpolate import interp1d
import matplotlib.pyplot as plt

class PracticeStudio:
    def __init__(self, movement_type=0, rep_duration=4, rest_duration=2):
        self.dataset_path = "dataset/SkeletonData/RawData"
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
        self.ground_truth_angles = None
        self.last_process_time = 0
        self.process_interval = 1.0 / 15  # Process every 15 frames
        self.last_results = None

        # Define joint sets for different Taekwondo techniques
        if self.movement_type == 1:  # Front Kick
            self.desired_joints = ["HipRight", "KneeRight", "AnkleRight"]
            self.movement_name = "Front Kick"
        elif self.movement_type == 2:  # Roundhouse Kick
            self.desired_joints = ["HipRight", "KneeRight", "AnkleRight"]
            self.movement_name = "Roundhouse Kick"
        elif self.movement_type == 3:  # Basic Punches
            self.desired_joints = ["ShoulderRight", "ElbowRight", "WristRight"]
            self.movement_name = "Basic Punch"
        elif self.movement_type == 4:  # Poomsae
            self.desired_joints = ["HipRight", "KneeRight", "AnkleRight", "ShoulderRight", "ElbowRight", "WristRight"]
            self.movement_name = "Poomsae"
        else:  # Default to front kick
            self.desired_joints = ["HipRight", "KneeRight", "AnkleRight"]
            self.movement_name = "Front Kick"

        self.load_and_process_dataset()

    def __del__(self):
        if self.video and self.video.isOpened():
            self.video.release()

    def load_and_process_dataset(self):
        """Loads the dataset, extracts angles, and computes ground truth."""
        dataset = self.load_intellirehab_dataset(self.dataset_path, self.movement_type)
        if not dataset:
            # If no dataset available, create synthetic data for the movement
            print("No dataset found, using synthetic data")
            self.ground_truth_angles = self.create_synthetic_movement_data()
            return

        all_angles = self.extract_joint_angles(dataset)
        self.ground_truth_angles, _ = self.compute_ground_truth_time_series(all_angles)

    def load_intellirehab_dataset(self, folder_path, movement_type):
        """Loads and cleans only valid IntelliRehabDS CSV files for a specific movement type."""
        dataset = {}
        # print(f"Loading dataset for movement type: {movement_type}")

        for file in os.listdir(folder_path):
            parts = file.split('_')
            if len(parts) < 6 or parts[2] != str(movement_type) or parts[4][0] != '2':
                continue
            file_path = os.path.join(folder_path, file)
            joint_positions = self.clean_and_parse_intellirehab_csv(file_path)
            if len(joint_positions) < 10:
                continue
            dataset[file] = joint_positions

        # print(f"Loaded {len(dataset)} files: {list(dataset.keys())}")
        return dataset

    def clean_and_parse_intellirehab_csv(self, file_path):
        """Reads and cleans an IntelliRehabDS CSV file."""
        cleaned_lines = []
        with open(file_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or "Version0.1" in line:
                    continue
                cleaned_lines.append(line)
        return [self.parse_intellirehab_line(line) for line in cleaned_lines]

    def parse_intellirehab_line(self, line):
        """Extracts joint data from a single line."""
        parts = line.split(",", 3)
        frame_id, _, _, joint_data = parts
        joint_pattern = r"\(([^,]+),Tracked,([-.\d]+),([-.\d]+),([-.\d]+),[\d.]+,[\d.]+\)"
        matches = re.findall(joint_pattern, joint_data)
        joints = {joint[0]: (float(joint[1]), float(joint[2]), float(joint[3])) for joint in matches}
        return int(frame_id), joints

    def extract_joint_angles(self, dataset):
        """Extracts angles between relevant joints from each parsed CSV dataset."""
        all_angles = []

        for file, data in dataset.items():
            angles = []
            for frame_id, joints in data:
                if not all(j in joints for j in self.desired_joints):
                    continue

                joint1, joint2, joint3 = [joints[joint] for joint in self.desired_joints]
                angle = self.compute_angle(joint1, joint2, joint3)
                angles.append(angle)

            if angles and len(angles) > 10:
                all_angles.append(self.normalize_time_series(angles))  # Ensure non-empty lists

        if not all_angles:
            raise ValueError("No valid angles extracted from dataset. Check data formatting.")

        return all_angles

    def compute_ground_truth_time_series(self, all_angles):
        """Computes the mean and standard deviation of joint angles at each time step."""
        if not all_angles:
            raise ValueError("Error: all_angles is empty. No data to compute ground truth.")

        all_angles = np.array(all_angles)
        if all_angles.ndim != 2:
            raise ValueError(f"Expected a 2D array, but got shape {all_angles.shape}")

        return np.mean(all_angles, axis=0), np.std(all_angles, axis=0)

    def normalize_time_series(self, data, num_points=100):
        """Resamples a variable-length series to a fixed-length using interpolation."""
        x_old = np.linspace(0, 1, len(data))
        x_new = np.linspace(0, 1, num_points)
        interpolator = interp1d(x_old, data, kind='linear')
        return interpolator(x_new)

    def compute_angle(self, a, b, c):
        """Computes the angle between three joint points."""
        a, b, c = np.array(a), np.array(b), np.array(c)
        radians = np.arctan2(c[1]-b[1], c[0]-b[0]) - np.arctan2(a[1]-b[1], a[0]-b[0])
        angle = np.abs(radians * 180.0 / np.pi)
        return 360 - angle if angle > 180.0 else angle
    
    def normalize_angle(self, angle, min_expected=50, max_expected=120):
        """Normalizes the calculated angle (0-180) to fit within the expected range (50-120)."""
        return ((angle - 20) / (170 - 20)) * (max_expected - min_expected) + min_expected

    def extract_mediapipe_joints(self, landmarks):
        """Extracts required joint coordinates from Mediapipe."""
        joint_mapping = {
            "HipRight": self.mp_pose.PoseLandmark.RIGHT_HIP,
            "KneeRight": self.mp_pose.PoseLandmark.RIGHT_KNEE,
            "AnkleRight": self.mp_pose.PoseLandmark.RIGHT_ANKLE,
            "HipLeft": self.mp_pose.PoseLandmark.LEFT_HIP,
            "KneeLeft": self.mp_pose.PoseLandmark.LEFT_KNEE,
            "AnkleLeft": self.mp_pose.PoseLandmark.LEFT_ANKLE,
            "ShoulderRight": self.mp_pose.PoseLandmark.RIGHT_SHOULDER,
            "ElbowRight": self.mp_pose.PoseLandmark.RIGHT_ELBOW,
            "WristRight": self.mp_pose.PoseLandmark.RIGHT_WRIST,
            "ShoulderLeft": self.mp_pose.PoseLandmark.LEFT_SHOULDER,
            "ElbowLeft": self.mp_pose.PoseLandmark.LEFT_ELBOW,
            "WristLeft": self.mp_pose.PoseLandmark.LEFT_WRIST
        }

        joints = {}
        for joint_name in self.desired_joints:
            if joint_name in joint_mapping:
                lm = landmarks.landmark[joint_mapping[joint_name]]
                joints[joint_name] = (lm.x, lm.y, lm.z)

        return joints

    def create_synthetic_movement_data(self):
        """Creates synthetic movement data for different techniques."""
        num_points = 100
        t = np.linspace(0, 1, num_points)
        
        if self.movement_type == 1:  # Front Kick
            # Simulate knee lift followed by leg extension
            angles = np.array([
                90 + 45 * np.sin(2 * np.pi * t),  # Hip angle
                90 + 30 * np.sin(2 * np.pi * t),  # Knee angle
                45 + 30 * np.sin(2 * np.pi * t)   # Ankle angle
            ])
            
        elif self.movement_type == 2:  # Roundhouse Kick
            # Simulate circular motion
            angles = np.array([
                90 + 60 * np.sin(2 * np.pi * t),  # Hip angle
                90 + 45 * np.sin(2 * np.pi * t),  # Knee angle
                45 + 45 * np.sin(2 * np.pi * t)   # Ankle angle
            ])
            
        elif self.movement_type == 3:  # Basic Punches
            # Simulate punch extension and retraction
            angles = np.array([
                90 - 45 * np.sin(2 * np.pi * t),  # Shoulder angle
                90 + 45 * np.sin(2 * np.pi * t),  # Elbow angle
                0 + 30 * np.sin(2 * np.pi * t)    # Wrist angle
            ])
            
        else:  # Default movement
            angles = np.array([
                90 + 30 * np.sin(2 * np.pi * t),  # Joint 1
                90 + 30 * np.sin(2 * np.pi * t),  # Joint 2
                45 + 30 * np.sin(2 * np.pi * t)   # Joint 3
            ])
        
        print(f"Created synthetic data with shape: {angles.shape}")
        return angles  # Shape will be (3, num_points)

    def get_technique_feedback(self, angles, expected_angles):
        """Provides specific feedback for Taekwondo techniques."""
        if not isinstance(angles, (list, np.ndarray)) or not isinstance(expected_angles, (list, np.ndarray)):
            return "Analyzing movement..."

        if len(angles) != len(expected_angles):
            return "Calibrating..."
            
        feedback = ""
        
        if self.movement_type == 1:  # Front Kick
            if angles[0] < expected_angles[0] - 15:
                feedback = "Lift your knee higher!"
            elif angles[1] < expected_angles[1] - 15:
                feedback = "Extend your leg more!"
            elif abs(angles[0] - expected_angles[0]) <= 15 and abs(angles[1] - expected_angles[1]) <= 15:
                feedback = "Good form!"
            else:
                feedback = "Keep your balance!"
                
        elif self.movement_type == 2:  # Roundhouse Kick
            if angles[0] < expected_angles[0] - 15:
                feedback = "Pivot your supporting foot!"
            elif angles[1] < expected_angles[1] - 15:
                feedback = "Chamber your knee higher!"
            elif abs(angles[0] - expected_angles[0]) <= 15 and abs(angles[1] - expected_angles[1]) <= 15:
                feedback = "Excellent rotation!"
            else:
                feedback = "Turn your hips more!"
                
        elif self.movement_type == 3:  # Basic Punches
            if angles[0] < expected_angles[0] - 15:
                feedback = "Rotate your shoulder more!"
            elif angles[1] < expected_angles[1] - 15:
                feedback = "Extend your punch!"
            elif abs(angles[0] - expected_angles[0]) <= 15 and abs(angles[1] - expected_angles[1]) <= 15:
                feedback = "Good power!"
            else:
                feedback = "Keep your guard up!"
                
        else:  # Default feedback
            avg_error = np.mean([abs(a - e) for a, e in zip(angles, expected_angles)])
            if avg_error > 15:
                feedback = "Adjust your form!"
            else:
                feedback = "Good technique!"
                
        return feedback

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
            technique_feedback = "Prepare for next technique"
            form_feedback = ""
        else:
            remaining_time_display = f"Timer: {max(0, self.rep_duration - cycle_progress):.1f}s"
            technique_feedback = ""
            form_feedback = ""
            
            if self.last_results and self.last_results.pose_landmarks:
                rep_progress = cycle_progress / self.rep_duration
                # Get the expected angles for the current time
                if isinstance(self.ground_truth_angles, np.ndarray) and self.ground_truth_angles.ndim == 2:
                    num_angles = self.ground_truth_angles.shape[0]
                    time_points = np.linspace(0, 1, self.ground_truth_angles.shape[1])
                    expected_angles = [
                        float(np.interp(rep_progress, time_points, self.ground_truth_angles[i]))
                        for i in range(num_angles)
                    ]
                else:
                    expected_angles = [90.0] * 3  # Default angles if no ground truth available
                
                joints = self.extract_mediapipe_joints(self.last_results.pose_landmarks)
                if all(j in joints for j in self.desired_joints):
                    current_angles = []
                    for i in range(0, len(self.desired_joints)-2, 3):
                        angle = self.compute_angle(
                            joints[self.desired_joints[i]],
                            joints[self.desired_joints[i+1]],
                            joints[self.desired_joints[i+2]]
                        )
                        current_angles.append(self.normalize_angle(angle))
                    
                    technique_feedback = self.get_technique_feedback(current_angles, expected_angles)
                    score = 100 - min(100, sum([abs(a - b) for a, b in zip(current_angles, expected_angles)]))
                    form_feedback = f"Form Score: {max(0, score):.0f}%"

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
