import cv2
import mediapipe as mp
import numpy as np
import os
import json
from pathlib import Path

# Initialize MediaPipe pose detector
mp_pose = mp.solutions.pose
pose = mp_pose.Pose(static_image_mode=True)
mp_drawing = mp.solutions.drawing_utils

# Directory where your pose images are stored
STATIC_DIR = Path('static')
pose_images_dir = STATIC_DIR / 'white_belt'
output_json = 'reference_poses.json'

def process_pose_images():
    if not pose_images_dir.exists():
        print(f"❌ Error: Directory {pose_images_dir} does not exist!")
        return

    reference_poses = {}
    image_files = [f for f in pose_images_dir.iterdir() if f.suffix.lower() in ['.jpg', '.png', '.jpeg']]

    if not image_files:
        print(f"❌ No image files found in {pose_images_dir}")
        return

    print(f"🔍 Found {len(image_files)} images to process...")

    for filepath in sorted(image_files):
        try:
            print(f"Processing {filepath.name}...")
            image = cv2.imread(str(filepath))
            if image is None:
                print(f"❌ Failed to load image: {filepath.name}")
                continue

            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            results = pose.process(image_rgb)

            if results.pose_landmarks:
                landmarks = []
                for lm in results.pose_landmarks.landmark:
                    landmarks.append({
                        'x': float(lm.x),
                        'y': float(lm.y),
                        'z': float(lm.z),
                        'visibility': float(lm.visibility)
                    })

                # Use filename (without extension) as the key
                pose_name = filepath.stem
                reference_poses[pose_name] = landmarks

                # Draw landmarks and preview
                annotated_image = image.copy()
                mp_drawing.draw_landmarks(
                    annotated_image,
                    results.pose_landmarks,
                    mp_pose.POSE_CONNECTIONS
                )
                
                # Resize image for display if too large
                height, width = annotated_image.shape[:2]
                max_dimension = 800
                if height > max_dimension or width > max_dimension:
                    scale = max_dimension / max(height, width)
                    new_width = int(width * scale)
                    new_height = int(height * scale)
                    annotated_image = cv2.resize(annotated_image, (new_width, new_height))

                cv2.imshow(pose_name, annotated_image)
                key = cv2.waitKey(500)  # Show for 500ms per image
                cv2.destroyAllWindows()

                if key == 27:  # ESC key
                    break

            else:
                print(f"⚠️ No pose landmarks detected in {filepath.name}")

        except Exception as e:
            print(f"❌ Error processing {filepath.name}: {str(e)}")

    if reference_poses:
        # Save all reference poses to JSON
        with open(output_json, 'w') as f:
            json.dump(reference_poses, f, indent=4)
        print(f"✅ Reference poses saved to {output_json}")
        print(f"📊 Processed {len(reference_poses)} poses successfully")
    else:
        print("❌ No pose data was generated!")

if __name__ == "__main__":
    process_pose_images() 