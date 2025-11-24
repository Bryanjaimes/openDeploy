from fastapi import FastAPI, UploadFile, File, HTTPException, Body, Security, Depends, status, Form
from fastapi.security import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from typing import Any
from contextlib import asynccontextmanager
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from backend.registry import registry
from backend.loader import load_plugins
from backend.gen_ui import generate_ui_from_prompt
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

# In-memory history storage
prediction_history = []

@app.get("/history", dependencies=[Depends(get_api_key)])
def get_history():
    """Get the history of predictions"""
    return prediction_history

@app.post("/models/{model_name}/predict", dependencies=[Depends(get_api_key)])
async def predict(model_name: str, file: UploadFile = File(None), text_input: str = Form(None)):
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
    import datetime
    history_entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "model": model_name,
        "input": input_summary,
        "result": result
    }
    prediction_history.insert(0, history_entry) # Add to top

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

