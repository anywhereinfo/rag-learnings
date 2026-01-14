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


        # Format playbook for maximum LLM attention
        formatted_playbook = self._format_playbook_for_prompt(context_playbook)

        print(f"   Context retrieved: Product Spec ({len(detailed_context)} chars), Style Guide ({len(style_context)} chars). Generating OAS...")

        prompt = f"""
You are an expert API Developer generating OpenAPI Specifications.

[OUTPUT FORMAT]
Output ONLY valid YAML. No markdown fences, no explanations.

[PRODUCT SPECIFICATION]
{detailed_context}

[STYLE GUIDE - AUTHORITATIVE RULES]
{style_context}

[⚠️ CRITICAL REMINDERS - RULES YOU FREQUENTLY MISS]
The following are NOT new rules. They are specific Style Guide rules that 
you have historically failed to apply correctly in previous epochs. 
Pay EXTRA attention to these:

{formatted_playbook}

[STRATEGIC SCOPING]
Do NOT generate endpoints for shared enterprise services (Authentication, User Login, 
Sessions, API Keys, Tenant Management). These are handled by external platform services. 
Focus ONLY on the CORE domain value of this specific product.

[FINAL INSTRUCTION - SELF-CHECK BEFORE OUTPUT]
Before outputting your OpenAPI Specification:
1. Review it against the Critical Reminders above
2. Verify you haven't repeated past mistakes (check examples if provided)
3. If the playbook includes a checklist, mentally verify each item
4. Ensure all naming conventions match the emphasized patterns

Generate the OpenAPI Specification now:
"""
        return self._clean_output(self._call_llm(prompt)), location_map


    def _parse_playbook_sections(self, playbook: str) -> dict:
        """
        Parse the playbook into structured sections based on headers.
        Returns dict with section names as keys and content lines as values.
        """
        sections = {}
        current_section = None
        current_content = []
        
        for line in playbook.split('\n'):
            line_stripped = line.strip()
            
            # Detect section headers
            if '🚨 CRITICAL' in line_stripped or 'CRITICAL' in line_stripped.upper():
                if current_section and current_content:
                    sections[current_section] = current_content
                current_section = 'FREQUENTLY_MISSED'
                current_content = []
            elif '⚠️ MODERATE' in line_stripped or 'MODERATE' in line_stripped.upper():
                if current_section and current_content:
                    sections[current_section] = current_content
                current_section = 'PARTIALLY_MISSED'
                current_content = []
            elif '📋' in line_stripped and 'CHECKLIST' in line_stripped.upper():
                if current_section and current_content:
                    sections[current_section] = current_content
                current_section = 'CHECKLIST'
                current_content = []
            elif '📌' in line_stripped or 'EDGE' in line_stripped.upper():
                if current_section and current_content:
                    sections[current_section] = current_content
                current_section = 'EDGE_CASES'
                current_content = []
            elif current_section and line_stripped:
                # Add content to current section
                current_content.append(line)
        
        # Add final section
        if current_section and current_content:
            sections[current_section] = current_content
        
        # Fallback: if no sections detected, treat entire playbook as FREQUENTLY_MISSED
        if not sections and playbook.strip():
            sections['FREQUENTLY_MISSED'] = playbook.split('\n')
        
        return sections

    def _format_playbook_for_prompt(self, playbook: str) -> str:
        """
        Format the context playbook to maximize LLM attention.
        Parses structured sections and presents them with visual emphasis.
        """
        if not playbook or not playbook.strip():
            return "- Follow standard RESTful practices.\n- Ensure valid YAML output."
        
        sections = self._parse_playbook_sections(playbook)
        
        formatted = "=== CRITICAL REMINDERS (Rules You Often Miss) ===\n\n"
        
        if 'FREQUENTLY_MISSED' in sections:
            formatted += "🚨 HIGH PRIORITY - You miss these >80% of the time:\n"
            formatted += "\n".join(sections['FREQUENTLY_MISSED'])
            formatted += "\n\n"
        
        if 'PARTIALLY_MISSED' in sections:
            formatted += "⚠️ MEDIUM PRIORITY - You sometimes miss these:\n"
            formatted += "\n".join(sections['PARTIALLY_MISSED'])
            formatted += "\n\n"
        
        if 'EDGE_CASES' in sections:
            formatted += "📌 EDGE CASES - Don't forget:\n"
            formatted += "\n".join(sections['EDGE_CASES'])
            formatted += "\n\n"
        
        if 'CHECKLIST' in sections:
            formatted += "✅ FINAL CHECKLIST - Validate before output:\n"
            formatted += "\n".join(sections['CHECKLIST'])
        
        return formatted.strip()


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
        Enhanced Curator with conflict detection and Style Guide validation.
        Multi-layered approach:
        1. Extract rule candidates from critique
        2. Validate against Style Guide (prevent contradictions)
        3. Detect conflicts with existing playbook
        4. Resolve conflicts intelligently
        5. Deduplicate semantically
        """
        print(f"--- Curator Step (Enhanced) ---")
        if "NO_ISSUES" in critique_text:
            return current_playbook_text

        # Step 1: Extract new rule candidates
        new_rule_candidates = self._extract_rule_candidates_simple(critique_text)
        
        if not new_rule_candidates:
            return current_playbook_text
        
        # Step 2: Validate against Style Guide
        validated_rules = self._validate_against_style_guide(new_rule_candidates)
        
        # Step 3: Detect and resolve conflicts
        conflict_free_rules = self._detect_and_resolve_conflicts(
            validated_rules,
            current_playbook_text
        )
        
        # Step 4: Merge with semantic deduplication
        updated_playbook = self._merge_rules_with_deduplication(
            current_playbook_text,
            conflict_free_rules
        )
        
        return updated_playbook
    
    def _extract_rule_candidates_simple(self, critique_text):
        """
        Extract actionable rules from Reflector's critique.
        Returns list of dict with 'rule', 'context', 'pattern' keys.
        """
        prompt = f"""
