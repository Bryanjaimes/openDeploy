from backend.interface import AIModel
import random
import asyncio

class CareerAdvisorModel(AIModel):
    @property
    def name(self):
        return "career-advisor-bot"

    @property
    def input_type(self):
        return "text"

    def load(self):
        print("⬇️  Loading Career Advisor Knowledge Base...")
        # Simulated loading time
        self.ready = True
        print("✅ Career Advisor Loaded")

    async def predict(self, input_data):
        # Simple keyword-based logic for "fake" AI
        text = input_data.lower()
        print(f"DEBUG CAREER ADVISOR INPUT: {text}")
        
        careers = {
            "tech": ["Software Engineer", "Data Scientist", "Cybersecurity Analyst", "DevOps Engineer"],
            "art": ["Graphic Designer", "UX/UI Designer", "Animator", "Art Director"],
            "science": ["Lab Researcher", "Biologist", "Chemist", "Environmental Scientist"],
            "business": ["Project Manager", "Marketing Specialist", "Financial Analyst", "Entrepreneur"],
            "health": ["Nurse", "Physical Therapist", "Medical Researcher", "Health Administrator"]
        }
        
        suggestion = ""
        reasoning = ""

        if any(word in text for word in ["code", "computer", "program", "ai", "data", "tech"]):
            suggestion = random.choice(careers["tech"])
            reasoning = "your interest in technology and problem solving."
        elif any(word in text for word in ["draw", "design", "art", "creative", "color"]):
            suggestion = random.choice(careers["art"])
            reasoning = "your creative eye and passion for aesthetics."
        elif any(word in text for word in ["science", "lab", "experiment", "biology", "chemistry"]):
            suggestion = random.choice(careers["science"])
            reasoning = "your analytical mind and curiosity about how the world works."
        elif any(word in text for word in ["money", "business", "manage", "lead", "market"]):
            suggestion = random.choice(careers["business"])
            reasoning = "your leadership potential and business acumen."
        elif any(word in text for word in ["help", "people", "doctor", "nurse", "health"]):
            suggestion = random.choice(careers["health"])
            reasoning = "your desire to help others and interest in well-being."
        else:
            suggestion = "Consultant"
            reasoning = "your versatile set of interests that could apply to many fields."

        response_text = f"Based on what you told me, I think you would make a great **{suggestion}**! This aligns well with {reasoning}"

        return {"response": response_text}
