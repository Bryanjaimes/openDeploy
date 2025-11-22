# OpenDeploy Models

This directory contains the AI models deployed on the platform.

## How to Deploy a New Model

1. Create a new Python file (e.g., `my_model.py`) in this directory.
2. Define a class that inherits from `backend.interface.AIModel`.
3. Implement the required methods: `name`, `input_type`, `load`, and `predict`.
4. Restart the backend server.

The platform will automatically discover your model, register it, and generate a UI for it.

## Example

```python
from backend.interface import AIModel

class MyModel(AIModel):
    @property
    def name(self): return "my-cool-model"
    
    @property
    def input_type(self): return "text"

    def load(self): pass

    async def predict(self, input_data):
        return {"result": "Hello World"}
```
