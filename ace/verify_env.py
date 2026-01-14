
import vertexai
from vertexai.language_models import TextEmbeddingModel, TextGenerationModel
from vertexai.generative_models import GenerativeModel
import traceback

project_id = "gcp-prj-ntpc-np-01"
location = "us-central1"

print(f"Initializing Vertex AI with project={project_id}, location={location}")
vertexai.init(project=project_id, location=location)

print("\n--- Testing Embeddings (text-embedding-004) ---")
try:
    model = TextEmbeddingModel.from_pretrained("text-embedding-004")
    vec = model.get_embeddings(["Hello world"])[0].values
    print("Success! Embedding generated (first 5 dims):", vec[:5])
except Exception:
    print("Embedding Failed:")
    traceback.print_exc()

print("\n--- Testing Generation (gemini-1.0-pro) ---")
try:
    model = GenerativeModel("gemini-1.0-pro")
    resp = model.generate_content("Hello")
    print("Success! Response:", resp.text)
except Exception:
    print("Gemini 1.0 Pro Failed:")
    print(traceback.format_exc().splitlines()[-1]) # Print last line

print("\n--- Testing Generation (text-bison) ---")
try:
    model = TextGenerationModel.from_pretrained("text-bison")
    resp = model.predict("Hello")
    print("Success! Response:", resp.text)
except Exception:
    print("Text Bison Failed:")
    print(traceback.format_exc().splitlines()[-1])
