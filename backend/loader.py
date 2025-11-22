import importlib
import os
import sys
import inspect
from typing import List
from .interface import AIModel
from .registry import registry

def load_plugins(models_dir: str = "models"):
    """
    Dynamically discovers and loads AIModel subclasses from the specified directory.
    """
    print(f"🔌 Scanning for models in '{models_dir}'...")
    
    # Ensure the models directory is in the python path so we can import from it
    abs_path = os.path.abspath(models_dir)
    if abs_path not in sys.path:
        sys.path.append(abs_path)

    # List all python files in the directory
    if not os.path.exists(models_dir):
        print(f"⚠️  Directory {models_dir} not found.")
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
                        
                        print(f"   Found model class: {name}")
                        try:
                            instance = obj()
                            registry.register(instance)
                            print(f"   ✅ Deployed: {instance.name}")
                        except Exception as e:
                            print(f"   ❌ Failed to initialize {name}: {e}")

            except Exception as e:
                print(f"   ❌ Failed to load module {module_name}: {e}")
