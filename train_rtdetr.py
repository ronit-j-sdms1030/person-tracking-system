"""
Standalone script to fine-tune RT-DETR for Head Detection on Kaggle or Colab.

Instructions for Kaggle:
1. Create a new notebook with GPU enabled.
2. Install dependencies:
   !pip install ultralytics roboflow
3. Download a Head Detection dataset in YOLO/COCO format (e.g. from Roboflow Universe).
4. Run this script!

Ensure your data.yaml file maps class 0 to 'head'.
"""

import os
from ultralytics import RTDETR

def train_custom_rtdetr():
    # 1. Initialize the RT-DETR model with pre-trained weights
    # We use rtdetr-l (large) for better accuracy, or rtdetr-r18 for faster CPU inference later
    model_name = "rtdetr-l.pt"
    print(f"Loading base model: {model_name}")
    model = RTDETR(model_name)

    # 2. Define the path to your dataset YAML file
    # Replace 'data.yaml' with the actual path to your dataset config
    data_yaml_path = "data.yaml" 
    
    if not os.path.exists(data_yaml_path):
        print(f"Error: {data_yaml_path} not found. Please upload your dataset first.")
        return

    # 3. Start fine-tuning
    print("Starting fine-tuning...")
    results = model.train(
        data=data_yaml_path,
        epochs=50,             # Adjust epochs based on dataset size and time available
        imgsz=640,             # Input image size
        batch=16,              # Batch size (reduce if you get Out Of Memory errors)
        device=0,              # Use GPU 0
        name="rtdetr_head_model", # Name of the run folder
        workers=8              # Number of dataloader workers
    )

    print("Training complete!")
    print("Your trained model weights are saved at: runs/detect/rtdetr_head_model/weights/best.pt")
    print("Download 'best.pt' and rename it to 'rtdetr-custom.pt' for your server!")

if __name__ == "__main__":
    train_custom_rtdetr()
