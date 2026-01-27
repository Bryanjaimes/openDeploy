from fastapi import FastAPI, UploadFile, File, HTTPException, Body, Security, Depends, status, Form
from fastapi.security import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from typing import Any, Optional
from contextlib import asynccontextmanager
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from backend.registry import registry
from backend.loader import load_plugins
from backend.gen_ui import generate_ui_from_prompt
from backend.database import init_db, get_db, Prediction
from backend.cloud_optimizer import optimizer
from sqlalchemy.orm import Session
from pydantic import BaseModel
import google.generativeai as genai

# --- Security Setup ---
API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

async def get_api_key(api_key_header: str = Security(api_key_header)):
    expected_key = os.getenv("OPENDEPLOY_API_KEY")
    
    # If no key is configured on the server, allow access (Dev Mode)
    if not expected_key:
        return None
        
    if api_key_header == expected_key:
        return api_key_header
        
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Invalid or missing API Key"
    )
# ----------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize Database
    init_db()
    
    # Startup: Load all models dynamically
    # Resolve absolute path to models directory (sibling of backend)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    models_path = os.path.join(os.path.dirname(current_dir), "models")
    load_plugins(models_path)
    yield
    # Shutdown: Could unload models here if needed

app = FastAPI(
    title="OpenDeploy v2", 
    description="Minimal AI Deployment Platform",
    lifespan=lifespan
)

# Enable CORS for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Welcome to OpenDeploy v2. Platform is running."}

@app.get("/health")
def health_check():
    return {"status": "healthy"}

@app.get("/models", dependencies=[Depends(get_api_key)])
def list_models():
    """List all deployed models and their capabilities"""
    return registry.list_models()

@app.get("/history", dependencies=[Depends(get_api_key)])
def get_history(db: Session = Depends(get_db)):
    """Get the history of predictions"""
    return db.query(Prediction).order_by(Prediction.timestamp.desc()).all()

@app.post("/models/{model_name}/predict", dependencies=[Depends(get_api_key)])
async def predict(model_name: str, file: UploadFile = File(None), text_input: str = Form(None), db: Session = Depends(get_db)):
    """
    Generic prediction endpoint. 
    Accepts either a file (for image/audio models) or text_input (for LLMs).
    """
    model = registry.get_model(model_name)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    result = None
    input_summary = ""

    # Simple routing based on input type
    if model.input_type == "text":
        if not text_input:
             raise HTTPException(status_code=400, detail="Model requires 'text_input'")
        result = await model.predict(text_input)
        input_summary = text_input[:50] + "..." if len(text_input) > 50 else text_input
    
    elif model.input_type == "image":
        if not file:
            raise HTTPException(status_code=400, detail="Model requires a file upload")
        # In a real app, we'd process the image bytes here
        content = await file.read()
        result = await model.predict(content)
        input_summary = f"Image: {file.filename}"

    else:
        raise HTTPException(status_code=500, detail="Unsupported model input type")

    # Save to history
    db_prediction = Prediction(
        model=model_name,
        input=input_summary,
        result=result
    )
    db.add(db_prediction)
    db.commit()
    db.refresh(db_prediction)

    return result

class GenUIRequest(BaseModel):
    prompt: str

@app.post("/generate-ui", dependencies=[Depends(get_api_key)])
async def generate_ui(request: GenUIRequest):
    """
    Generates HTML UI components based on a natural language prompt.
    """
    html = generate_ui_from_prompt(request.prompt)
    return {"html": html}

class ChatRequest(BaseModel):
    message: str

@app.post("/chat", dependencies=[Depends(get_api_key)])
async def chat(request: ChatRequest):
    """
    Chat with an AI assistant about the UI/platform.
    Uses Gemini AI for intelligent conversation.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    
    # Fallback if no API key
    if not api_key:
        message = request.message.lower()
        ui_keywords = ["add", "create", "make", "field", "input", "button", "form"]
        if any(kw in message for kw in ui_keywords):
            return {"response": "I'll create that for you!", "action": "generate_ui", "prompt": request.message}
        return {"response": "I can help you customize this interface!", "action": "none"}
    
    # Use Gemini AI
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('models/gemini-2.5-flash')
        
        system_prompt = """You are a helpful UI assistant for OpenDeploy, a medical AI platform.
        
When users request UI changes (like "add patient field" or "create a dropdown"):
- Respond: "I'll create that for you!"
- Return: {"response": "your message", "action": "generate_ui", "prompt": "clear description of what to generate"}

When users ask questions:
- Respond conversationally
- Return: {"response": "your message", "action": "none"}

Always return valid JSON with 'response', 'action', and optionally 'prompt' fields."""
        
        response = model.generate_content(f"{system_prompt}\n\nUser: {request.message}")
        
        # Parse JSON from response
        import json, re
        text = response.text.strip()
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        
        if json_match:
            return json.loads(json_match.group())
        else:
            return {"response": text, "action": "none"}
            
    except Exception as e:
        print(f"Gemini error: {e}")
        return {"response": "I'm here to help! What would you like to add?", "action": "none"}

class GenerateRequest(BaseModel):
    prompt: str
    model: Optional[str] = None

@app.post("/generate", dependencies=[Depends(get_api_key)])
async def generate(request: GenerateRequest, db: Session = Depends(get_db)):
    """
    Simple text-generation endpoint for V0 local runner.
    """
    # Pick requested model or first text-capable model
    model_name = request.model
    if not model_name:
        for m in registry.list_models():
            if m.get("input_type") == "text":
                model_name = m.get("name")
                break

    if not model_name:
        raise HTTPException(status_code=404, detail="No text-capable model available")

    model = registry.get_model(model_name)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    result = await model.predict(request.prompt)

    # Save to history
    db_prediction = Prediction(
        model=model_name,
        input=request.prompt[:50] + "..." if len(request.prompt) > 50 else request.prompt,
        result=result
    )
    db.add(db_prediction)
    db.commit()
    db.refresh(db_prediction)

    if isinstance(result, dict):
        return {"model": model_name, **result}
    return {"model": model_name, "response": result}

class CloudRecommendRequest(BaseModel):
    model_name: str
    provider: str = None

@app.post("/deploy/recommend", dependencies=[Depends(get_api_key)])
async def recommend_cloud(request: CloudRecommendRequest):
    """
    Analyzes a model's requirements and recommends the best cloud instance.
    """
    model = registry.get_model(request.model_name)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    
    # Use model's self-reported requirements
    reqs = model.hardware_requirements
    min_ram = reqs.get("min_ram", 1)
    min_vram = reqs.get("min_vram", 0)
    
    recommendation = optimizer.recommend(
        min_ram=min_ram, 
        min_vram=min_vram, 
        preferred_provider=request.provider
    )
    
    return recommendation

