import asyncio
import logging

from backend.interface import AIModel
from transformers import pipeline

logger = logging.getLogger(__name__)


class HFSentimentModel(AIModel):
    @property
    def name(self):
        return "hf-patient-sentiment"

    @property
    def input_type(self):
        return "text"

    def load(self):
        logger.info("⬇️ Downloading/Loading Hugging Face Model (distilbert)...")
        self.pipe = pipeline("sentiment-analysis", model="distilbert-base-uncased-finetuned-sst-2-english")
        self.ready = True
        logger.info("✅ Hugging Face Model Loaded")

    async def predict(self, input_data):
        loop = asyncio.get_running_loop()

        def _run_inference():
            return self.pipe(input_data)[0]

        result = await loop.run_in_executor(None, _run_inference)

        interpretation = "Positive Outlook" if result['label'] == 'POSITIVE' else "Negative/Distressed"

        return {
            "sentiment": interpretation,
            "raw_label": result['label'],
            "confidence": f"{result['score']:.2%}",
            "source": "Hugging Face (DistilBERT)"
        }
