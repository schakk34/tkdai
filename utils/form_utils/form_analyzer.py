import os
import json
import requests
import re
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

class FormAnalyzer:
    def __init__(
        self,
        provider: str = 'gemini',  # 'gemini' or 'huggingface'
        api_key: str = None,
        model: str = None,
        breadth: float = 5.0,
        overlap: float = 1.0,
        score_threshold: float = 0.9,
        max_tokens: int = 100000,
        temperature: float = 0.5,
        top_p: float = 0.9
    ):
        self.provider = provider.lower()
        self.breadth = breadth
        self.overlap = overlap
        self.score_threshold = score_threshold
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.top_p = top_p

        # Configure appropriate client
        if self.provider == 'huggingface':
            self.model_url = model or 'https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.2'
            self.api_key = api_key or os.getenv('HUGGINGFACE_API_KEY')
            if not self.api_key:
                raise RuntimeError('HUGGINGFACE_API_KEY not set')
        elif self.provider == 'gemini':
            if genai is None:
                raise ImportError('google-generative-ai library is required for Gemini provider')
            self.api_key = api_key or os.getenv('GOOGLE_API_KEY')
            if not self.api_key:
                raise RuntimeError('GOOGLE_API_KEY not set')
            genai.configure(api_key=self.api_key)
            # Use default Gemini model or override
            self.model = 'gemini-2.5-flash'
        else:
            raise ValueError('Unknown provider: choose "gemini" or "huggingface"')

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
        if self.provider == 'huggingface':
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
        else:  # gemini
            response = genai.GenerativeModel(
                model_name=self.model,
                system_instruction={"role": "system", "parts": [{"text": "You are a helpful coaching assistant for Taekwondo forms."}]}
            ).generate_content(
                contents=[{"role": "user", "parts": [{"text": prompt}]}],
                generation_config=genai.GenerationConfig(
                    temperature=self.temperature,
                    top_p=self.top_p,
                    max_output_tokens=self.max_tokens
                )
            )
            text = response.text.strip()

        m = re.search(r'```json\s*(\{[\s\S]*?\})\s*```', text)
        if m:
            json_str = m.group(1)
        else:
            # Fallback: first {...} to last }
            start = text.find('{');
            end = text.rfind('}')
            json_str = text[start:end + 1] if start != -1 and end != -1 else text

        # Parse and return
        try:
            result = json.loads(json_str)
            return result.get('feedback', [])
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON parse error: {e}\nExtracted text:\n{json_str}")

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
