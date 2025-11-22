from fastapi import FastAPI, UploadFile, File, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from typing import Any
from contextlib import asynccontextmanager

from .registry import registry
from .loader import load_plugins

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Load all models dynamically
    load_plugins("models")
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

@app.get("/models")
def list_models():
    """List all deployed models and their capabilities"""
    return registry.list_models()

@app.post("/models/{model_name}/predict")
async def predict(model_name: str, file: UploadFile = File(None), text_input: str = Body(None)):
    """
    Generic prediction endpoint. 
    Accepts either a file (for image/audio models) or text_input (for LLMs).
    """
    model = registry.get_model(model_name)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    # Simple routing based on input type
    if model.input_type == "text":
        if not text_input:
             raise HTTPException(status_code=400, detail="Model requires 'text_input'")
        result = await model.predict(text_input)
        return result
    
    elif model.input_type == "image":
        if not file:
            raise HTTPException(status_code=400, detail="Model requires a file upload")
        # In a real app, we'd process the image bytes here
        content = await file.read()
        result = await model.predict(content)
        return result

    else:
        raise HTTPException(status_code=500, detail="Unsupported model input type")

