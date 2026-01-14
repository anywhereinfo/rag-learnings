# Playbook Enhancement Summary
**Date**: 2026-01-14  
**Version**: 2.0

## 🎯 Objective
Transform the Context Playbook from a simple list of rules into a **structured, prioritized knowledge base** that maximizes LLM attention on frequently-violated rules.

---

## ✅ Implemented Changes

### **1. Enhanced Generator Prompt Structure**
**Files Modified:**
- `ace/ace_agent.py` (lines 142-178)
- `ace_platform/plugins/openapi_gen/plugin.py` (lines 110-230)

**Changes:**
- Reorganized prompt with clear section headers: `[OUTPUT FORMAT]`, `[PRODUCT SPECIFICATION]`, `[STYLE GUIDE]`, `[CRITICAL REMINDERS]`
- Added explicit warning that playbook contains NO NEW RULES (prevents LLM from treating it as separate ruleset)
- Added `[FINAL INSTRUCTION - SELF-CHECK BEFORE OUTPUT]` section with 4-step verification process
- Emphasized that Style Guide is AUTHORITATIVE and always wins in conflicts

**Impact:**
- Clearer hierarchy: Style Guide = rules, Playbook = reminders of frequently-missed rules
- Reduced likelihood of duplicate rule generation
- Self-check step encourages LLM to review output before submission

---

### **2. Structured Playbook Parsing**
**New Methods Added:**
- `_parse_playbook_sections(playbook: str) -> dict`
- `_format_playbook_for_prompt(playbook: str) -> str`

**Functionality:**
- Parses playbook markdown into structured sections:
  - `FREQUENTLY_MISSED` (🚨 CRITICAL - >75% violation rate)
  - `PARTIALLY_MISSED` (⚠️ MODERATE - 25-75% violation rate)
  - `EDGE_CASES` (📌 Special cases)
  - `CHECKLIST` (✅ Pre-submission verification)
- Formats sections with visual emphasis (emojis, priority labels)
- Presents sections in priority order (CRITICAL first)

**Fallback Behavior:**
- If no structured sections detected, treats entire playbook as `FREQUENTLY_MISSED`
- If playbook is empty, returns default rules: "Follow RESTful practices, ensure valid YAML"

---

### **3. Example Structured Playbook**
**File Created:** `ace/context_playbook_EXAMPLE.md`

**Structure:**
```markdown
## 🚨 CRITICAL (Violated in >75% of generations)
### Rule: operationId Naming Convention
**Violation Rate**: 85%
**Style Guide Reference**: Section 2.3.1
❌ You keep doing: [bad example]
✅ Correct format: [good example]

## ⚠️ MODERATE (Violated in 25-75% of generations)
[Similar structure]

## 📋 PRE-SUBMISSION CHECKLIST
- [ ] All operationId values are camelCase
- [ ] All components/schemas are PascalCase
[...]

## 📊 IMPROVEMENT METRICS
- Previous: 68% compliance
- Target: 90% compliance
```

---

## 🔄 How It Works (Flow)

### **Before (v1.0):**
```
1. Generator receives raw playbook text
2. LLM sees playbook as "guidelines" (ambiguous)
3. LLM may treat playbook as new rules → duplicates
4. No prioritization of critical vs. minor issues
```

### **After (v2.0):**
```
1. Generator calls _format_playbook_for_prompt()
2. Playbook is parsed into priority sections
3. Formatted playbook emphasizes CRITICAL rules first
4. LLM sees clear hierarchy: Style Guide (rules) > Playbook (reminders)
5. Self-check step prompts LLM to verify against checklist
6. Output has fewer violations of frequently-missed rules
```

---

## 📊 Expected Benefits

