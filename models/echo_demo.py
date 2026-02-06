"""
Lightweight demo model that requires no ML dependencies.
Used for UI testing and smoke-testing the platform pipeline.
"""

import asyncio
import random
from typing import Any, Dict

from backend.interface import AIModel


class EchoDemo(AIModel):
    """Echo model that returns input text with metadata — no ML deps needed."""

    @property
    def name(self) -> str:
        return "echo_demo"

    @property
    def input_type(self) -> str:
        return "text"

    @property
    def version(self) -> str:
        return "1.0.0"

    def load(self) -> None:
        self.ready = True

    async def predict(self, input_data: Any) -> Dict[str, Any]:
        # Simulate a small amount of compute
        await asyncio.sleep(random.uniform(0.02, 0.08))
        text = str(input_data)
        word_count = len(text.split())
        return {
            "echo": text,
            "word_count": word_count,
            "char_count": len(text),
            "sentiment_stub": random.choice(["positive", "neutral", "negative"]),
            "confidence": round(random.uniform(0.70, 0.99), 3),
            "model": "echo_demo",
        }
