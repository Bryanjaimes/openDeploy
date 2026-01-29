import importlib
import os
import sys
import inspect
import logging
import time
from typing import List
from backend.interface import AIModel
from backend.registry import registry
from backend.metrics import metrics_store

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def load_plugins(models_dir: str = "models"):
    """
    Dynamically discovers and loads AIModel subclasses from the specified directory.
    """
    logger.info(f"🔌 Scanning for models in '{models_dir}'...")
    
    # Ensure the parent of models directory is in the python path so we can import models.x
    abs_path = os.path.abspath(models_dir)
    parent_dir = os.path.dirname(abs_path)
    if parent_dir not in sys.path:
        sys.path.append(parent_dir)

    # List all python files in the directory
    if not os.path.exists(models_dir):
        logger.warning(f"⚠️  Directory {models_dir} not found.")
        return

    for filename in os.listdir(models_dir):
        if filename.endswith(".py") and not filename.startswith("__"):
            module_name = filename[:-3] # remove .py
            
            try:
                # Import the module dynamically
                # We assume models are in the 'models' package context or top level
                module = importlib.import_module(f"models.{module_name}")
                
                # Find all classes in the module that inherit from AIModel
                for name, obj in inspect.getmembers(module):
                    if (inspect.isclass(obj) and 
                        issubclass(obj, AIModel) and 
                        obj is not AIModel):
                        
                        logger.info(f"   Found model class: {name}")
                        try:
                            instance = obj()
                            start = time.perf_counter()
                            registry.register(instance)
                            duration_ms = (time.perf_counter() - start) * 1000.0
                            metrics_store.record_model_load(instance.name, duration_ms)
                            logger.info(f"   ✅ Deployed: {instance.name}")
                        except Exception as e:
                            logger.error(f"   ❌ Failed to initialize {name}: {e}")

            except Exception as e:
                logger.error(f"   ❌ Failed to load module {module_name}: {e}")
