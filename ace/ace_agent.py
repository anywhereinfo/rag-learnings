import hashlib

import vertexai
from vertexai.language_models import TextGenerationModel, TextEmbeddingModel
from vertexai.generative_models import GenerativeModel, SafetySetting
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
import yaml
import os
import traceback

# Import utilities
from utils.chunker import PDFChunker
from utils.vector_store import GoogleVectorStore

# Initialize Vertex AI
# Ensure you have authenticated with: gcloud auth application-default login
PROJECT_ID = "gcp-prj-ntpc-np-01"
LOCATION = "us-central1"
vertexai.init(project=PROJECT_ID, location=LOCATION)

class ACEAgent:
    def __init__(self, model_name="gemini-1.5-pro", mock=False):
        """
        Initialize the ACE Agent with a Generative Model and Vector Store.
        """
        self.mock = mock
        print(f"Initializing ACEAgent with model: {model_name} (Mock: {mock})")
        
        # Initialize Vector Store (RAG)
        self.vector_store = GoogleVectorStore(project_id=PROJECT_ID, location=LOCATION)
        
        # Cache for Reflector (Optimization)
        self.endpoint_cache = {}
        
        if not self.mock:
            self.model = GenerativeModel(model_name)
        else:
            self.model = None
        
        self.safety_settings = [
            SafetySetting(
                category=SafetySetting.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                threshold=SafetySetting.HarmBlockThreshold.BLOCK_ONLY_HIGH
            ),
        ]

    def _call_llm(self, prompt):
        print(f"   Debug: Calling LLM (Length of prompt: {len(prompt)})...")
        if self.mock:
            # Heuristic Mock Responses for Demo/Testing
            if "openapi" in prompt.lower() or "generate" in prompt.lower():
                return """```yaml
openapi: 3.0.0
info:
  title: Mock Generated API
  version: 1.0.0
paths:
  /users:
    get:
      summary: List Users
      operationId: listUsers
      responses:
        '200':
          description: OK
  /users/{id}:
    get:
      summary: Get User
      operationId: getUser
      responses:
        '200':
          description: OK
```"""
            elif "critique" in prompt.lower() and "review" in prompt.lower():
                return "Critique: The path `/users/{id}` is missing a 404 Not Found error response, which is required by the Style Guide for resource lookups."
            elif "insight" in prompt.lower() or "playbook" in prompt.lower():
                return "- Ensure all resource lookup endpoints include a 404 Error response."
            else:
                return "MOCK RESPONSE: No Issues Found."

        try:
            start_t = __import__('time').time()
            response = self.model.generate_content(
                prompt,
                safety_settings=self.safety_settings,
                generation_config={"temperature": 0}
            )
            print(f"   Debug: LLM Response received in {round(__import__('time').time() - start_t, 2)}s")
            return response.text
        except Exception as e:
            print(f"LLM Call Failed: {e}")
            raise

    def build_knowledge_base(self, product_spec_path, style_guide_path):
        """
        Ingest PDFs into the Vector Store.
        """
        if self.vector_store.load_local():
            print("Skipping ingestion (loaded from cache).")
            return

        # We pass self.model (Gemini) to the chunker for Image Captioning
        chunker = PDFChunker(chunk_size=1500, overlap=200, image_model=self.model)
        
        print("Chunking Product Spec (including images)...")
        ps_chunks = chunker.extract_text_with_metadata(product_spec_path)
        # Tag them
        for c in ps_chunks: c['metadata']['type'] = 'product_spec'
        
        print("Chunking Style Guide...")
        sg_chunks = chunker.extract_text_with_metadata(style_guide_path)
        for c in sg_chunks: c['metadata']['type'] = 'style_guide'
        
        # Ingest
        all_chunks = ps_chunks + sg_chunks
        self.vector_store.ingest_chunks(all_chunks)
        self.vector_store.save_local()
        print(f"Knowledge Base built with {len(all_chunks)} chunks.")

    def generator(self, context_playbook):
        """
        The Generator produces the artifact (OAS) using RAG-retrieved context.
        Uses a robust 2-pass discovery mechanism.
        """
        print(f"--- Generator Step ---")
        
        # Pass 1: Discover High-Level Features
        print("   Pass 1: Discovering API Features from Product Spec...")
        features = self._discover_features(context_playbook)
        print(f"   Features identified: {features}")

        # Pass 2: Deep Dive into each Feature
        print("   Pass 2: Deep Diving into Features...")
        detailed_context, location_map = self._deep_dive_context(features)
        
        # Pass 3: Retrieve Style Guide Rules
        print("   Pass 3: Retrieving Style Guide Rules...")
        style_context = self._retrieve_style_guidelines()

        print(f"   Context retrieved: Product Spec ({len(detailed_context)} chars), Style Guide ({len(style_context)} chars). Generating OAS...")

        prompt = f"""
You are an expert API Developer.
Your task is to generate an OpenAPI Specification (OAS 3.0) in YAML format.

Retrieved Product Specification Context:
{detailed_context}

Retrieved Style Guide Rules:
{style_context}

Context Playbook (Guidelines & Learned Strategies):
{context_playbook}

Instructions:
1. Synthesize the retrieved product information into a cohesive OAS.
2. Apply the Style Guide Rules and Context Playbook guidelines strictly.
3. If information is missing, use standard industry placeholders (e.g., "description: To be defined").
4. **STRATEGIC SCOPING**: Do NOT generate endpoints for shared enterprise services (Authentication, User Login, Sessions, API Keys, Tenant Management). These are handled by external platform services. Focus ONLY on the CORE domain value of this specific product.
5. Output ONLY the valid YAML content.
"""
        return self._clean_output(self._call_llm(prompt)), location_map

    def _retrieve_style_guidelines(self):
        """
        Retrieve ALL design rules from the assigned Style Guide.
        """
        results = self.vector_store.get_all_by_metadata({'type': 'style_guide'})
        context = ""
        for r in results:
             context += f"---\nRule Source (Pg {r['metadata'].get('pages', '?')}): {r['text']}\n"
        return context

    def _clean_output(self, text):
        clean = text.strip()
        if clean.startswith("```yaml"):
            clean = clean[7:]
        elif clean.startswith("```"):
            clean = clean[3:]
        if clean.endswith("```"):
            clean = clean[:-3]
        return clean.strip()

    def _discover_features(self, context_playbook):
        """
        Query the Vector Store for high-level Table of Contents or Feature lists.
        """
        # 1. Broad Search (fallback)
        discovery_queries = [
            "Table of Contents High Level Features",
            "List of System Capabilities and Modules",
            "API Service Overview"
        ]
        
        context = ""
        for q in discovery_queries:
            results = self.vector_store.search(q, k=5, filter_metadata={'type': 'product_spec'})
            for r in results:
                context += r['text'] + "\n"
        
        # Ask LLM to extract list
        prompt = f"""
        You are an Enterprise Architect.
        Analyze the Product Spec text below and identify the CORE DOMAIN features.
        
        CRITICAL SCOPE RULES:
        1. EXCLUDE Shared Enterprise Services (e.g., Authentication, SSO, User Onboarding, Tenant Management). These are handled by external systems.
        2. EXCLUDE Infrastructure concerns (e.g., Logging, Monitoring, Keys).
        3. FOCUS ONLY on the specific business value drivers of this product (e.g., "Orders", "Inventory", "Shipments").

        Text:
        {context[:15000]}

        Return ONLY a comma-separated list of included nouns.
        """
        try:
             response = self._call_llm(prompt)
             # Removing any "feature:" prefix if LLM adds it
             return response.replace("Features:", "").strip()
        except:
            return "General API Resources"

    def _deep_dive_context(self, features_list):
        """
        For each feature, perform targeted RAG.
        Returns context string AND a map of {feature: [pages]}
        """
        retrieved_context = ""
        location_map = {}
        
        features = [f.strip() for f in features_list.split(',')]
        
        # Limit to top 5 to avoid blowing up context window too much in demo
        for feature in features[:5]: 
            location_map[feature] = []
            # Deep Dive for specific feature logic
            # Use Reranker (rerank=True) to ensure the 15 chunks are actually relevant
            results = self.vector_store.search(
                f"Detailed API specifications, endpoints, data models and errors for {feature}", 
                k=15, 
                filter_metadata={'type': 'product_spec'},
                rerank=True
            )

            
            # "Bell Curve" Reordering (Lost in the Middle optimization)
            # Places best chunks at Start and End of context window
            # Input (Sorted): [0(Best), 1, 2, 3, 4(Worst)]
            # Output: [0, 2, 4, 3, 1]
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
                if r is None: continue # Safety check
                # Deduplicate by simple string check
                if r['text'] not in retrieved_context:
                        # Extract pages
                        pages = r['metadata'].get('pages', [])
                        if isinstance(pages, list):
                            location_map[feature].extend(pages)
                        elif isinstance(pages, int):
                            location_map[feature].append(pages)
                            
                        retrieved_context += f"---\n[Context for {feature}]: (Pg {pages})\n{r['text']}\n"
        
        return retrieved_context, location_map

    def reflector(self, candidate_oas):
        """
        The Reflector critiques the artifact using RAG-retrieved Style Guide rules and Industry Best Practices.
        Performs:
        1. Global Structure Review
        2. Per-Endpoint Detailed Review
        """
        print(f"--- Reflector Step ---")
        
        try:
            spec = yaml.safe_load(candidate_oas)
        except yaml.YAMLError as e:
            return f"CRITICAL: generated OAS is not valid YAML. Error: {e}"

        critiques = []

        # --- 0. Completeness Review (Did we miss entire features?) ---
        print("Reflector: performing Completeness Review...")
        # Re-run high-level discovery to get the "Truth" of what should be there
        discovery_context = ""
        discovery_queries = ["System Capabilities", "Table of Contents"]
        for q in discovery_queries:
             results = self.vector_store.search(q, k=3, filter_metadata={'type': 'product_spec'})
             for r in results: discovery_context += r['text'] + "\n"

        prompt_completeness = f"""
        You are a Product Auditor.
        Compare the generated OAS against the Product Spec overview.
        
        Product Spec Overview:
        {discovery_context[:5000]}
        
        Generated OAS Tags/Resources:
        {list(spec.get('paths', {}).keys())}
        
        Instructions:
        1. Identify PRIMARY domain entities mentioned in the text (e.g., "Users", "Orders").
        2. Check if they exist in the OAS paths.
        3. If a CORE feature is missing, report it as a CRITICAL ISSUE.
        4. Ignore ignored scopes (Auth, Logging).
        """
        completeness_critique = self._call_llm(prompt_completeness)
        if "MISSING" in completeness_critique.upper() or "CRITICAL" in completeness_critique.upper():
             critiques.append(f"### Missing Features:\n{completeness_critique}")

        # --- 1. Global Review ---
        print("Reflector: performing Global Review...")
        global_sections = {k: v for k, v in spec.items() if k != 'paths'}
        global_yaml = yaml.dump(global_sections)
        
        # Retrieve ALL Style Rules
        style_context = self._retrieve_style_guidelines()

        prompt_global = f"""
You are an expert API Architect.
Critique the GLOBAL sections of this OAS (Info, Servers, Components, Security) against the Style Guide.

Style Guide Context:
{style_context}

Global OAS Sections:
{global_yaml}

Instructions:
1. Check Versioning strategy.
2. Check Base URL/Servers formatting.
3. Check Security Definitions.
4. Check reuse of Components/Schemas.
5. Return "NO_ISSUES" if perfect, otherwise bullet points of issues.
"""
        global_critique = self._call_llm(prompt_global)
        if "NO_ISSUES" not in global_critique:
            critiques.append(f"### Global Issues:\n{global_critique}")

        # --- 2. Per-Endpoint Review ---
        print("Reflector: performing Per-Endpoint Review...")
        paths = spec.get('paths', {})
        
        # Reuse ALL Style Rules (already retrieved above as style_context)
        # We pass the same comprehensive context to ensure consistency.

        
        # Iterate
        for path, methods in paths.items():
            for verb, operation in methods.items():
                print(f"  - Reviewing {verb.upper()} {path}...")
                op_yaml = yaml.dump({path: {verb: operation}})
                
                # OPTIMIZATION: Check Cache
                op_hash = hashlib.md5(op_yaml.encode()).hexdigest()
                if op_hash in self.endpoint_cache:
                    print(f"    -> Cache Hit! Skipping LLM review for unchanged endpoint.")
                    cached_val = self.endpoint_cache[op_hash]
                    if "NO_ISSUES" not in cached_val:
                         critiques.append(f"### Issue in {verb.upper()} {path}:\n{cached_val}")
                    continue

                prompt_endpoint = f"""
You are a code reviewer focusing on API Design.
Critique this SPECIFIC endpoint against standards.

Style Guide Rules (Naming, Verbs, Codes, Errors):
{style_context}

Endpoint Definition:
{op_yaml}

Instructions:
1. Verify **Naming Conventions** (URL construction, parameter names).
2. Verify **Verb Usage** (GET vs POST vs PUT appropriateness).
3. Verify **Status Codes** (Success, Errors, are they standard?).
4. Verify **Error Structure** (Does it return standard error objects?).
5. Return "NO_ISSUES" if compliant. Otherwise, provide actionable fixes.
"""
                op_critique = self._call_llm(prompt_endpoint)
                
                # Update Cache
                self.endpoint_cache[op_hash] = op_critique
                
                if "NO_ISSUES" not in op_critique:
                     critiques.append(f"### Issue in {verb.upper()} {path}:\n{op_critique}")

        if not critiques:
            return "NO_ISSUES"
        
        return "\n\n".join(critiques)

    def curator(self, current_playbook_text, critique_text):
        """
        The Curator updates the Context Playbook based on the Reflector's critique.
        """
        print(f"--- Curator Step ---")
        if "NO_ISSUES" in critique_text:
            return current_playbook_text

        prompt = f"""
You are the Curator of the Agentic Context Engineering (ACE) system.
Reflector's Critique (Recent Failures):
{critique_text}

Instructions:
1. Based on the critique, generate a list of distinct, actionable guidelines.
2. Formulate them as imperative rules.
3. Output EACH rule on a new line starting with "- ".
4. Do NOT output the entire playbook, ONLY the NEW rules.
"""
        try:
            new_insights_text = self._call_llm(prompt)
        except Exception:
            return current_playbook_text
        
        new_items = [line.strip()[2:] for line in new_insights_text.split('\n') if line.strip().startswith('- ')]
        
        if not new_items:
            return current_playbook_text

        # Deduplication (using existing vector store)
        updated_playbook_items = [line.strip() for line in current_playbook_text.split('\n') if line.strip().startswith('-')]
        if not updated_playbook_items: updated_playbook_items = [current_playbook_text.strip()]

        print(f"Curator: Processing {len(new_items)} new candidates...")
        
        for new_item in new_items:
            # Embed NEW item
            new_emb = self.vector_store.embed_text(new_item)
            is_dupe = False
            
            # Compare against existing Playbook (brute force for now, playbook is small)
            for existing in updated_playbook_items:
                ex_emb = self.vector_store.embed_text(existing)
                sim = cosine_similarity([new_emb], [ex_emb])[0][0]
                if sim > 0.85:
                    is_dupe = True
                    break
            
            if not is_dupe:
                updated_playbook_items.append(f"- {new_item}")
            else:
                print(f"Skipped duplicate: {new_item[:30]}...")

        return "\n".join(updated_playbook_items)

    def run(self, product_spec_path, style_guide_path, epochs=6):
        # 1. Build Knowledge Base (RAG)
        self.build_knowledge_base(product_spec_path, style_guide_path)

        if os.path.exists("ace/context_playbook.md"):
            with open("ace/context_playbook.md", "r") as f:
                context_playbook = f.read()
            print("Loaded existing Context Playbook from disk.")
        else:
            context_playbook = "- Follow standard RESTful practices.\n- Ensure valid YAML output."
        final_oas = ""
        previous_critique_len = 0

        # Run loop
        for epoch in range(1, epochs + 1):
            print(f"\n=== EPOCH {epoch} ===")
            
            # 2. Generate (with RAG)
            final_oas, _ = self.generator(context_playbook)
            if not final_oas: break
            
            # 3. Reflect (with RAG)
            critique = self.reflect(final_oas)
            print("Critique Generated.")
            
            # Check for convergence
            if "NO_ISSUES" in critique:
                print("Converged! No issues found.")
                break

            # Quantitative Convergence Check
            critique_len = len(critique)
            print(f"   Critique Length: {critique_len} chars")
            
            if previous_critique_len > 0:
                improvement = (previous_critique_len - critique_len) / previous_critique_len
                print(f"   Improvement vs last epoch: {round(improvement*100, 1)}%")
                
                # Only stop if improvement is POSITIVE but small (0-5%)
                # If negative (getting worse) or large (>5%), keep going
                if 0 < improvement < 0.05:
                    print("   !! Diminishing returns detected (0-5% improvement). Stopping early.")
                    break
                elif improvement <= 0:
                    print("   !! Critique size INCREASED. Agent needs more training - continuing...")
            
            previous_critique_len = critique_len

            # 4. Curate (with Dedup)
            context_playbook = self.curator(context_playbook, critique)
            
            # Metrics
            playbook_rules_count = len([line for line in context_playbook.split('\n') if line.strip().startswith('-')])
            print(f"   [Epoch {epoch} Stats]: Critique Size={critique_len} chars | Playbook Rules={playbook_rules_count}")
            print("Context Updated.")

        return final_oas, context_playbook, previous_critique_len

    def reflect(self, c): return self.reflector(c)

