#!/usr/bin/env python3
"""
Playbook Validation and Conflict Pruning Script

This script analyzes an existing context playbook to:
1. Detect conflicting rules (contradictory statements)
2. Validate rules against the authoritative Style Guide
3. Prune duplicates and conflicts
4. Generate a cleaned, conflict-free playbook

Usage:
    python validate_playbook.py [--playbook context_playbook.md] [--style-guide docs/style_guide.pdf] [--output cleaned_playbook.md]
"""

import os
import argparse
import yaml
import json
import re
from typing import List, Dict, Set, Tuple
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
import logging

# Vertex AI Imports
import vertexai
from vertexai.generative_models import GenerativeModel, SafetySetting
from vertexai.language_models import TextEmbeddingModel

# Constants
PROJECT_ID = "gcp-prj-ntpc-np-01"
LOCATION = "us-central1"

# Initialize Vertex AI
try:
    vertexai.init(project=PROJECT_ID, location=LOCATION)
except Exception as e:
    print(f"⚠ Warning: Failed to initialize Vertex AI: {e}")
    print("  Ensure you have run: gcloud auth application-default login")

# Import from existing modules
from utils.vector_store import GoogleVectorStore
from utils.chunker import PDFChunker


class PlaybookValidator:
    """Validates and cleans context playbooks."""
    
    def __init__(self, model_name="gemini-2.5-pro"):
        self.model_name = model_name
        try:
            self.model = GenerativeModel(model_name)
            self.embedding_model = TextEmbeddingModel.from_pretrained("text-embedding-004")
        except Exception as e:
            print(f"Error initializing models: {e}")
            self.model = None
            self.embedding_model = None

    def _call_llm(self, prompt: str) -> str:
        """Call LLM with error handling (Vertex AI)."""
        if not self.model:
            return ""
        try:
            response = self.model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            print(f"LLM Call failed: {e}")
            return ""

    def _get_embedding(self, text: str) -> np.ndarray:
        """Get embedding for text (Vertex AI)."""
        if not self.embedding_model:
            return np.zeros(768)
        
        if hasattr(self, 'embedding_cache') and text in self.embedding_cache:
            return self.embedding_cache[text]

        try:
            embeddings = self.embedding_model.get_embeddings([text])
            if embeddings:
                val = np.array(embeddings[0].values)
                if hasattr(self, 'embedding_cache'):
                    self.embedding_cache[text] = val
                return val
            return np.zeros(768)
        except Exception as e:
            print(f"Embedding failed: {e}")
            return np.zeros(768)

    def cache_all_embeddings(self, rules: List[Dict]):
        """Pre-compute embeddings for all rules."""
        if not hasattr(self, 'embedding_cache'):
            self.embedding_cache = {}
            
        print(f"⚡ Pre-computing embeddings for {len(rules)} rules...")
        batch_size = 20
        texts = [r['rule'] for r in rules if r['rule'] not in self.embedding_cache]
        
        if not texts: return

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i+batch_size]
            try:
                embeddings = self.embedding_model.get_embeddings(batch)
                for text, embedding in zip(batch, embeddings):
                    self.embedding_cache[text] = np.array(embedding.values)
            except Exception as e:
                print(f"  ⚠ Batch embedding failed: {e}")
    
    def load_playbook(self, playbook_path: str) -> str:
        """Load playbook from file."""
        if not os.path.exists(playbook_path):
            raise FileNotFoundError(f"Playbook not found: {playbook_path}")
        
        with open(playbook_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        print(f"✓ Loaded playbook from {playbook_path}")
        return content
    
    def load_style_guide(self, style_guide_path: str) -> str:
        """Load and extract Style Guide content."""
        if not os.path.exists(style_guide_path):
            print(f"⚠ Style Guide not found: {style_guide_path}")
            return ""
        
        print(f"Loading Style Guide from {style_guide_path}...")
        
        # Use chunker to extract text
        chunker = PDFChunker()
        chunks = chunker.extract_text_with_metadata(style_guide_path)
        
        # Combine all chunks
        style_guide_text = "\n".join([chunk['text'] for chunk in chunks])
        
        print(f"✓ Loaded Style Guide ({len(style_guide_text)} chars)")
        return style_guide_text

    def save_playbook(self, content: str, path: str):
        """
        Save cleaned playbook and verified rule manifest.
        """
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(path), exist_ok=True)
            
            # 1. Save Playbook
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"✓ Saved cleaned playbook to {path}")
            
            # 2. Generate and Save Verified Rule Manifest
            # Parse the rules back out to get individual items
            rules = self.parse_playbook_rules(content)
            import hashlib
            verified_hashes = [hashlib.md5(r['rule'].encode('utf-8')).hexdigest() for r in rules]
            
            manifest_path = os.path.join(os.path.dirname(path), "verified_rules.json")
            with open(manifest_path, 'w') as f:
                json.dump(verified_hashes, f)
            print(f"✓ Saved verified manifest to {manifest_path} ({len(verified_hashes)} rules)")

        except Exception as e:
            print(f"Error saving playbook: {e}")
    
    def parse_playbook_rules(self, playbook_text: str) -> List[Dict]:
        """Parse playbook into structured rules."""
        rules = []
        current_section = None
        
        for line in playbook_text.split('\n'):
            line_stripped = line.strip()
            
            # Detect section headers
            if '##' in line_stripped and 'CRITICAL' in line_stripped.upper():
                current_section = 'CRITICAL'
            elif '##' in line_stripped and 'MODERATE' in line_stripped.upper():
                current_section = 'MODERATE'
            elif '##' in line_stripped and 'CHECKLIST' in line_stripped.upper():
                current_section = 'CHECKLIST'
            elif '##' in line_stripped and 'EDGE' in line_stripped.upper():
                current_section = 'EDGE_CASES'
            elif line_stripped.startswith('- '):
                # This is a rule
                rule_text = line_stripped[2:]
                rules.append({
                    'rule': rule_text,
                    'section': current_section or 'GENERAL',
                    'context': self._infer_context(rule_text),
                    'original_line': line_stripped
                })
        
        print(f"✓ Parsed {len(rules)} rules from playbook")
        return rules
    
    def _infer_context(self, rule_text: str) -> str:
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
    
    def detect_conflicts(self, rules: List[Dict]) -> List[Tuple[Dict, Dict, str]]:
        """
        Detect conflicts between rules.
        Returns list of (rule_a, rule_b, reason) tuples.
        """
        print(f"\n🔍 Detecting conflicts among {len(rules)} rules...")
        conflicts = []
        
        for i, rule_a in enumerate(rules):
            if i % 10 == 0:
                print(f"  ... checking rule {i+1}/{len(rules)}")
            for j, rule_b in enumerate(rules[i+1:], start=i+1):
                # OPTIMIZATION: Check semantic similarity first
                # Only check for conflict if rules are somewhat related (sim > 0.75)
                emb_a = self._get_embedding(rule_a['rule'])
                emb_b = self._get_embedding(rule_b['rule'])
                similarity = cosine_similarity([emb_a], [emb_b])[0][0]
                
                if similarity < 0.75:
                    continue  # Skip LLM call
                
                print(f"    ? Checking potential conflict (sim={similarity:.2f})...")
                # Check for semantic conflict using LLM
                conflict_result = self._check_conflict(rule_a, rule_b)
                
                if conflict_result['has_conflict']:
                    conflicts.append((rule_a, rule_b, conflict_result['reason']))
                    print(f"  ⚠ Conflict #{len(conflicts)}:")
                    print(f"    Rule A: {rule_a['rule'][:60]}...")
                    print(f"    Rule B: {rule_b['rule'][:60]}...")
                    print(f"    Reason: {conflict_result['reason']}")
        
        print(f"\n{'✓' if len(conflicts) == 0 else '⚠'} Found {len(conflicts)} conflicts")
        return conflicts
    
    def _check_conflict(self, rule_a: Dict, rule_b: Dict) -> Dict:
        """Use LLM to detect if two rules conflict."""
        prompt = f"""
You are a Logic Validator.

Rule A: {rule_a['rule']}
Context A: {rule_a['context']}

Rule B: {rule_b['rule']}
Context B: {rule_b['context']}

Question: Do these rules CONTRADICT each other?

Two rules contradict if:
- They apply to the same thing but prescribe opposite actions
- Following both simultaneously is impossible
- Example: "Use snake_case for X" vs "Use camelCase for X"

Output ONLY:
- "NO_CONFLICT" if they can coexist
- "CONFLICT: [brief reason]" if they contradict
"""
        
        try:
            result = self._call_llm(prompt).strip()
            
            if "CONFLICT" in result.upper() and "NO_CONFLICT" not in result.upper():
                reason = result.replace("CONFLICT:", "").replace("CONFLICT", "").strip()
                return {'has_conflict': True, 'reason': reason or 'contradictory rules'}
            else:
                return {'has_conflict': False, 'reason': 'compatible'}
                
        except Exception as e:
            print(f"  ! Conflict check failed: {e}")
            return {'has_conflict': False, 'reason': 'check_failed'}
    
    def validate_against_style_guide(self, rules: List[Dict], style_guide_text: str) -> List[Dict]:
        """
        Validate rules against Style Guide.
        Returns list of rules that contradict the Style Guide.
        """
        if not style_guide_text:
            print("\n⚠ Skipping Style Guide validation (no Style Guide loaded)")
            return []
        
        print(f"\n🔍 Validating {len(rules)} rules against Style Guide...")
        contradictions = []
        
        for rule in rules:
            validation_result = self._validate_rule(rule, style_guide_text)
            
            if validation_result['contradicts']:
                contradictions.append(rule)
                print(f"  ✗ CONTRADICTION: {rule['rule'][:60]}...")
                print(f"    Reason: {validation_result['reason']}")
        
        print(f"\n{'✓' if len(contradictions) == 0 else '⚠'} Found {len(contradictions)} Style Guide contradictions")
        return contradictions
    
    def _validate_rule(self, rule: Dict, style_guide_text: str) -> Dict:
        """Validate a single rule against Style Guide."""
        # Use a sample of Style Guide to avoid token limits
        style_sample = style_guide_text[:8000]
        
        prompt = f"""
You are a Standards Compliance Validator.

AUTHORITATIVE STYLE GUIDE (excerpt):
{style_sample}

PROPOSED RULE:
{rule['rule']}

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
            
            if "CONTRADICTION" in result:
                reason = result.replace("CONTRADICTION:", "").replace("CONTRADICTION", "").strip()
                return {'contradicts': True, 'reason': reason or 'contradicts Style Guide'}
            else:
                return {'contradicts': False, 'reason': 'valid or not covered'}
                
        except Exception as e:
            print(f"  ! Validation failed: {e}")
            return {'contradicts': False, 'reason': 'check_failed'}
    
    def detect_duplicates(self, rules: List[Dict]) -> List[Tuple[Dict, Dict, float]]:
        """
        Detect duplicate rules using semantic similarity.
        Returns list of (rule_a, rule_b, similarity) tuples.
        """
        print(f"\n🔍 Detecting duplicates among {len(rules)} rules...")
        duplicates = []
        
        for i, rule_a in enumerate(rules):
            for j, rule_b in enumerate(rules[i+1:], start=i+1):
                # Embed both rules
                emb_a = self._get_embedding(rule_a['rule'])
                emb_b = self._get_embedding(rule_b['rule'])
                
                # Calculate similarity
                similarity = cosine_similarity([emb_a], [emb_b])[0][0]
                
                if similarity > 0.85:
                    duplicates.append((rule_a, rule_b, similarity))
                    print(f"  ⚠ Duplicate #{len(duplicates)} (similarity: {similarity:.2f}):")
                    print(f"    Rule A: {rule_a['rule'][:60]}...")
                    print(f"    Rule B: {rule_b['rule'][:60]}...")
        
        print(f"\n{'✓' if len(duplicates) == 0 else '⚠'} Found {len(duplicates)} duplicates")
        return duplicates
    
    def prune_conflicts(self, rules: List[Dict], conflicts: List[Tuple]) -> List[Dict]:
        """
        Prune conflicting rules by keeping the more specific one.
        """
        print(f"\n✂️ Pruning {len(conflicts)} conflicts...")
        
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
        
        print(f"✓ Pruned {len(rules) - len(pruned_rules)} rules, {len(pruned_rules)} remaining")
        return pruned_rules
    
    def prune_duplicates(self, rules: List[Dict], duplicates: List[Tuple]) -> List[Dict]:
        """
        Prune duplicate rules by keeping the first occurrence.
        """
        print(f"\n✂️ Pruning {len(duplicates)} duplicates...")
        
        rules_to_remove = set()
        
        for rule_a, rule_b, similarity in duplicates:
            # Keep rule_a, remove rule_b (arbitrary choice)
            rules_to_remove.add(rule_b['rule'])
            print(f"  ✂️ Removing duplicate: {rule_b['rule'][:50]}...")
        
        # Filter out removed rules
        pruned_rules = [r for r in rules if r['rule'] not in rules_to_remove]
        
        print(f"✓ Pruned {len(rules) - len(pruned_rules)} rules, {len(pruned_rules)} remaining")
        return pruned_rules
    
    def remove_style_guide_contradictions(self, rules: List[Dict], contradictions: List[Dict]) -> List[Dict]:
        """Remove rules that contradict the Style Guide."""
        print(f"\n✂️ Removing {len(contradictions)} Style Guide contradictions...")
        
        contradiction_texts = {r['rule'] for r in contradictions}
        pruned_rules = [r for r in rules if r['rule'] not in contradiction_texts]
        
        for rule in contradictions:
            print(f"  ✂️ Removing: {rule['rule'][:60]}...")
        
        print(f"✓ Removed {len(rules) - len(pruned_rules)} rules, {len(pruned_rules)} remaining")
        return pruned_rules
    
    def generate_cleaned_playbook(self, rules: List[Dict]) -> str:
        """Generate a cleaned playbook from validated rules."""
        print(f"\n📝 Generating cleaned playbook from {len(rules)} rules...")
        
        # Group rules by section
        sections = {
            'CRITICAL': [],
            'MODERATE': [],
            'EDGE_CASES': [],
            'CHECKLIST': [],
            'GENERAL': []
        }
        
        for rule in rules:
            section = rule.get('section', 'GENERAL')
            sections[section].append(rule['rule'])
        
        # Build playbook text
        playbook_lines = ["# Context Playbook (Validated & Cleaned)", ""]
        
        if sections['CRITICAL']:
            playbook_lines.append("## 🚨 CRITICAL (Violated in >75% of generations)")
            for rule in sections['CRITICAL']:
                playbook_lines.append(f"- {rule}")
            playbook_lines.append("")
        
        if sections['MODERATE']:
            playbook_lines.append("## ⚠️ MODERATE (Violated in 25-75% of generations)")
            for rule in sections['MODERATE']:
                playbook_lines.append(f"- {rule}")
            playbook_lines.append("")
        
        if sections['EDGE_CASES']:
            playbook_lines.append("## 📌 EDGE CASES")
            for rule in sections['EDGE_CASES']:
                playbook_lines.append(f"- {rule}")
            playbook_lines.append("")
        
        if sections['CHECKLIST']:
            playbook_lines.append("## ✅ PRE-SUBMISSION CHECKLIST")
            for rule in sections['CHECKLIST']:
                playbook_lines.append(f"- {rule}")
            playbook_lines.append("")
        
        if sections['GENERAL']:
            playbook_lines.append("## General Guidelines")
            for rule in sections['GENERAL']:
                playbook_lines.append(f"- {rule}")
            playbook_lines.append("")
        
        return "\n".join(playbook_lines)
    
    def categorize_rules(self, rules: List[Dict]) -> List[Dict]:
        """
        Auto-categorize rules into v3.0 sections using LLM.
        Only runs for rules currently in 'GENERAL' section.
        """
        general_rules = [r for r in rules if r.get('section', 'GENERAL') == 'GENERAL']
        if not general_rules:
            return rules
            
        print(f"\n🧠 Auto-categorizing {len(general_rules)} rules into v3.0 sections...")
        
        # Process in batches to avoid token limits
        batch_size = 30
        categorized_rules = [r for r in rules if r.get('section', 'GENERAL') != 'GENERAL']
        
        for i in range(0, len(general_rules), batch_size):
            batch_num = (i // batch_size) + 1
            print(f"  ... categorizing batch {batch_num}...")
            batch = general_rules[i:i+batch_size]
            batch_text = "\n".join([f"{idx}. {r['rule']}" for idx, r in enumerate(batch)])
            
            prompt = f"""
