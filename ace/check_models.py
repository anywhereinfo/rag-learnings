import vertexai
from vertexai.generative_models import GenerativeModel
from vertexai.language_models import TextGenerationModel, TextEmbeddingModel
import os

PROJECT_ID = "gcp-prj-ntpc-np-01"
LOCATION = "us-central1"

vertexai.init(project=PROJECT_ID, location=LOCATION)

candidate_models = [
    # User Requested
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-3-pro-preview",
    "gemini-3.0-pro-001",
    "gemini-3.0-pro",
    # Gemini 1.5
    "gemini-1.5-pro-001",
    "gemini-1.5-pro",
    "gemini-1.5-flash-001",
    "gemini-1.5-flash",
    # Gemini 1.0
    "gemini-1.0-pro-001",
    "gemini-1.0-pro",
    "gemini-pro",
    # Gemini 3 (if available)
    "gemini-3.0-flash-001",
    # PaLM 2 (Legacy)
    "text-bison@002",
    "text-bison@001",
    "text-bison",
    "text-unicorn",
    # Embeddings
    "text-embedding-004",
    "text-embedding-gecko@001"
]

print(f"Checking availability in {PROJECT_ID} / {LOCATION}...\n")

for model_name in candidate_models:
    print(f"Testing {model_name}...", end=" ", flush=True)
    try:
        if "embedding" in model_name:
            model = TextEmbeddingModel.from_pretrained(model_name)
            # Try a dummy embedding
            model.get_embeddings(["test"])
            print("AVAILABLE (Embeddings)")
        elif "bison" in model_name or "unicorn" in model_name:
            model = TextGenerationModel.from_pretrained(model_name)
            model.predict("test")
            print("AVAILABLE (generation)")
        else:
            # Gemini
            model = GenerativeModel(model_name)
            model.generate_content("test")
            print("AVAILABLE (GenAI)")
            
    except Exception as e:
        if "404" in str(e):
            print("NOT FOUND (404)")
        elif "403" in str(e):
            print("PERMISSION DENIED (403)")
        else:
            print(f"ERROR: {str(e)[:100]}...")
