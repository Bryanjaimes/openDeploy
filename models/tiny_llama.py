import torch
import asyncio
from transformers import pipeline
from backend.interface import AIModel

class TinyLlamaModel(AIModel):
    @property
    def name(self):
        return "tiny-llama-chat"

    @property
    def input_type(self):
        return "text"

    @property
    def hardware_requirements(self):
        return {
            "min_ram": 8,
            "min_vram": 6 # Needs GPU ideally
        }

    def load(self):
        print("⬇️  Loading TinyLlama-1.1B-Chat...")
        # TinyLlama is ~1.1B params, runs easily on most CPUs/small GPUs
        self.model_id = "TinyLlama/TinyLlama-1.1B-Chat-v1.0"
        
        # Force CUDA usage since user has a powerful GPU
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"🚀 Using device: {device}")

        self.pipe = pipeline(
            "text-generation",
            model=self.model_id,
            torch_dtype=torch.float16, # Use float16 for GPU speedup
            device_map="auto"
        )
        self.ready = True
        print(f"✅ {self.model_id} Loaded Successfully on {device}")

    async def predict(self, input_data):
        loop = asyncio.get_running_loop()
        
        def _run_inference():
            # Direct interaction: No system prompt, just the user input
            messages = [
                {"role": "user", "content": input_data},
            ]
            
            prompt = self.pipe.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            
            outputs = self.pipe(
                prompt, 
                max_new_tokens=256, 
                do_sample=True, 
                temperature=0.7, 
                top_k=50, 
                top_p=0.95
            )
            
            generated_text = outputs[0]["generated_text"]
            
            # Clean up the response to remove the prompt
            if "<|assistant|>" in generated_text:
                return generated_text.split("<|assistant|>")[-1].strip()
            return generated_text

        # Run blocking inference in a thread pool
        response_text = await loop.run_in_executor(None, _run_inference)

        return {"response": response_text}

        return {
            "response": response,
            "model": "TinyLlama-1.1B-Chat"
        }
