from typing import List, Dict, Optional, Any
from pydantic import BaseModel

class CloudInstance(BaseModel):
    provider: str
    instance_type: str
    vcpus: int
    ram_gb: float
    gpu: Optional[str] = None
    vram_gb: Optional[float] = 0
    price_per_hour: float
    free_tier: bool = False

class CloudOptimizer:
    def __init__(self):
        # A simplified catalog of cloud instances (Prices are estimates)
        self.catalog: List[CloudInstance] = [
            # --- AWS ---
            CloudInstance(provider="AWS", instance_type="t2.micro", vcpus=1, ram_gb=1, price_per_hour=0.0116, free_tier=True),
            CloudInstance(provider="AWS", instance_type="t3.medium", vcpus=2, ram_gb=4, price_per_hour=0.0416),
            CloudInstance(provider="AWS", instance_type="g4dn.xlarge", vcpus=4, ram_gb=16, gpu="NVIDIA T4", vram_gb=16, price_per_hour=0.526),
            CloudInstance(provider="AWS", instance_type="p3.2xlarge", vcpus=8, ram_gb=61, gpu="NVIDIA V100", vram_gb=16, price_per_hour=3.06),
            
            # --- GCP ---
            CloudInstance(provider="GCP", instance_type="e2-micro", vcpus=2, ram_gb=1, price_per_hour=0.00, free_tier=True), # Free tier specific
            CloudInstance(provider="GCP", instance_type="n1-standard-4 + T4", vcpus=4, ram_gb=15, gpu="NVIDIA T4", vram_gb=16, price_per_hour=0.35),
            
            # --- Azure ---
            CloudInstance(provider="Azure", instance_type="B1s", vcpus=1, ram_gb=1, price_per_hour=0.01, free_tier=True),
            CloudInstance(provider="Azure", instance_type="NC4as T4 v3", vcpus=4, ram_gb=28, gpu="NVIDIA T4", vram_gb=16, price_per_hour=0.58),
            
            # --- Lambda / Serverless (Conceptual) ---
            CloudInstance(provider="Modal/RunPod", instance_type="Serverless GPU", vcpus=2, ram_gb=12, gpu="Any", vram_gb=24, price_per_hour=0.20)
        ]

    def recommend(self, min_ram: float, min_vram: float = 0, preferred_provider: str = None) -> Dict[str, Any]:
        """
        Finds the most cost-effective instance for the given requirements.
        """
        candidates = []
        
        for instance in self.catalog:
            # Filter by Provider
            if preferred_provider and instance.provider.lower() != preferred_provider.lower():
                continue
                
            # Filter by Specs
            if instance.ram_gb < min_ram:
                continue
            
            if min_vram > 0:
                if not instance.gpu or instance.vram_gb < min_vram:
                    continue
            
            candidates.append(instance)
            
        if not candidates:
            return {"error": "No suitable instances found for these requirements."}
            
        # Sort by price
        candidates.sort(key=lambda x: x.price_per_hour)
        
        best_option = candidates[0]
        
        return {
            "recommendation": best_option,
            "alternatives": candidates[1:3],
            "monthly_cost_est": f"${best_option.price_per_hour * 730:.2f}",
            "is_free_tier": best_option.free_tier
        }

optimizer = CloudOptimizer()
