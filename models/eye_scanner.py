import io
import logging
import os
import numpy as np
import torch
import torch.nn as nn
from torchvision import models, transforms
from PIL import Image
from backend.interface import AIModel

logger = logging.getLogger(__name__)

class EyeScannerModel(AIModel):
    @property
    def name(self):
        return "diabetic-retinopathy-glaucoma-detector"

    @property
    def input_type(self):
        return "image"

    def load(self):
        logger.info("Loading ResNet-18 (Lightweight)...")

        # Optional Triton path
        triton_url = os.getenv("TRITON_URL")
        if triton_url:
            try:
                import tritonclient.http as triton_http
            except Exception as e:
                raise RuntimeError("TRITON_URL is set but tritonclient is not available. Install 'tritonclient[http]'.") from e

            self.triton_client = triton_http.InferenceServerClient(url=triton_url)
            self.triton_model_name = os.getenv("TRITON_MODEL_NAME", "resnet18")
            self.triton_input_name = os.getenv("TRITON_INPUT_NAME", "input")
            self.triton_output_name = os.getenv("TRITON_OUTPUT_NAME", "logits")
            self.use_triton = True

            # Keep preprocessing identical
            self.transform = transforms.Compose([
                transforms.Resize(256),
                transforms.CenterCrop(224),
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406], 
                                     std=[0.229, 0.224, 0.225])
            ])

            self.ready = True
            logger.info("✅ Eye Scanner using Triton at %s (model: %s)", triton_url, self.triton_model_name)
            return
        
        # 1. Setup Device (Use your RTX 4070 Ti)
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        
        # 2. Load a real, lightweight architecture
        # We use ResNet-18 with default ImageNet weights
        weights = models.ResNet18_Weights.DEFAULT
        self.model = models.resnet18(weights=weights)

        # 3. Modify the 'Head' for Medical Binary Classification
        # ImageNet has 1000 classes. We replace the last layer to have just 2:
        # [0] = Normal
        # [1] = Abnormal
        num_features = self.model.fc.in_features
        self.model.fc = nn.Linear(num_features, 2)

        # Move to GPU and set to evaluation mode
        self.model = self.model.to(self.device)
        self.model.eval()

        # 4. Define the exact transforms ResNet expects
        self.transform = transforms.Compose([
            transforms.Resize(256),
            transforms.CenterCrop(224),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], 
                                 std=[0.229, 0.224, 0.225])
        ])
        self.ready = True
        logger.info("Eye Scanner loaded on %s", self.device)
 
    async def predict(self, input_data: bytes):
        try:
            # 1. Preprocess
            image = Image.open(io.BytesIO(input_data)).convert('RGB')
            # Add batch dimension (1, 3, 224, 224) and move to GPU
            tensor = self.transform(image).unsqueeze(0)

            if getattr(self, "use_triton", False):
                import tritonclient.http as triton_http

                input_data_np = tensor.numpy().astype(np.float32)
                inputs = [triton_http.InferInput(self.triton_input_name, input_data_np.shape, "FP32")]
                inputs[0].set_data_from_numpy(input_data_np)
                outputs = [triton_http.InferRequestedOutput(self.triton_output_name)]

                response = self.triton_client.infer(
                    model_name=self.triton_model_name,
                    inputs=inputs,
                    outputs=outputs
                )

                logits = response.as_numpy(self.triton_output_name)
                # Softmax
                exp = np.exp(logits - np.max(logits, axis=1, keepdims=True))
                probs = exp / np.sum(exp, axis=1, keepdims=True)
                abnormal_score = float(probs[0][1])
                normal_score = float(probs[0][0])
            else:
                tensor = tensor.to(self.device)
                # 2. Real Inference
                with torch.no_grad():
                    outputs = self.model(tensor)
                    # Convert logits to probabilities (0% to 100%)
                    probs = torch.nn.functional.softmax(outputs, dim=1)
                    
                    # Get probability of Class 1 (Abnormal)
                    abnormal_score = probs[0][1].item()
                    normal_score = probs[0][0].item()

            # 3. Logic
            # Since this is a base model (not fine-tuned on eyes yet), 
            # it's essentially guessing based on visual features.
            is_abnormal = abnormal_score > 0.5
            confidence = abnormal_score if is_abnormal else normal_score
            
            diagnosis = "Potential Abnormality Detected" if is_abnormal else "No Significant Abnormalities"
            
            return {
                "diagnosis": diagnosis,
                "confidence": f"{confidence:.2%}",
                "details": (
                    "Backbone: ResNet-18 (ImageNet-pretrained)\n"
                    "Stem: 7x7 conv, 64 filters, stride 2 + maxpool\n"
                    "Stages: 4 residual stages (2 blocks each)\n"
                    "Head: global average pool + 2-class linear layer\n"
                    f"Device: {self.device if not getattr(self, 'use_triton', False) else 'triton'}\n"
                    f"Serving: {'Triton' if getattr(self, 'use_triton', False) else 'PyTorch'}\n"
                    f"Raw Score (Abnormal): {abnormal_score:.4f}\n"
                    "Note: This is not medically fine-tuned."
                ),
                "image_size": f"{image.width}x{image.height}"
            }
            
        except Exception as e:
            return {"error": f"Inference failed: {str(e)}"}