You are a Playbook Architect.
Categorize the following API Standards rules into these sections:

1. CRITICAL: High-impact rules, naming conventions, security, error handling, versioning.
2. MODERATE: Formatting details, specific parameter types, documentation nuances.
3. EDGE_CASES: Rules about specific edge cases, batch operations, or rare conditions.
4. CHECKLIST: Verifyable binary checks (e.g. "All X must have Y").

RULES TO CATEGORIZE:
{batch_text}

Output ONLY a JSON mapping of Index -> Section Name.
Example: {{ "0": "CRITICAL", "1": "MODERATE" }}
"""
            try:
                response = self._call_llm(prompt)
                # clean response to get just json
                import json
                import re
                
                json_match = re.search(r'\{.*\}', response, re.DOTALL)
                if json_match:
                    mapping = json.loads(json_match.group(0))
                    
                    for idx, rule in enumerate(batch):
                        section = mapping.get(str(idx), "MODERATE")
                        rule['section'] = section
                        categorized_rules.append(rule)
                else:
                    print("  ⚠ Failed to parse LLM response, keeping as GENERAL")
                    categorized_rules.extend(batch)
                    
            except Exception as e:
                print(f"  ⚠ Categorization failed: {e}")
                categorized_rules.extend(batch)
                
        print(f"✓ Categorized {len(general_rules)} rules")
        return categorized_rules

    def validate_and_clean(self, playbook_path: str, style_guide_path: str = None, output_path: str = None, verify_only: bool = False):
        """
        Main validation and cleaning workflow.
        """
        print("=" * 60)
        print("PLAYBOOK VALIDATION & CONFLICT PRUNING")
        print("=" * 60)
        
        # Load playbook
        playbook_text = self.load_playbook(playbook_path)
        
        # Load Style Guide (optional)
        style_guide_text = ""
        if style_guide_path:
            style_guide_text = self.load_style_guide(style_guide_path)
        
        # Parse rules
        rules = self.parse_playbook_rules(playbook_text)
        
        if not rules:
            print("\n⚠ No rules found in playbook!")
            return
        
        # Pre-compute embeddings for speed
        self.cache_all_embeddings(rules)
        
        # 1. Detect & Prune Duplicates (Fastest)
        duplicates = self.detect_duplicates(rules)
        if duplicates and not verify_only:
            rules = self.prune_duplicates(rules, duplicates)
        
        # 2. Auto-categorize (if cleaning)
        if not verify_only:
            rules = self.categorize_rules(rules)
        
        # 3. Detect & Prune Conflicts (Slowest)
        conflicts = self.detect_conflicts(rules)
        if conflicts and not verify_only:
            rules = self.prune_conflicts(rules, conflicts)
            
        # 4. Style Guide Validation
        contradictions = []
        if style_guide_text:
            contradictions = self.validate_against_style_guide(rules, style_guide_text)
            if contradictions and not verify_only:
                rules = self.remove_style_guide_contradictions(rules, contradictions)
            
        if verify_only:
            print("\nVerify only mode - no changes made.")
            # For summary purposes in verify mode
            pass
        
        # Generate cleaned playbook
        cleaned_playbook = self.generate_cleaned_playbook(rules)
        
        # Save output
        if output_path:
            self.save_playbook(cleaned_playbook, output_path)
            
            # Generate Hash for Agent Integration
            import hashlib
            run_hash = hashlib.md5(cleaned_playbook.encode('utf-8')).hexdigest()
            # Assuming output_path is like 'ace/context_playbook.md', hash is 'ace/context_playbook.md5'
            hash_path = os.path.splitext(output_path)[0] + ".md5"
            with open(hash_path, "w") as f:
                f.write(run_hash)
            print(f"✓ Generated Verification Hash: {hash_path}")
            
        else:
            print("\n" + "=" * 60)
            print("CLEANED PLAYBOOK")
            print("=" * 60)
            print(cleaned_playbook)
        
        # Summary
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"Original rules: {len(self.parse_playbook_rules(playbook_text))}")
        print(f"Conflicts detected: {len(conflicts)}")
        print(f"Duplicates detected: {len(duplicates)}")
        print(f"Style Guide contradictions: {len(contradictions)}")
        print(f"Final rules: {len(rules)}")
        print(f"Rules removed: {len(self.parse_playbook_rules(playbook_text)) - len(rules)}")
        print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Validate and clean context playbook by detecting and pruning conflicts"
    )
    parser.add_argument(
        '--playbook',
        default='ace/context_playbook.md',
        help='Path to playbook file (default: ace/context_playbook.md)'
    )
    parser.add_argument(
        '--style-guide',
        default=None,
        help='Path to Style Guide PDF (optional, for validation)'
    )
    parser.add_argument(
        '--output',
        default=None,
        help='Path to save cleaned playbook (default: print to stdout)'
    )
    parser.add_argument(
        '--verify-only',
        action='store_true',
        help='Only check for issues, do not clean or categorize'
    )
    
    args = parser.parse_args()
    
    # Run validation
    validator = PlaybookValidator()
    validator.validate_and_clean(
        playbook_path=args.playbook,
        style_guide_path=args.style_guide,
        output_path=args.output,
        verify_only=args.verify_only
    )


if __name__ == "__main__":
    main()
