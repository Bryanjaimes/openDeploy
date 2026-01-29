import asyncio
import re
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

        user_prompt = (input_data or "").strip()

        def _clean_response(text: str) -> str:
            cleaned = (text or "").strip()

            if user_prompt:
                lowered = cleaned.lower()
                prompt_lower = user_prompt.lower()
                prompt_index = lowered.find(prompt_lower)
                if prompt_index != -1:
                    cleaned = cleaned[prompt_index + len(user_prompt):].lstrip(' \n\r:?-')

            boilerplate_patterns = [
                r"^You are .*?Large Language Model.*?(\n\n|\r\n\r\n)",
                r"^You are .*?Mistral.*?(\n\n|\r\n\r\n)",
                r"^Your knowledge base.*?(\n\n|\r\n\r\n)",
                r"^The current date.*?(\n\n|\r\n\r\n)",
                r"^When you're not sure.*?(\n\n|\r\n\r\n)"
            ]
            for pattern in boilerplate_patterns:
                cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE | re.DOTALL)

            return cleaned.strip() or text.strip()

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
        response_text = _clean_response(response_text)
        tokens_generated = None
        try:
            tokens_generated = len(self.tokenizer.encode(response_text))
        except Exception:
            tokens_generated = None
        return {
            "response": response_text,
            "model": self.model_id,
            "quantization": "4-bit",
            "tokens_generated": tokens_generated
        }