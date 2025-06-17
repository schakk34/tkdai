import os
import json
import requests

class FormAnalyzer:
    def __init__(
        self,
        api_key: str = None,
        model_url: str = "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.2",
        breadth: float = 5.0,
        overlap: float = 1.0,
        score_threshold: float = 0.9,
        max_tokens: int = 300,
        temperature: float = 0.5,
        top_p: float = 0.9
    ):
        self.api_key = api_key or os.getenv('HUGGINGFACE_API_KEY')
        self.model_url = model_url
        self.breadth = breadth
        self.overlap = overlap
        self.score_threshold = score_threshold
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.top_p = top_p

    def sample_worst_frames(self, feature_vectors):
        """
        Sliding-window sampling of worst frames below threshold.
        """
        if not feature_vectors:
            return []
        vecs = sorted(feature_vectors, key=lambda x: x['timestamp'])
        start = vecs[0]['timestamp']
        end = vecs[-1]['timestamp']
        step = self.breadth - self.overlap
        selected = []
        win_start = start
        while win_start <= end:
            win_end = win_start + self.breadth
            bucket = [fv for fv in vecs if win_start <= fv['timestamp'] < win_end]
            if bucket:
                worst = min(bucket, key=lambda fv: fv['overall_score'])
                if worst['overall_score'] < self.score_threshold:
                    selected.append(worst)
            win_start += step
        return selected

    def build_prompt(self, sampled_frames):
        """
        Construct the LLM prompt from sampled feature vectors.
        """
        data_json = json.dumps(sampled_frames, indent=2)
        return f"""
You are a Taekwondo instructor. Below is the student’s form data vs. ideal form. 
For each timestamp, you have:
  • joint_errors: normalized distances (lower is better)
  • angle_errors: abs angle diffs in degrees
  • overall_score: 0–1 (1 is perfect)

Data:
{data_json}

Provide at least 3 actionable feedback points in JSON:
{{"feedback":[{{"timestamp":"MM:SS","text":"..."}}]}}
Focus on the largest errors first and give clear coaching tips.
""".strip()

    def ask_llm_for_feedback(self, prompt):
        """
        Send the prompt to the LLM and parse its JSON response.
        """
        if not self.api_key:
            raise RuntimeError("HuggingFace API key is missing.")
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {
            "inputs": f"<s>[INST] {prompt} [/INST]</s>",
            "parameters": {
                "max_new_tokens": self.max_tokens,
                "temperature": self.temperature,
                "top_p": self.top_p,
                "return_full_text": False
            }
        }
        resp = requests.post(self.model_url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        raw = resp.json()
        text = raw[0].get('generated_text', '').strip()
        try:
            obj = json.loads(text)
            return obj.get('feedback', [])
        except json.JSONDecodeError:
            raise ValueError(f"Failed to parse LLM response as JSON: {text}")

    def analyze(self, feature_vectors):
        """
        End-to-end: sample frames, build prompt, call LLM.
        Returns list of feedback entries.
        """
        sampled = self.sample_worst_frames(feature_vectors)
        if not sampled:
            return []  # no errors above threshold
        prompt = self.build_prompt(sampled)
        return self.ask_llm_for_feedback(prompt)
