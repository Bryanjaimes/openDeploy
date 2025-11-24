import sys
import os

# Add current directory to sys.path
sys.path.append(os.getcwd())

from backend.loader import load_plugins
from backend.registry import registry

print(f"Current working directory: {os.getcwd()}")
print(f"sys.path: {sys.path}")

models_path = os.path.join(os.getcwd(), "models")
print(f"Loading models from: {models_path}")

load_plugins(models_path)

print("\nRegistry state:")
print(registry._models)