You are the Curator of an API Standards Learning System.

Reflector's Critique (violations found in generated OAS):
{critique_text}

Instructions:
1. Extract SPECIFIC, ACTIONABLE rules that would prevent these violations
2. Frame each as an imperative statement (e.g., "Use camelCase for operationId")
3. Output EACH rule on a new line starting with "- "
4. Do NOT output the entire playbook, ONLY the NEW rules

Output:
"""
        
        try:
            response = self._call_llm(prompt)
            rules = []
            for line in response.split('\n'):
                if line.strip().startswith('- '):
                    rule_text = line.strip()[2:]
                    rules.append({
                        'rule': rule_text,
                        'context': self._infer_context_from_rule(rule_text),
                        'pattern': 'see rule text'
                    })
            print(f"Curator: Extracted {len(rules)} rule candidates")
            return rules
        except Exception as e:
            print(f"Curator: Failed to extract rules: {e}")
            return []
    
    def _infer_context_from_rule(self, rule_text):
        """Infer what the rule applies to from its text."""
        rule_lower = rule_text.lower()
        
        if 'operationid' in rule_lower:
            return 'operationId'
        elif 'parameter' in rule_lower or 'path' in rule_lower:
            return 'parameters'
        elif 'response' in rule_lower:
            return 'responses'
        elif 'schema' in rule_lower or 'component' in rule_lower:
            return 'schemas'
        elif 'etag' in rule_lower or 'header' in rule_lower:
            return 'headers'
        elif 'delete' in rule_lower:
            return 'delete_operations'
        else:
            return 'general'
    
    def _validate_against_style_guide(self, rule_candidates):
        """
        Validate that new rules align with (don't contradict) the Style Guide.
        """
        if not rule_candidates:
            return []
        
        print(f"Curator: Validating {len(rule_candidates)} candidates against Style Guide...")
        
        # Retrieve relevant Style Guide sections
        style_context = self._retrieve_style_guidelines()
        
        validated = []
        for candidate in rule_candidates:
            prompt = f"""
You are a Standards Compliance Validator.

AUTHORITATIVE STYLE GUIDE (excerpt):
{style_context[:8000]}

PROPOSED NEW RULE (from learning system):
{candidate['rule']}

Task:
Check if this proposed rule ALIGNS with or CONTRADICTS the Style Guide.

Output one of:
- "VALID" if it aligns/reinforces the Style Guide
- "CONTRADICTION" if it contradicts any Style Guide rule
- "NOT_COVERED" if Style Guide is silent on this topic

Output format: Just the status word.
"""
            
            try:
                validation_result = self._call_llm(prompt).strip().upper()
                
                if "VALID" in validation_result:
                    validated.append(candidate)
                    print(f"  ✓ Validated: {candidate['rule'][:60]}...")
                elif "CONTRADICTION" in validation_result:
                    print(f"  ✗ REJECTED (contradicts Style Guide): {candidate['rule'][:60]}...")
                elif "NOT_COVERED" in validation_result:
                    # New rule for something Style Guide doesn't address - accept it
                    validated.append(candidate)
                    print(f"  ? Accepted (not in Style Guide): {candidate['rule'][:60]}...")
                else:
                    # Unclear response, be conservative and accept
                    validated.append(candidate)
                    
            except Exception as e:
                print(f"  ! Validation failed for rule, accepting anyway: {e}")
                validated.append(candidate)
                continue
        
        print(f"Curator: {len(validated)}/{len(rule_candidates)} rules validated")
        return validated
    
    def _detect_and_resolve_conflicts(self, new_rules, existing_playbook):
        """
        Detect conflicts between new rules and existing playbook rules.
        Resolve by keeping the MOST SPECIFIC or MOST RECENT rule.
        """
        if not new_rules:
            return []
        
        print(f"Curator: Checking for conflicts with existing playbook...")
        
        existing_rules = self._parse_existing_playbook(existing_playbook)
        
        conflict_free = []
        conflicts_detected = 0
        
        for new_rule in new_rules:
            has_conflict = False
            
            for existing_rule in existing_rules:
                # Quick heuristic: skip if contexts are completely different
                if new_rule['context'] != existing_rule['context'] and \
                   new_rule['context'] != 'general' and \
                   existing_rule['context'] != 'general':
                    continue
                
                # Check for semantic conflict
                conflict_check = self._check_rule_conflict(new_rule, existing_rule)
                
                if conflict_check['has_conflict']:
                    has_conflict = True
                    conflicts_detected += 1
                    
                    # Resolve: prefer new rule (it reflects recent issues)
                    print(f"  ! Conflict detected:")
                    print(f"    Existing: {existing_rule['rule'][:50]}...")
                    print(f"    New: {new_rule['rule'][:50]}...")
                    print(f"    Resolution: Replacing with new rule (more recent)")
                    
                    # Mark existing rule for removal
                    existing_rule['_remove'] = True
                    conflict_free.append(new_rule)
                    break
            
            if not has_conflict:
                conflict_free.append(new_rule)
        
        if conflicts_detected > 0:
            print(f"Curator: Resolved {conflicts_detected} conflicts")
        
        return conflict_free
    
    def _parse_existing_playbook(self, playbook_text):
        """Parse existing playbook into structured rules."""
        rules = []
        for line in playbook_text.split('\n'):
            line = line.strip()
            if line.startswith('- '):
                rule_text = line[2:]
                rules.append({
                    'rule': rule_text,
                    'context': self._infer_context_from_rule(rule_text),
                    'original_line': line
                })
        return rules
    
    def _check_rule_conflict(self, new_rule, existing_rule):
        """
        Use LLM to detect if two rules conflict.
        """
        prompt = f"""
You are a Logic Validator.

Rule A (existing): {existing_rule['rule']}
Rule B (new): {new_rule['rule']}

Question: Do these rules CONTRADICT each other?

Two rules contradict if:
- They apply to the same thing but prescribe opposite actions
- Following both simultaneously is impossible
- Example: "Use snake_case for X" vs "Use camelCase for X"

Output ONLY:
- "NO_CONFLICT" if they can coexist
- "CONFLICT" if they contradict
"""
        
        try:
            result = self._call_llm(prompt).strip().upper()
            
            if "CONFLICT" in result and "NO_CONFLICT" not in result:
                return {'has_conflict': True, 'reason': 'contradictory rules'}
            else:
                return {'has_conflict': False, 'reason': 'compatible'}
                
        except Exception as e:
            print(f"  ! Conflict check failed: {e}")
            # Conservative: assume no conflict if check fails
            return {'has_conflict': False, 'reason': 'check_failed'}
    
    def _merge_rules_with_deduplication(self, existing_playbook, new_rules):
        """
        Merge new rules with existing playbook, with semantic deduplication.
        """
        # Parse existing playbook
        existing_rules = self._parse_existing_playbook(existing_playbook)
        
        # Remove rules marked for deletion (from conflict resolution)
        existing_rules = [r for r in existing_rules if not r.get('_remove', False)]
        
        # Convert to text format
        merged_lines = [f"- {r['rule']}" for r in existing_rules]
        
        # Add new rules with semantic deduplication
        print(f"Curator: Merging {len(new_rules)} new rules with deduplication...")
        added_count = 0
        
        for new_rule in new_rules:
            new_text = new_rule['rule']
            new_emb = self.vector_store.embed_text(new_text)
            
            is_duplicate = False
            for existing_rule in existing_rules:
                existing_text = existing_rule['rule']
                existing_emb = self.vector_store.embed_text(existing_text)
                
                similarity = cosine_similarity([new_emb], [existing_emb])[0][0]
                
                if similarity > 0.85:
                    is_duplicate = True
                    print(f"  Skipped duplicate: {new_text[:50]}...")
                    break
            
            if not is_duplicate:
                merged_lines.append(f"- {new_text}")
                added_count += 1
                print(f"  + Added: {new_text[:60]}...")
        
        print(f"Curator: Added {added_count} new rules to playbook")
        return "\n".join(merged_lines)

    def validate_playbook_consistency(self, playbook_text: str) -> str:
        """
        Validate playbook with INCREMENTAL verification.
        Only checks conflicts for rules NOT in the verified manifest (verified_rules.json).
        """
        import json
        
        print("\n" + "="*60)
        print("PLAYBOOK CONSISTENCY VALIDATION (INCREMENTAL)")
        print("="*60)
        
        # Parse existing playbook
        rules = self._parse_existing_playbook(playbook_text)
        if not rules:
            print("⚠ No rules found in playbook, skipping validation")
            return playbook_text
            
        # Load Verified Manifest
        verified_hashes = set()
        manifest_path = "ace/verified_rules.json"
        
        # Also try absolute path if needed
        if not os.path.exists(manifest_path):
             manifest_path = os.path.join(os.getcwd(), "ace", "verified_rules.json")

        if os.path.exists(manifest_path):
            try:
                with open(manifest_path, 'r') as f:
                    verified_hashes = set(json.load(f))
                print(f"✓ Loaded {len(verified_hashes)} verified rule hashes.")
            except Exception as e:
                print(f"⚠ Could not load manifest: {e}")

        # Identify New vs Verified Rules
        new_rules = []
        known_rules = []
        
        for rule in rules:
            rule_hash = hashlib.md5(rule['rule'].encode('utf-8')).hexdigest()
            rule['hash'] = rule_hash
            if rule_hash in verified_hashes:
                known_rules.append(rule)
            else:
                new_rules.append(rule)
        
        if not new_rules:
            print("✓ All rules verified in manifest. Skipping conflict check.")
            return playbook_text

        print(f"🔍 Validating {len(new_rules)} NEW rules against {len(known_rules)} existing rules...")

        # 1. Validate New Rules against Style Guide
        # (Assuming verified rules are already style-compliant)
        try:
            style_guide_rules = self._validate_against_style_guide(new_rules)
            if len(style_guide_rules) < len(new_rules):
                diff = len(new_rules) - len(style_guide_rules)
                print(f"✂️ Removed {diff} new rules that contradicted Style Guide.")
                new_rules = style_guide_rules
        except Exception as e:
            print(f"⚠ Style check failed: {e}")

        # 2. Detect Conflicts (Incremental)
        # We need to check:
        # A. New vs New
        # B. New vs Verified
        
        conflicts = []
        conflicts_detected = 0
        
        # We only need to iterate over NEW rules as the 'primary' check, 
        # comparing them against EVERYONE else (new + known).
        
        for i, rule_a in enumerate(new_rules):
            # Compare with other NEW rules (forward only to avoid double counting)
            for j, rule_b in enumerate(new_rules[i+1:], start=i+1):
                conflict = self._check_pair_incremental(rule_a, rule_b)
                if conflict:
                    conflicts.append(conflict)
                    conflicts_detected += 1
            
            # Compare with ALL KNOWN rules
            for rule_b in known_rules:
                conflict = self._check_pair_incremental(rule_a, rule_b)
                if conflict:
                    conflicts.append(conflict)
                    conflicts_detected += 1

        if conflicts_detected == 0:
            print("✓ No conflicts detected.")
            # Update manifest
            all_hashes = [r['hash'] for r in new_rules + known_rules]
            with open(manifest_path, 'w') as f:
                json.dump(all_hashes, f)
            print("✓ Updated verified_rules.json")
            return playbook_text 

        # Prune conflicts
        print(f"\n✂️ Pruning {conflicts_detected} conflicts...")
        rules_to_remove = set()
        
        for rule_a, rule_b, reason in conflicts:
            # Prefer keeping known rules over new rules (stability)
            hash_a_verified = rule_a['hash'] in verified_hashes
            hash_b_verified = rule_b['hash'] in verified_hashes
            
            if hash_a_verified and not hash_b_verified:
                rules_to_remove.add(rule_b['rule'])
                print(f"  ✂️ Removing (new conflicting with verified): {rule_b['rule'][:40]}...")
            elif hash_b_verified and not hash_a_verified:
                rules_to_remove.add(rule_a['rule'])
                print(f"  ✂️ Removing (new conflicting with verified): {rule_a['rule'][:40]}...")
            else:
                # Both new, use length heuristic
                if len(rule_a['rule']) > len(rule_b['rule']):
                    rules_to_remove.add(rule_b['rule'])
                else:
                    rules_to_remove.add(rule_a['rule'])
                    
        # Filter and Rebuild
        final_rules = [r for r in new_rules + known_rules if r['rule'] not in rules_to_remove]
        
        # Save Manifest
        final_hashes = [hashlib.md5(r['rule'].encode('utf-8')).hexdigest() for r in final_rules]
        with open(manifest_path, 'w') as f:
            json.dump(final_hashes, f)
            
        print(f"\n✓ Validation complete: Kept {len(final_rules)} rules.")
        print("="*60 + "\n")
        
        return "\n".join([f"- {r['rule']}" for r in final_rules])

    def _check_pair_incremental(self, rule_a, rule_b):
        """Helper to check pair conflict with optimization."""
        # Quick heuristic context check
        if rule_a['context'] != rule_b['context'] and \
           rule_a['context'] != 'general' and \
           rule_b['context'] != 'general':
            return None

        # Opt: Semantic Sim
        try:
            emb_a = self.vector_store.embed_text(rule_a['rule'])
            emb_b = self.vector_store.embed_text(rule_b['rule'])
            # Ensure embeddings are 2D arrays for sklearn
            if len(emb_a.shape) == 1: emb_a = [emb_a]
            if len(emb_b.shape) == 1: emb_b = [emb_b]
            sim = cosine_similarity(emb_a, emb_b)[0][0]
            if sim < 0.75: return None
        except: pass
        
        # Logic Check
        check = self._check_rule_conflict(rule_a, rule_b)
        if check['has_conflict']:
            return (rule_a, rule_b, check['reason'])
        return None

    def run(self, product_spec_path, style_guide_path, epochs=6):
        # 1. Build Knowledge Base (RAG)
        self.build_knowledge_base(product_spec_path, style_guide_path)

        if os.path.exists("ace/context_playbook.md"):
            with open("ace/context_playbook.md", "r") as f:
                context_playbook = f.read()
            print("Loaded existing Context Playbook from disk.")
        else:
            context_playbook = "- Follow standard RESTful practices.\n- Ensure valid YAML output."
        
        # HASH CHECK: Skip validation if playbook hasn't changed
        current_hash = hashlib.md5(context_playbook.encode('utf-8')).hexdigest()
        hash_file = "ace/context_playbook.md5"
        
        should_validate = True
        if os.path.exists(hash_file):
            with open(hash_file, "r") as f:
                stored_hash = f.read().strip()
            if stored_hash == current_hash:
                print("✓ Playbook unchanged (hash match). Skipping validation.")
                should_validate = False
        
        # Validate playbook consistency before starting epochs
        if should_validate:
            context_playbook = self.validate_playbook_consistency(context_playbook)
            # Update hash after validation (using the CLEANED version if it changed, or original)
            new_hash = hashlib.md5(context_playbook.encode('utf-8')).hexdigest()
            with open(hash_file, "w") as f:
                f.write(new_hash)
                print(f"✓ Validated and hashed playbook ({new_hash[:8]})")
        
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
                # Stop only if improvement is positive but tiny (0-5%)
                if 0 < improvement <= 0.05:
                    print("   !! Diminishing returns detected (0-5% positive improvement). Stopping early.")
                    break
                else:
                    print("   Improvement sufficient or negative; continuing training.")
            # Update previous critique length for next epoch
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