| Metric | Before | After (Expected) |
|--------|--------|------------------|
| Duplicate rules in playbook | ~15-20% | <5% |
| Compliance with critical rules | ~60-70% | ~85-90% |
| Convergence speed | 4-6 epochs | 3-4 epochs |
| Playbook growth rate | +10-15 rules/epoch | +3-5 rules/epoch |
| LLM attention on critical issues | Low (buried in text) | High (visual emphasis) |

---

## 🧪 Testing Recommendations

### **Test 1: Structured Playbook Parsing**
```python
# Create a test playbook with sections
test_playbook = """
## 🚨 CRITICAL
- Rule 1
- Rule 2

## ⚠️ MODERATE
- Rule 3

## 📋 CHECKLIST
- [ ] Item 1
"""

agent = ACEAgent(...)
formatted = agent._format_playbook_for_prompt(test_playbook)
print(formatted)
# Should show prioritized sections with emojis
```

### **Test 2: Fallback Behavior**
```python
# Test with unstructured playbook
simple_playbook = "- Rule A\n- Rule B"
formatted = agent._format_playbook_for_prompt(simple_playbook)
# Should treat as FREQUENTLY_MISSED section
```

### **Test 3: End-to-End Generation**
```bash
# Run agent with enhanced playbook
python ace/ace_agent.py

# Observe:
# 1. Fewer duplicate rules in curator output
# 2. Better compliance with critical naming conventions
# 3. Faster convergence (fewer epochs needed)
```

---

## 🚀 Future Enhancements (Phase 2)

### **1. Violation Rate Tracking**
```python
class PlaybookMetrics:
    def track_violation(self, rule_id: str):
        """Increment violation count for a rule"""
        
    def get_violation_rate(self, rule_id: str) -> float:
        """Calculate % of epochs where rule was violated"""
        
    def auto_promote_to_critical(self, threshold=0.75):
        """Move rules to CRITICAL if violation rate > 75%"""
```

### **2. Self-Correction Loop**
```python
def _validate_against_playbook_rules(self, oas_yaml: str, playbook: dict) -> list:
    """
    Parse generated OAS and check for violations of playbook rules.
    Returns list of violations found.
    """
    
def _self_correct(self, oas_yaml: str, violations: list) -> str:
    """
    Re-prompt LLM with violations highlighted, ask for corrections.
    """
```

### **3. Dynamic Playbook Reordering**
```python
def _reorder_playbook_by_recency(self, playbook: dict, recent_violations: list):
    """
    Move recently-violated rules to top of CRITICAL section.
    Implements recency bias for attention mechanism.
    """
```

---

## 📝 Migration Notes

### **For Existing Playbooks:**
- Old format (simple bullet list) still works (fallback behavior)
- To leverage new features, restructure playbook with section headers:
  ```markdown
  ## 🚨 CRITICAL (Violated in >75% of generations)
  [rules]
  
  ## ⚠️ MODERATE (Violated in 25-75% of generations)
  [rules]
  
  ## 📋 PRE-SUBMISSION CHECKLIST
  [checklist items]
  ```

### **Backward Compatibility:**
- ✅ Old playbooks continue to work (treated as FREQUENTLY_MISSED)
- ✅ No breaking changes to API
- ✅ Gradual migration path (can add sections incrementally)

---

## 🎓 Key Learnings

1. **Playbook ≠ Rules**: The playbook is a dynamic attention mechanism, not a ruleset
2. **Visual Emphasis Matters**: Emojis and priority labels help LLM focus
3. **Structure > Volume**: A well-structured 10-rule playbook beats an unstructured 50-rule list
4. **Self-Check is Powerful**: Asking LLM to verify before output reduces violations
5. **Hierarchy is Critical**: Style Guide (authoritative) > Playbook (reminders) must be explicit

---

## 📚 References

- Original playbook design: `ace/context_playbook.md`
- Enhanced example: `ace/context_playbook_EXAMPLE.md`
- Implementation: `ace/ace_agent.py` (lines 177-260)
- Platform plugin: `ace_platform/plugins/openapi_gen/plugin.py` (lines 146-230)
