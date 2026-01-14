import os
import yaml
import hashlib
import vertexai
from vertexai.generative_models import GenerativeModel, SafetySetting

from ace_platform.utils.chunker import PDFChunker
from ace_platform.utils.vector_store import GoogleVectorStore

PROJECT_ID = "gcp-prj-ntpc-np-01"
LOCATION = "us-central1"

class OpenAPIGeneratorPlugin:
    def __init__(self, model_name="gemini-1.5-pro", mock=False):
        self.mock = mock
        self.model_name = model_name
        self.endpoint_cache = {}
        
        # Initialize AI
        vertexai.init(project=PROJECT_ID, location=LOCATION)
        if not self.mock:
            self.model = GenerativeModel(model_name)
    
    def _call_llm(self, prompt):
        if self.mock: return "MOCK_RESPONSE"
        try:
            # Enforce Deterministic Output
            response = self.model.generate_content(
                prompt,
                generation_config={"temperature": 0}
            )
            return response.text
        except Exception as e:
            print(f"LLM Error: {e}")
            return "Error generating content."

    def ingest(self, source_path):
        """
        Reads PDF, Chunks it, Ingests into VectorStore.
        Returns the populated VectorStore as 'context'.
        """
        print(f"Plugin: Ingesting {source_path}...")
        vector_store = GoogleVectorStore(project_id=PROJECT_ID, location=LOCATION)
        
        chunker = PDFChunker()
        chunks = chunker.process_file(source_path)
        
        # Add metadata
        for c in chunks:
            c['metadata']['type'] = 'product_spec'
            
        vector_store.ingest_chunks(chunks)
        
        # Also ingest Style Guide if available (Hardcoded expectation for now)
        style_path = source_path.replace("product_spec.pdf", "style_guide.pdf")
        if os.path.exists(style_path):
             print(f"Plugin: Found Style Guide at {style_path}")
             style_chunks = chunker.process_file(style_path)
             for c in style_chunks:
                 c['metadata']['type'] = 'style_guide'
             vector_store.ingest_chunks(style_chunks)
             
        return vector_store

    def initial_playbook(self):
        playbook_path = "context_playbook.md"
        if os.path.exists(playbook_path):
             print(f"Plugin: Loading existing Context Playbook from {playbook_path}")
             with open(playbook_path, "r") as f:
                 return f.read()

        return """
# Context Playbook
- **Style Guide**: Apply all style guidelines strictly.
- **Naming**: Use kebab-case for URLs, camelCase for properties.
- **Security**: All endpoints must have OAuth2 security schemes.
- **Error Handling**: Standardize 400, 401, 403, 404, 500 responses.
"""

    def generate(self, context, playbook):
        print("Plugin: Generating OAS...")
        vector_store = context
        
        # 1. Feature Discovery
        features = self._discover_features(vector_store)
        print(f"  -> Features found: {features}")
        
        # 2. Deep Dive
        full_context, location_map = self._deep_dive_context(vector_store, features)
        
        # 3. Retrieve Style Guide
        style_rules = self._retrieve_style_guidelines(vector_store)

        # 4. Generate
        prompt = f"""
You are a Senior API Architect.
Task: Generate a comprehensive OpenAPI 3.0 Specification (YAML) for the product described below.

Input Context (Product Specs):
{full_context}

Style Guide Rules:
{style_rules}

Context Playbook (Guidelines & Learned Strategies):
{playbook}

Instructions:
1. Output ONLY valid YAML. No markdown fences.
2. Apply the Style Guide Rules and Context Playbook guidelines strictly.
3. Be EXHAUSTIVE. Include all schemas, paths, and error responses found in the text.
4. Use the gathered context to infer parameter types and descriptions.
5. **STRATEGIC SCOPING**: Do NOT generate endpoints for shared enterprise services (Authentication, User Login, Sessions, API Keys, Tenant Management). These are handled by external platform services. Focus ONLY on the CORE domain value of this specific product (e.g., Gateways, Interfaces, Routes).
6. Output begins here:

Begin OAS:
openapi: 3.0.0
"""
        return self._call_llm(prompt)

    def reflect(self, artifact, context):
        print("Plugin: Reflecting on OAS...")
        spec_yaml = artifact
        vector_store = context
        critiques = []
        
        try:
            spec = yaml.safe_load(spec_yaml)
        except Exception as e:
            return f"CRITICAL: YAML Parsing Failed: {e}"

        # 0. Completeness Check
        discovery_context = ""
        for q in ["System Capabilities", "Table of Contents"]:
             results = vector_store.search(q, k=3, filter_metadata={'type': 'product_spec'})
             for r in results: discovery_context += r['text'] + "\n"

        prompt_completeness = f"""
        You are a Product Auditor.
        Compare Generated OAS vs Product Spec.
        Spec: {discovery_context[:3000]}
        OAS Paths: {list(spec.get('paths', {}).keys())}
        Identify MISSING CORE FEATURES.
        """
        comp_critique = self._call_llm(prompt_completeness)
        if "MISSING" in comp_critique.upper():
            critiques.append(f"### Completeness:\n{comp_critique}")

        # 1. Global Review
        style_context = self._retrieve_style_guidelines(vector_store)
        global_sections = {k: v for k, v in spec.items() if k != 'paths'}
        prompt_global = f"""
        Review this OAS Global Structure against Style Guide.
        Structure: {yaml.dump(global_sections)}
        Style Guide: {style_context}
        """
        critiques.append(self._call_llm(prompt_global))

        # 2. Endpoint Review
        for path, methods in spec.get('paths', {}).items():
            for verb, operation in methods.items():
                op_yaml = yaml.dump({path: {verb: operation}})
                
                # Cache Check
                op_hash = hashlib.md5(op_yaml.encode()).hexdigest()
                if op_hash in self.endpoint_cache:
                    cached = self.endpoint_cache[op_hash]
                    if "NO_ISSUES" not in cached:
                        critiques.append(f"### {verb} {path}: {cached}")
                    continue

                prompt_ep = f"""
                Review this Endpoint against Style Guide.
                Endpoint: {op_yaml}
                Style Guide: {style_context}
                Return "NO_ISSUES" or list violations.
                """
                res = self._call_llm(prompt_ep)
                self.endpoint_cache[op_hash] = res
                if "NO_ISSUES" not in res:
                    critiques.append(f"### {verb} {path}: {res}")

        return "\n".join(critiques) if critiques else "NO_ISSUES"

    def curate(self, playbook, critique):
        print("Plugin: Curating Playbook...")
        prompt = f"""
        You are the Keeper of the Playbook.
        Current Playbook:
        {playbook}

        Recent Critique (Errors to avoid):
        {critique}

        Task:
        1. Extract specific, actionable rules from the Critique to prevent recurrence.
        2. Append them to the Playbook.
        3. Do not remove existing rules unless contradicted.
        4. Return the updated Playbook.
        """
        return self._call_llm(prompt)

    # --- Helper Methods ---
    def _discover_features(self, vector_store):
        results = vector_store.search("System Capabilities, high level modules", k=5, filter_metadata={'type': 'product_spec'})
        text = "\n".join([r['text'] for r in results])
        prompt = f"Extract list of core feature names from:\n{text}"
        return self._call_llm(prompt)

    def _deep_dive_context(self, vector_store, features):
        full_context = ""
        loc_map = {}
        for feat in features.split(','):
            feat = feat.strip()
            if not feat: continue
            
            # Deep Dive with Reranking
            # Use Reranker (rerank=True) to ensure the 15 chunks are actually relevant
            results = vector_store.search(
                f"Detailed API specifications, endpoints, data models and errors for {feat}", 
                k=15, 
                filter_metadata={'type': 'product_spec'},
                rerank=True
            )
            

            
            # "Bell Curve" Reordering (Lost in the Middle optimization)
            reordered = [None] * len(results)
            left, right = 0, len(results) - 1
            for i, item in enumerate(results):
                if i % 2 == 0:
                    reordered[left] = item
                    left += 1
                else:
                    reordered[right] = item
                    right -= 1
            
            for r in reordered:
                if r is None: continue
                full_context += f"--- Context for {feat} ---\n{r['text']}\n"
        return full_context, loc_map

    def _retrieve_style_guidelines(self, vector_store):
        results = vector_store.get_all_by_metadata({'type': 'style_guide'})
        return "\n".join([r['text'] for r in results])