if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    docs_dir = os.path.join(base_dir, "docs")
    
    product_spec_file = os.path.join(docs_dir, "product_spec.pdf") # Now preferring PDF
    style_guide_file = os.path.join(docs_dir, "style_guide.pdf") # Now preferring PDF
    output_file = os.path.join(base_dir, "generated_openapi.yaml")
    playbook_file = os.path.join(base_dir, "context_playbook.md")

    # Check validity
    if not os.path.exists(product_spec_file):
        print(f"Error: Could not find {product_spec_file}")
    
    agent = ACEAgent(model_name="gemini-2.5-pro", mock=False)
    
    print("Starting ACE Agent...")
    try:
        final_yaml, final_playbook, previous_critique_len = agent.run(product_spec_file, style_guide_file, epochs=3)
        
        with open(output_file, "w") as f:
            f.write(final_yaml)
        print(f"Final OAS saved to {output_file}")

        with open(playbook_file, "w") as f:
            f.write(final_playbook)
        print(f"Final Context Playbook saved to {playbook_file}")
        
        # Final Verification
        final_rules = len([l for l in final_playbook.split('\n') if l.strip().startswith('-')])
        print(f"\n=== FINAL SUMMARY ===")
        print(f"Total Rules Learned: {final_rules}")
        if agent.mock == False and previous_critique_len > 500:
            print(f"WARNING: Final Critique Size is still high ({previous_critique_len} chars).")
            print("Recommendation: Increase 'epochs' to give the Agent more time to self-correct.")
        print(f"Run Complete.")

    except Exception as e:
        print("Fatal Error:")
        traceback.print_exc()
