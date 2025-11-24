import io
import torch
import torch.nn as nn
from torchvision import models, transforms
from PIL import Image
from backend.interface import AIModel

class EyeScannerModel(AIModel):
    @property
    def name(self):
        return "diabetic-retinopathy-glaucoma-detector"

    @property
    def input_type(self):
        return "image"

    def load(self):
        print("Loading ResNet-18 (Lightweight)...")
        
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
        print(f"Eye Scanner loaded on {self.device}")
 
    async def predict(self, input_data: bytes):
        try:
            # 1. Preprocess
            image = Image.open(io.BytesIO(input_data)).convert('RGB')
            # Add batch dimension (1, 3, 224, 224) and move to GPU
            tensor = self.transform(image).unsqueeze(0).to(self.device)
            
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
                    f"Architecture: ResNet-18 (Lightweight)\n"
                    f"Device: {self.device}\n"
                    f"Raw Score (Abnormal): {abnormal_score:.4f}"
                ),
                "image_size": f"{image.width}x{image.height}"
            }
            
        except Exception as e:
            return {"error": f"Inference failed: {str(e)}"}

