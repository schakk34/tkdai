import os
import json
import requests
import logging
import cv2
import numpy as np
from datetime import timedelta
import mediapipe as mp
from dotenv import load_dotenv
import time
import base64

class FormAnalyzer:
    def __init__(self):
        # Load environment variables from .env file
        load_dotenv()
        
        # Get API key from environment
        self.api_key = os.getenv('HUGGINGFACE_API_KEY')
        if not self.api_key:
            print("Warning: HUGGINGFACE_API_KEY not found in environment variables")
        else:
            print(f"API Key found: {self.api_key[:4]}...{self.api_key[-4:]}")
            print(f"API Key length: {len(self.api_key)}")
        
        # Load ideal form data
        try:
            with open('static/data/forms/pose_data/koryo_ideal_data.json', 'r') as f:
                self.ideal_data = json.load(f)
            print("Successfully loaded ideal form data")
        except Exception as e:
            print(f"Error loading ideal form data: {str(e)}")
            self.ideal_data = None

    def _extract_key_frames(self, video_path, num_frames=10):
        """Extract evenly spaced frames from the video."""
        cap = cv2.VideoCapture(video_path)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        
        # Calculate frame intervals
        frame_interval = total_frames // (num_frames + 1)
        key_frames = []
        
        for i in range(1, num_frames + 1):
            frame_idx = i * frame_interval
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            
            if ret:
                timestamp = str(timedelta(seconds=frame_idx/fps))[2:7]
                # Convert frame to base64
                _, buffer = cv2.imencode('.jpg', frame)
                frame_base64 = base64.b64encode(buffer).decode('utf-8')
                key_frames.append({
                    "timestamp": timestamp,
                    "frame": frame_base64
                })
        
        cap.release()
        return key_frames

    def _get_frame_description(self, frame_base64):
        """Use BLIP model to get a description of the frame."""
        headers = {
            "Authorization": f"Bearer {self.api_key}"
        }

        API_URL = "https://api-inference.huggingface.co/models/bigscience/bloomz-560m"
        
        # Convert base64 back to binary
        frame_binary = base64.b64decode(frame_base64)
        
        try:
            response = requests.post(API_URL, headers=headers, data=frame_binary)
            if response.status_code == 200:
                result = response.json()
                return result[0]['generated_text']
            else:
                print(f"Error getting frame description: {response.status_code} {response.text}")
                return "Unable to describe frame"
        except Exception as e:
            print(f"Error in frame description: {str(e)}")
            return "Error describing frame"

    def analyze_form(self, video_url):
        try:
            print("\n=== Starting Form Analysis ===")
            print(f"Video URL received: {video_url}")
            
            # Verify API key
            if not self.api_key:
                raise Exception("HuggingFace API key not found. Please set HUGGINGFACE_API_KEY in your environment variables.")
            
            # Verify ideal data is loaded
            if not self.ideal_data:
                raise Exception("Ideal form data not loaded. Please ensure koryo_ideal_data.json exists.")
            
            # Convert URL to file path
            if video_url.startswith('http://127.0.0.1:5002/'):
                video_path = video_url.replace('http://127.0.0.1:5002/', '')
                print(f"Converted to file path: {video_path}")
            elif video_url.startswith('/static/'):
                video_path = video_url[1:]  # Remove leading slash
                print(f"Converted to file path: {video_path}")
            else:
                raise Exception(f"Invalid video URL format: {video_url}")
            
            if not os.path.exists(video_path):
                raise Exception(f"Video file not found at: {video_path}")

            # Extract and describe key frames from user video
            print("\nExtracting key frames from user video...")
            user_frames = self._extract_key_frames(video_path)
            
            # Get descriptions for each frame
            print("\nGetting frame descriptions...")
            frame_comparisons = []
            
            for user_frame in user_frames:
                user_desc = self._get_frame_description(user_frame["frame"])
                
                # Find closest matching ideal frame based on timestamp
                timestamp = user_frame["timestamp"]
                ideal_frame = self._find_closest_ideal_frame(timestamp)
                
                frame_comparisons.append({
                    "timestamp": timestamp,
                    "user_frame": user_desc,
                    "ideal_frame": ideal_frame
                })
            
            print("\nFrame comparisons:")
            for comp in frame_comparisons:
                print(f"\nTimestamp: {comp['timestamp']}")
                print(f"User: {comp['user_frame']}")
                print(f"Ideal: {comp['ideal_frame']}")

            # Prepare the prompt for the LLM
            prompt = f"""As a Taekwondo instructor, analyze this form performance by comparing the student's execution with the ideal form.
            For each timestamp, I'll show you the student's frame description followed by the ideal form's frame description.

            {json.dumps(frame_comparisons, indent=2)}

            Please provide detailed feedback in the following JSON format:
            {{
                "feedback": [
                    {{
                        "timestamp": "MM:SS",
                        "text": "Detailed feedback about the specific differences between the student's execution and the ideal form, with suggestions for improvement"
                    }}
                ]
            }}

            Focus on:
            1. Technical accuracy of stances and techniques
            2. Timing and rhythm
            3. Balance and stability
            4. Power and precision
            5. Specific corrections for each issue

            Format timestamps as MM:SS and provide at least 3 feedback points."""

            # Call HuggingFace API for final analysis
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            # Use Mistral for the final analysis
            API_URL = "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.2"
            
            payload = {
                "inputs": f"<s>[INST] {prompt} [/INST]</s>",
                "parameters": {
                    "max_new_tokens": 500,
                    "temperature": 0.7,
                    "top_p": 0.9,
                    "return_full_text": False
                }
            }

            print("\nSending request to HuggingFace API for final analysis...")
            print(f"API URL: {API_URL}")
            
            # Add retry logic for API calls
            max_retries = 3
            retry_delay = 5  # seconds
            
            for attempt in range(max_retries):
                try:
                    response = requests.post(API_URL, headers=headers, json=payload, timeout=30)
                    
                    print(f"\nAPI Response Status: {response.status_code}")
                    print(f"API Response Headers: {dict(response.headers)}")
                    print(f"API Response Text: {response.text[:500]}...")  # Print first 500 chars of response
                    
                    if response.status_code == 503:
                        print(f"Model is loading, waiting {retry_delay} seconds...")
                        time.sleep(retry_delay)
                        continue
                        
                    if response.status_code == 200:
                        try:
                            result = response.json()
                            print(f"\nParsed API Response: {json.dumps(result, indent=2)}")
                            feedback_text = result[0]['generated_text'].strip()
                            print(f"\nGenerated Feedback Text: {feedback_text}")

                            try:
                                feedback_data = json.loads(feedback_text)
                            except json.JSONDecodeError as e:
                                print(f"\nFailed to parse generated_text as JSON: {str(e)}")
                                return {
                                    "success": False,
                                    "error": f"Failed to parse response as JSON. Generated text was:\n{feedback_text}"
                                }
                            return {
                                "success": True,
                                "feedback": feedback_data["feedback"]
                            }
                        except Exception as e:
                            print(f"\nError parsing API response: {str(e)}")
                            print(f"Raw response text: {response.text}")
                            raise Exception("Failed to parse API response")
                    else:
                        print(f"\nAPI request failed with status {response.status_code}")
                        print(f"Response: {response.text}")
                        if attempt < max_retries - 1:
                            print(f"Retrying in {retry_delay} seconds...")
                            time.sleep(retry_delay)
                            continue
                        raise Exception(f"API request failed: {response.text}")
                        
                except requests.exceptions.Timeout:
                    print(f"Request timed out. Attempt {attempt + 1} of {max_retries}")
                    if attempt < max_retries - 1:
                        print(f"Retrying in {retry_delay} seconds...")
                        time.sleep(retry_delay)
                        continue
                    raise Exception("Request timed out after multiple attempts")

        except Exception as e:
            print(f"Error analyzing form: {str(e)}")
            print(f"Error type: {type(e)}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            return {
                "success": False,
                "error": f"Failed to analyze form: {str(e)}"
            }

    def _find_closest_ideal_frame(self, timestamp):
        """Find the closest matching ideal frame based on timestamp."""
        try:
            # Convert timestamp to seconds for comparison
            user_min, user_sec = map(int, timestamp.split(':'))
            user_seconds = user_min * 60 + user_sec
            
            # Find the closest ideal frame
            closest_frame = None
            min_diff = float('inf')
            
            for frame in self.ideal_data.get('frames', []):
                ideal_timestamp = frame.get('timestamp', '00:00')
                ideal_min, ideal_sec = map(int, ideal_timestamp.split(':'))
                ideal_seconds = ideal_min * 60 + ideal_sec
                
                diff = abs(user_seconds - ideal_seconds)
                if diff < min_diff:
                    min_diff = diff
                    closest_frame = frame
            
            if closest_frame:
                return closest_frame.get('description', 'No description available')
            return 'No matching ideal frame found'
            
        except Exception as e:
            print(f"Error finding closest ideal frame: {str(e)}")
            return 'Error finding ideal frame'

    def _parse_feedback(self, feedback_text):
        """Parse the feedback into structured format."""
        try:
            return feedback_text
        except Exception as e:
            print(f"Error parsing feedback: {str(e)}")
            return [] 