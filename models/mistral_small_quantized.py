import asyncio
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

from backend.interface import AIModel


class MistralSmallQuantizedModel(AIModel):
    @property
    def name(self):
        return "mistral-small-24b-quantized"

    @property
    def input_type(self):
        return "text"

    @property
    def hardware_requirements(self):
        return {
            "min_ram": 32,
            "min_vram": 24
        }

    def load(self):
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA GPU required for quantized Mistral Small 24B.")

        print("⬇️  Loading Mistral-Small-24B-Instruct (4-bit quantized)...")

        self.model_id = "mistralai/Mistral-Small-24B-Instruct-2501"

        quant_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16
        )

        self.tokenizer = AutoTokenizer.from_pretrained(self.model_id)
        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_id,
            quantization_config=quant_config,
            device_map="auto",
            torch_dtype=torch.float16
        )

        self.ready = True
        print("✅ Mistral Small 24B (quantized) loaded successfully")

    async def predict(self, input_data):
        loop = asyncio.get_running_loop()

        if not hasattr(self, "model") or self.model is None:
            raise RuntimeError("Model is not loaded. Check server logs for load errors.")

        def _run_inference():
            messages = [
                {"role": "user", "content": input_data}
            ]

            if hasattr(self.tokenizer, "apply_chat_template"):
                prompt = self.tokenizer.apply_chat_template(
                    messages,
                    tokenize=False,
                    add_generation_prompt=True
                )
            else:
                prompt = input_data

            inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=512,
                do_sample=True,
                temperature=0.7,
                top_p=0.95
            )
            generated = self.tokenizer.decode(outputs[0], skip_special_tokens=True)

            if prompt in generated:
                return generated.replace(prompt, "").strip()

            return generated.strip()

        response_text = await loop.run_in_executor(None, _run_inference)
        return {
            "response": response_text,
            "model": self.model_id,
            "quantization": "4-bit"
        }