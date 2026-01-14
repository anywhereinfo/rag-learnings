# Playbook Validation Script - Summary

**Created**: 2026-01-14  
**Purpose**: Detect and prune conflicting, duplicate, and contradictory rules from context playbooks

## 🎯 Problem Solved

Even with the enhanced curator (v3.0), legacy playbooks may contain:
- **Conflicting rules** from earlier epochs before conflict detection was implemented
- **Duplicate rules** that slipped through due to slight wording variations
- **Style Guide contradictions** if the Style Guide was updated after rules were added

This script provides a **one-time cleanup tool** and **periodic validation mechanism**.

## 📦 Files Created

| File | Purpose |
|------|---------|
| `ace/validate_playbook.py` | Main validation script (standalone) |
| `ace/VALIDATE_PLAYBOOK_GUIDE.md` | Comprehensive usage guide |
| `ace/test_playbook_with_conflicts.md` | Test file with intentional conflicts |

## 🔧 How It Works

### **3-Phase Validation Pipeline**

```
┌─────────────────────────────────────────────────────────┐
│  PHASE 1: Conflict Detection                            │
│  ├─ Parse playbook into structured rules                │
│  ├─ Compare all rules pairwise                          │
│  ├─ LLM-based semantic conflict detection               │
│  └─ Output: List of conflicting rule pairs              │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│  PHASE 2: Duplicate Detection                           │
│  ├─ Embed all rules (text-embedding-004)                │
│  ├─ Calculate cosine similarity (pairwise)              │
│  ├─ Flag duplicates (>0.85 similarity)                  │
│  └─ Output: List of duplicate rule pairs                │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│  PHASE 3: Style Guide Validation (Optional)             │
│  ├─ Load Style Guide PDF                                │
│  ├─ Validate each rule against Style Guide              │
│  ├─ LLM checks for contradictions                       │
│  └─ Output: List of contradicting rules                 │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│  PRUNING                                                 │
│  ├─ Conflicts: Keep more specific rule                  │
│  ├─ Duplicates: Keep first occurrence                   │
│  ├─ Style Guide contradictions: Remove all              │
│  └─ Output: Cleaned playbook                            │
└─────────────────────────────────────────────────────────┘
```

## 🚀 Usage Examples

### **Quick Validation**
```bash
python ace/validate_playbook.py
```

### **Full Validation with Cleanup**
```bash
python ace/validate_playbook.py \
    --playbook ace/context_playbook.md \
    --style-guide docs/style_guide.pdf \
    --output ace/context_playbook_cleaned.md
```

### **Test with Sample Conflicts**
```bash
python ace/validate_playbook.py \
    --playbook ace/test_playbook_with_conflicts.md \
    --output ace/test_playbook_cleaned.md
```

## 📊 Expected Results (Test Playbook)

The test playbook contains **intentional conflicts**:

| Conflict Type | Example |
|---------------|---------|
| **Naming Convention** | "Use snake_case for operationId" vs "Use camelCase for operationId" |
| **ETag Usage** | "Include ETag on all GET" vs "ETag only on single resources" |
| **DELETE Responses** | "Return 200 with message" vs "Return 204 with no body" |
| **Duplicates** | "Use camelCase for operationId" appears 3 times with slight variations |

**Expected Pruning**:
- Original rules: ~15
- Conflicts detected: ~6
- Duplicates detected: ~4
- Final rules: ~8-10 (after pruning)

## 🔗 Integration with ACE Agent

### **Option 1: Periodic Validation (Recommended)**

Add to `ace_agent.py`:

```python
def validate_playbook_consistency(self, playbook_text):
    """Run periodic playbook validation."""
    from validate_playbook import PlaybookValidator
    
    validator = PlaybookValidator(model_name=self.model_name)
    rules = validator.parse_playbook_rules(playbook_text)
    conflicts = validator.detect_conflicts(rules)
    
    if conflicts:
        rules = validator.prune_conflicts(rules, conflicts)
        return validator.generate_cleaned_playbook(rules)
    
    return playbook_text

# In run() method:
if epoch % 2 == 0:
    context_playbook = self.validate_playbook_consistency(context_playbook)
```

### **Option 2: Pre-Run Validation**

Add to `run()` method before the epoch loop:

```python
def run(self, product_spec_path, style_guide_path, epochs=6):
    # ... existing code ...
    
    # Validate playbook before starting
    print("\n=== Validating Playbook ===")
    context_playbook = self.validate_playbook_consistency(context_playbook)
    
    # ... continue with epochs ...
```

## 📈 Performance Metrics

| Metric | Value |
|--------|-------|
| **LLM Calls** | ~N*(N-1)/2 (pairwise comparison) |
| **Execution Time** | ~30-60s for 25 rules |
| **Cost** | ~$0.01-0.05 per validation (Gemini Flash) |
| **Memory** | <100MB (embeddings cached) |

## 🎓 Key Features

1. **Standalone Script**: Can run independently without modifying agent code
2. **LLM-Based Conflict Detection**: Semantic understanding, not just text matching
3. **Embedding-Based Deduplication**: Catches paraphrased duplicates
4. **Style Guide Validation**: Ensures alignment with authoritative standards
5. **Intelligent Pruning**: Keeps more specific rules, removes less useful ones
6. **Structured Output**: Maintains playbook sections (CRITICAL, MODERATE, etc.)

## 🧪 Testing

### **Test the Script**
```bash
# 1. Run on test playbook with known conflicts
python ace/validate_playbook.py \
    --playbook ace/test_playbook_with_conflicts.md

# 2. Verify conflicts are detected
# Expected: 6+ conflicts, 4+ duplicates

# 3. Generate cleaned version
python ace/validate_playbook.py \
    --playbook ace/test_playbook_with_conflicts.md \
    --output ace/test_playbook_cleaned.md

# 4. Compare before/after
diff ace/test_playbook_with_conflicts.md ace/test_playbook_cleaned.md
```

## 🔮 Future Enhancements

1. **Batch Mode**: Validate multiple playbooks at once
2. **Conflict Resolution UI**: Interactive mode to choose which rule to keep
3. **Violation Rate Tracking**: Track which rules are violated most often
4. **Auto-Categorization**: Automatically assign rules to CRITICAL/MODERATE based on history
5. **Git Integration**: Auto-validate on commit (pre-commit hook)

## 📝 Best Practices

1. **Backup First**: Always keep a copy of the original playbook
2. **Manual Review**: Review pruned rules before accepting changes
3. **Run Periodically**: Validate every 2-3 epochs during agent execution
4. **Use Style Guide**: Always validate against Style Guide when available
5. **Version Control**: Track playbook changes in Git

## 📚 References

- **Main Script**: `ace/validate_playbook.py`
- **Usage Guide**: `ace/VALIDATE_PLAYBOOK_GUIDE.md`
- **Test Playbook**: `ace/test_playbook_with_conflicts.md`
- **Enhanced Curator**: `ace/ENHANCED_CURATOR_DOCS.md`
- **Framework Summary**: `ace/ACE_FRAMEWORK_ENHANCEMENT_SUMMARY.md`

---

**Status**: ✅ **Ready to use**

Run the test to see it in action:
```bash
python ace/validate_playbook.py --playbook ace/test_playbook_with_conflicts.md
```
