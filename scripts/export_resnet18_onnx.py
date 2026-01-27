import os
import torch
import torch.nn as nn
from torchvision import models


def export_resnet18_onnx(output_dir: str):
    os.makedirs(output_dir, exist_ok=True)
    model = models.resnet18(weights=models.ResNet18_Weights.DEFAULT)

    # Replace head for binary classification
    num_features = model.fc.in_features
    model.fc = nn.Linear(num_features, 2)
    model.eval()

    dummy = torch.randn(1, 3, 224, 224)
    onnx_path = os.path.join(output_dir, "model.onnx")

    torch.onnx.export(
        model,
        dummy,
        onnx_path,
        input_names=["input"],
        output_names=["logits"],
        dynamic_axes={"input": {0: "batch"}, "logits": {0: "batch"}},
        opset_version=18,
        dynamo=False,
    )

    print(f"✅ Exported ONNX model to {onnx_path}")


if __name__ == "__main__":
    repo_root = os.path.join(os.getcwd(), "triton_model_repo", "resnet18", "1")
    export_resnet18_onnx(repo_root)
