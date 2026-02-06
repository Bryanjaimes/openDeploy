"""
Rule-based symptom checker model.
Keyword matching for common symptom patterns — no ML dependencies required.
"""

import asyncio
from backend.interface import AIModel


class SymptomCheckerModel(AIModel):
    @property
    def name(self):
        return "general-symptom-checker"

    @property
    def input_type(self):
        return "text"

    def load(self):
        self.ready = True

    async def predict(self, input_data):
        await asyncio.sleep(0.3)

        symptoms = str(input_data).lower()
        diagnosis = "Unknown"
        confidence = "0%"

        if "headache" in symptoms and "fever" in symptoms:
            diagnosis = "Flu / Viral Infection"
            confidence = "85%"
        elif "chest pain" in symptoms:
            diagnosis = "Urgent: Cardiac Evaluation Needed"
            confidence = "95%"
        elif "itchy" in symptoms or "rash" in symptoms:
            diagnosis = "Allergic Reaction"
            confidence = "70%"
        elif "cough" in symptoms:
            diagnosis = "Upper Respiratory Infection"
            confidence = "65%"
        elif "nausea" in symptoms or "vomit" in symptoms:
            diagnosis = "Gastrointestinal Distress"
            confidence = "60%"
        else:
            diagnosis = "General Malaise"
            confidence = "40%"

        return {
            "diagnosis": diagnosis,
            "confidence": confidence,
            "details": f"Analyzed symptoms: {str(input_data)[:50]}...",
        }
