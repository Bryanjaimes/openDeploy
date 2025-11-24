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
        print("Loading Symptom Checker knowledge base...")
        self.ready = True

    async def predict(self, input_data):
        # Simulate processing
        await asyncio.sleep(1)
        
        symptoms = input_data.lower()
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
        else:
            diagnosis = "General Malaise"
            confidence = "40%"

        return {
            "diagnosis": diagnosis,
            "confidence": confidence,
            "details": f"Analyzed symptoms: {input_data[:50]}..."
        }
