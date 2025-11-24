from backend.interface import AIModel
from transformers import pipeline
import asyncio

class HFSentimentModel(AIModel):
    @property
    def name(self):
        return "hf-patient-sentiment"

    @property
    def input_type(self):
        return "text"

    def load(self):
        print("⬇️ Downloading/Loading Hugging Face Model (distilbert)...")
        # This pipeline downloads the model automatically on first use
        self.pipe = pipeline("sentiment-analysis", model="distilbert-base-uncased-finetuned-sst-2-english")
        self.ready = True
        print("✅ Hugging Face Model Loaded")

    async def predict(self, input_data):
        # Run inference (blocking call, so we wrap it if needed, but for this demo it's fine)
        # In production, you'd run this in a thread pool
        result = self.pipe(input_data)[0]
        
        # Map standard sentiment to medical context
        interpretation = "Positive Outlook" if result['label'] == 'POSITIVE' else "Negative/Distressed"
        
        return {
            "sentiment": interpretation,
            "raw_label": result['label'],
            "confidence": f"{result['score']:.2%}",
            "source": "Hugging Face (DistilBERT)"
        }
