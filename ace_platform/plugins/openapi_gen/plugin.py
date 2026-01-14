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
            # Safety Settings to prevent blocking
            self.safety_settings = [
                SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
                SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
                SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
                SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
            ]
    
    def _call_llm(self, prompt):
        if self.mock: return "MOCK_RESPONSE"
        try:
            import time
            start_t = time.time()
            # Enforce Deterministic Output
            response = self.model.generate_content(
                prompt,
                safety_settings=self.safety_settings,
                generation_config={"temperature": 0}
            )
            print(f"   Debug: LLM Response received in {round(time.time() - start_t, 2)}s")
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
        
        # Check for cached vector store
        if vector_store.load_local():
            print("Skipping ingestion (loaded from cache).")
            return vector_store
        
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
                 playbook = f.read()
        else:
            playbook = """
# Context Playbook
- **Style Guide**: Apply all style guidelines strictly.
- **Naming**: Use kebab-case for URLs, camelCase for properties.
- **Security**: All endpoints must have OAuth2 security schemes.
- **Error Handling**: Standardize 400, 401, 403, 404, 500 responses.
"""
        
        # Validate consistency before returning
        return self.validate_playbook_consistency(playbook)

    def validate_playbook_consistency(self, playbook_text: str) -> str:
        """
        Validate entire playbook for internal consistency.
        Detects and prunes conflicting rules.
        """
        print("\n" + "="*60)
        print("PLUGIN: PLAYBOOK CONSISTENCY VALIDATION")
        print("="*60)
        
        # Parse existing playbook
        rules = self._parse_existing_playbook(playbook_text)
        
        if not rules:
            print("⚠ No rules found in playbook, skipping validation")
            return playbook_text
        
        print(f"✓ Parsed {len(rules)} rules from playbook")

        # 1. Validate against Style Guide
        # Check if we have Style Guide content available
        try:
            style_guide_rules = self._validate_against_style_guide_plugin(rules)
            if len(style_guide_rules) < len(rules):
                diff = len(rules) - len(style_guide_rules)
                print(f"✂️ Removed {diff} rules that contradicted the Style Guide.")
                rules = style_guide_rules
            else:
                print("✓ All rules align with Style Guide")
        except Exception as e:
            print(f"⚠ Could not validate against Style Guide: {e}")
        
        # 2. Detect conflicts (internal consistency)
        print(f"\n🔍 Detecting internal conflicts among {len(rules)} rules...")
        conflicts = []
        conflicts_detected = 0
        
        for i, rule_a in enumerate(rules):
            for j, rule_b in enumerate(rules[i+1:], start=i+1):
                # Quick heuristic: skip if contexts are completely different
                if rule_a['context'] != rule_b['context'] and \
                   rule_a['context'] != 'general' and \
                   rule_b['context'] != 'general':
                    continue
                
                # Check for semantic conflict using the plugin's conflict checker
                conflict_check = self._check_rule_conflict_plugin(rule_a, rule_b)
                
                if conflict_check['has_conflict']:
                    conflicts_detected += 1
                    conflicts.append((rule_a, rule_b, conflict_check['reason']))
                    print(f"  ⚠ Conflict #{conflicts_detected}:")
                    print(f"    Rule A: {rule_a['rule'][:60]}...")
                    print(f"    Rule B: {rule_b['rule'][:60]}...")
                    print(f"    Reason: {conflict_check['reason']}")
        
        if conflicts_detected == 0:
            print("✓ No conflicts detected - playbook is consistent")
            return playbook_text
        
        # Prune conflicts
        print(f"\n✂️ Pruning {conflicts_detected} conflicts...")
        rules_to_remove = set()
        
        for rule_a, rule_b, reason in conflicts:
            # Decide which rule to keep (prefer more specific)
            len_a = len(rule_a['rule'])
            len_b = len(rule_b['rule'])
            
            if len_a > len_b * 1.2:
                # Rule A is significantly more specific
                rules_to_remove.add(rule_b['rule'])
                print(f"  ✂️ Removing (less specific): {rule_b['rule'][:50]}...")
            elif len_b > len_a * 1.2:
                # Rule B is significantly more specific
                rules_to_remove.add(rule_a['rule'])
                print(f"  ✂️ Removing (less specific): {rule_a['rule'][:50]}...")
            else:
                # Similar length, keep the first one (arbitrary)
                rules_to_remove.add(rule_b['rule'])
                print(f"  ✂️ Removing (duplicate): {rule_b['rule'][:50]}...")
        
        # Filter out removed rules
        pruned_rules = [r for r in rules if r['rule'] not in rules_to_remove]
        
        # Rebuild playbook
        merged_lines = [f"- {r['rule']}" for r in pruned_rules]
        cleaned_playbook = "\n".join(merged_lines)
        
        return cleaned_playbook


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

        # 4. Format playbook for maximum LLM attention
        formatted_playbook = self._format_playbook_for_prompt(playbook)

        # 5. Generate
        prompt = f"""
You are a Senior API Architect generating OpenAPI Specifications.

[OUTPUT FORMAT]
Output ONLY valid YAML. No markdown fences, no explanations.

[PRODUCT SPECIFICATION]
{full_context}

[STYLE GUIDE - AUTHORITATIVE RULES]
{style_rules}

[⚠️ CRITICAL REMINDERS - RULES YOU FREQUENTLY MISS]
The following are NOT new rules. They are specific Style Guide rules that 
you have historically failed to apply correctly in previous epochs. 
Pay EXTRA attention to these:

{formatted_playbook}

[STRATEGIC SCOPING]
Do NOT generate endpoints for shared enterprise services (Authentication, User Login, 
Sessions, API Keys, Tenant Management). These are handled by external platform services. 
Focus ONLY on the CORE domain value of this specific product (e.g., Gateways, Interfaces, Routes).

[FINAL INSTRUCTION - SELF-CHECK BEFORE OUTPUT]
Before outputting your OpenAPI Specification:
1. Review it against the Critical Reminders above
2. Verify you haven't repeated past mistakes (check examples if provided)
3. If the playbook includes a checklist, mentally verify each item
4. Ensure all naming conventions match the emphasized patterns
5. Be EXHAUSTIVE - include all schemas, paths, and error responses found in the text

Generate the OpenAPI Specification now:
openapi: 3.0.0
"""
        return self._call_llm(prompt)

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
        """
        Enhanced Curator with conflict detection and Style Guide validation.
        Matches the legacy agent's enhanced curator implementation.
        """
        print("Plugin: Curating Playbook (Enhanced)...")
        if "NO_ISSUES" in critique:
            return playbook

        # Step 1: Extract rule candidates
        new_rule_candidates = self._extract_rule_candidates_simple(critique)
        
        if not new_rule_candidates:
            return playbook
        
        # Step 2: Validate against Style Guide (using vector_store from context)
        # Note: We need access to vector_store, which we'll get from self if available
        validated_rules = self._validate_against_style_guide_plugin(new_rule_candidates)
        
        # Step 3: Detect and resolve conflicts
        conflict_free_rules = self._detect_and_resolve_conflicts_plugin(
            validated_rules,
            playbook
        )
        
        # Step 4: Merge with semantic deduplication
        updated_playbook = self._merge_rules_with_deduplication_plugin(
            playbook,
            conflict_free_rules
        )
        
        return updated_playbook
    
    def _extract_rule_candidates_simple(self, critique_text):
        """Extract actionable rules from critique."""
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
            print(f"  Extracted {len(rules)} rule candidates")
            return rules
        except Exception as e:
            print(f"  Failed to extract rules: {e}")
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
    
    def _validate_against_style_guide_plugin(self, rule_candidates):
        """Validate rules against Style Guide (using vector_store)."""
        if not rule_candidates:
            return []
        
        print(f"  Validating {len(rule_candidates)} candidates against Style Guide...")
        
        # Retrieve style guide text
        style_guide_text = ""
        if hasattr(self, 'vector_store'):
            try:
                results = self.vector_store.get_all_by_metadata({'type': 'style_guide'})
                style_guide_text = "\n".join([r['text'] for r in results])
                print(f"  Loaded Style Guide context ({len(style_guide_text)} chars)")
            except Exception as e:
                print(f"  ⚠ Failed to load Style Guide: {e}")
        else:
             print("  ⚠ No vector_store found, skipping validation")
             # Fallback: accept all if no vector store
             return rule_candidates

        # If style guide is empty, we can't validate (or assume silence = valid)
        if not style_guide_text:
            return rule_candidates

        # Use sample for prompt
        style_sample = style_guide_text[:8000]

        validated = []
        for candidate in rule_candidates:
            # Skip validation for obviously safe rules or if context suggests otherwise
            
            prompt = f"""
You are a Standards Compliance Validator.

AUTHORITATIVE STYLE GUIDE (excerpt):
{style_sample}

PROPOSED RULE:
{candidate['rule']}

Task:
Check if this rule CONTRADICTS the Style Guide.

Output one of:
- "VALID" if it aligns with or reinforces the Style Guide
- "CONTRADICTION: [reason]" if it contradicts any Style Guide rule
- "NOT_COVERED" if Style Guide is silent on this topic

Output:
"""
            try:
                result = self._call_llm(prompt).strip().upper()
                
                if "CONTRADICTION" in result and "VALID" not in result:
                    reason = result.replace("CONTRADICTION:", "").replace("CONTRADICTION", "").strip()
                    print(f"  ✗ Rejected: {candidate['rule'][:50]}... (Reason: {reason})")
                else:
                    validated.append(candidate)
                    print(f"  ✓ Accepted: {candidate['rule'][:50]}...")
            except Exception as e:
                print(f"  ⚠ Validation error for rule: {e}")
                validated.append(candidate) # Fail open
        
        return validated
    
    def _detect_and_resolve_conflicts_plugin(self, new_rules, existing_playbook):
        """Detect and resolve conflicts (simplified for plugin)."""
        if not new_rules:
            return []
        
        print(f"  Checking for conflicts...")
        
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
                conflict_check = self._check_rule_conflict_plugin(new_rule, existing_rule)
                
                if conflict_check['has_conflict']:
                    has_conflict = True
                    conflicts_detected += 1
                    
                    print(f"  ! Conflict: Replacing existing rule with new rule")
                    existing_rule['_remove'] = True
                    conflict_free.append(new_rule)
                    break
            
            if not has_conflict:
                conflict_free.append(new_rule)
        
        if conflicts_detected > 0:
            print(f"  Resolved {conflicts_detected} conflicts")
        
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
    
    def _check_rule_conflict_plugin(self, new_rule, existing_rule):
        """Use LLM to detect if two rules conflict."""
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
            return {'has_conflict': False, 'reason': 'check_failed'}
    
    def _merge_rules_with_deduplication_plugin(self, existing_playbook, new_rules):
        """Merge new rules with existing playbook (simplified - no embeddings)."""
        # Parse existing playbook
        existing_rules = self._parse_existing_playbook(existing_playbook)
        
        # Remove rules marked for deletion
        existing_rules = [r for r in existing_rules if not r.get('_remove', False)]
        
        # Convert to text format
        merged_lines = [f"- {r['rule']}" for r in existing_rules]
        
        # Add new rules with simple text-based deduplication
        print(f"  Merging {len(new_rules)} new rules...")
        added_count = 0
        
        for new_rule in new_rules:
            new_text = new_rule['rule']
            
            # Simple text-based deduplication
            is_duplicate = False
            for existing_rule in existing_rules:
                existing_text = existing_rule['rule']
                
                # Check for exact or very similar text
                if new_text.lower() == existing_text.lower() or \
                   new_text.lower() in existing_text.lower() or \
                   existing_text.lower() in new_text.lower():
                    is_duplicate = True
                    print(f"  Skipped duplicate: {new_text[:50]}...")
                    break
            
            if not is_duplicate:
                merged_lines.append(f"- {new_text}")
                added_count += 1
                print(f"  + Added: {new_text[:60]}...")
        
        print(f"  Added {added_count} new rules to playbook")
        return "\n".join(merged_lines)



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
