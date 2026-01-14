import vertexai
from vertexai.generative_models import GenerativeModel, SafetySetting
from vertexai.language_models import TextEmbeddingModel
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
import os
import traceback

# Initialize Vertex AI
# Ensure you have authenticated with: gcloud auth application-default login
vertexai.init(project="gcp-prj-ntpc-np-01", location="us-central1")

class ACEAgent:
    def __init__(self, model_name="gemini-1.5-flash-001"):
        """
        Initialize the ACE Agent with a Generative Model and an Embedding Model.
        """
        print(f"Initializing ACEAgent with model: {model_name}")
        self.model = GenerativeModel(model_name)
        try:
            self.embedding_model = TextEmbeddingModel.from_pretrained("text-embedding-004")
        except Exception as e:
            print("Warning: Failed to load embedding model. Deduplication might fail.")
            print(e)
            self.embedding_model = None

        self.safety_settings = [
            SafetySetting(
                category=SafetySetting.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                threshold=SafetySetting.HarmBlockThreshold.BLOCK_ONLY_HIGH
            ),
        ]

    def _call_llm(self, prompt):
        try:
            response = self.model.generate_content(
                prompt,
                safety_settings=self.safety_settings
            )
            return response.text
        except Exception as e:
            print(f"LLM Call Failed: {e}")
            raise

    def _get_embedding(self, text):
        if not self.embedding_model:
            return np.zeros(768) # Fallback / Mock
        return self.embedding_model.get_embeddings([text])[0].values

    def generator(self, product_spec_text, context_playbook):
        """
        The Generator produces the artifact (OAS) based on the input and the current context.
        """
        print(f"--- Generator Step ---")
        prompt = f"""
You are an expert API Developer.
Your task is to generate an OpenAPI Specification (OAS 3.0) in YAML format.

Input Product Specification:
{product_spec_text}

Context Playbook (Guidelines & Learned Strategies):
{context_playbook}

Instructions:
1. Analyze the Product Specification to identify resources, endpoints, and data models.
2. Apply the guidelines from the Context Playbook strictly.
3. Output ONLY the valid YAML content for the OAS.
"""
        return self._call_llm(prompt)

    def reflector(self, candidate_oas, style_guide_text):
        """
        The Reflector critiques the artifact against the ground truth or standards (Style Guide).
        """
        print(f"--- Reflector Step ---")
        prompt = f"""
You are an expert API Architect and Reviewer.
Your task is to critique the following Open API Specification (OAS) against the provided Style Guide.

Style Guide:
{style_guide_text}

Candidate OAS:
{candidate_oas}

Instructions:
1. Identify specific violations of the Style Guide in the Candidate OAS.
2. Identify any missing endpoints or data models mentioned in the Product Spec (implicit verification).
3. Provide a list of actionable insights/critiques.
4. If the OAS is perfect, reply with "NO_ISSUES".
"""
        return self._call_llm(prompt)

    def curator(self, current_playbook_text, critique_text):
        """
        The Curator updates the Context Playbook based on the Reflector's critique.
        It uses EMBEDDINGS to deduplicate new insights against the existing playbook.
        """
        print(f"--- Curator Step ---")
        if "NO_ISSUES" in critique_text:
            return current_playbook_text

        # 1. Generate NEW candidates only
        prompt = f"""
You are the Curator of the Agentic Context Engineering (ACE) system.
Reflector's Critique (Recent Failures):
{critique_text}

Instructions:
1. Based on the critique, generate a list of distinct, actionable guidelines or "lessons learned".
2. Do NOT simply restate the critique. Formulate them as imperative rules for the Generator.
3. Output EACH rule on a new line starting with "- ".
4. Do NOT output the entire playbook, ONLY the NEW rules.
"""
        try:
            new_insights_text = self._call_llm(prompt)
        except Exception:
            print("Curator failed to generate insights. Returning original.")
            return current_playbook_text
        
        # Parse text into lists
        current_items = [line.strip() for line in current_playbook_text.split('\n') if line.strip().startswith('-') or line.strip().startswith('*')]
        # Fallback if structure is loose
        if not current_items and current_playbook_text.strip():
             current_items = [current_playbook_text.strip()]

        new_items = [line.strip()[2:] for line in new_insights_text.split('\n') if line.strip().startswith('- ')]
        
        if not new_items:
            print("Curator: No new items generated.")
            return current_playbook_text

        print(f"Curator: {len(new_items)} new candidates generated.")

        # 2. Embeddings & Deduplication
        updated_playbook_items = list(current_items)
        
        if current_items and self.embedding_model:
            try:
                # Embed existing (Note: For large lists, you should batch this or cache it)
                curr_embeddings = [self._get_embedding(item) for item in current_items]
                new_embeddings = [self._get_embedding(item) for item in new_items]
                
                curr_emb_matrix = np.array(curr_embeddings)
                
                for i, new_item in enumerate(new_items):
                    new_emb_vector = np.array(new_embeddings[i]).reshape(1, -1)
                    
                    # Compute similarity against all existing
                    similarities = cosine_similarity(new_emb_vector, curr_emb_matrix)
                    max_sim = np.max(similarities)
                    
                    if max_sim > 0.85: # Threshold for "too similar"
                        print(f"Skipping duplicate item (sim={max_sim:.2f}): {new_item[:50]}...")
                    else:
                        print(f"Adding new item (sim={max_sim:.2f}): {new_item[:50]}...")
                        updated_playbook_items.append(f"- {new_item}")
                        
            except Exception as e:
                print(f"Embedding/Dedup logic failed: {e}. Appending all new items as fallback.")
                for item in new_items:
                    updated_playbook_items.append(f"- {item}")
        else:
            # No existing items or no model, just add all
            for item in new_items:
                updated_playbook_items.append(f"- {item}")

        return "\n".join(updated_playbook_items)

    def run(self, product_spec_path, style_guide_path, epochs=3):
        # Load documents
        with open(product_spec_path, 'r', encoding='utf-8', errors='ignore') as f:
            product_spec = f.read()
        
        with open(style_guide_path, 'r', encoding='utf-8', errors='ignore') as f:
            style_guide = f.read()

        context_playbook = "- Follow standard RESTful practices.\n- Ensure valid YAML output."

        final_oas = ""

        # Run loop
        for epoch in range(1, epochs + 1):
            print(f"\n=== EPOCH {epoch} ===")
            
            # 1. Generate
            final_oas = self.generator(product_spec, context_playbook)
            if not final_oas: 
                print("Generator failed to produce output.")
                break
            print("OAS Generated (length):", len(final_oas))
            
            # 2. Reflect
            critique = self.reflect(final_oas, style_guide)
            print("Critique Generated.")
            
            # Check for convergence
            if "NO_ISSUES" in critique:
                print("Converged! No issues found.")
                break

            # 3. Curate
            context_playbook = self.curator(context_playbook, critique)
            print("Context Updated.")
            
            # Debug/Preview Playbook
            # print(context_playbook)

        return final_oas

    # Wrapper 
    def reflect(self, c, s): return self.reflector(c, s)

if __name__ == "__main__":
    # Define paths
    base_dir = os.path.dirname(os.path.abspath(__file__))
    docs_dir = os.path.join(base_dir, "docs")
    
    product_spec_file = os.path.join(docs_dir, "product_spec.txt")
    style_guide_file = os.path.join(docs_dir, "style_guide.txt")
    output_file = os.path.join(base_dir, "generated_openapi.yaml")

    # Check validity
    if not os.path.exists(product_spec_file):
        print(f"Error: Could not find {product_spec_file}")
    
    # Try using Gemini Flash as default
    agent = ACEAgent(model_name="gemini-1.5-flash-001")
    
    print("Starting ACE Agent...")
    try:
        final_yaml = agent.run(product_spec_file, style_guide_file, epochs=3)
        
        with open(output_file, "w") as f:
            f.write(final_yaml)
        
        print(f"Final OAS saved to {output_file}")
    except Exception as e:
        print("Fatal Error during Execution:")
        traceback.print_exc()
        print("\nNote: Please ensure your GCP Project has Vertex AI Generative AI API enabled and you have access to the model.")
