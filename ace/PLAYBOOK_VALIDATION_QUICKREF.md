# Quick Reference: Playbook Validation

## 🚀 Quick Start

```bash
# Basic validation (detect only)
python ace/validate_playbook.py

# Full validation with cleanup
python ace/validate_playbook.py \
    --style-guide docs/style_guide.pdf \
    --output ace/context_playbook_cleaned.md

# Test with sample conflicts
python ace/validate_playbook.py \
    --playbook ace/test_playbook_with_conflicts.md
```

## 📋 What It Detects

| Issue Type | Detection Method | Example |
|------------|------------------|---------|
| **Conflicts** | LLM semantic analysis | "Use snake_case" vs "Use camelCase" |
| **Duplicates** | Embedding similarity >0.85 | "Use camelCase for X" vs "X should be camelCase" |
| **Style Guide Contradictions** | LLM validation | Rule contradicts authoritative Style Guide |

## 🔧 Command-Line Options

```bash
--playbook PATH        # Playbook to validate (default: ace/context_playbook.md)
--style-guide PATH     # Style Guide PDF for validation (optional)
--output PATH          # Save cleaned playbook (default: print to stdout)
```

## 📊 Example Output

```
Original rules: 25
Conflicts detected: 3
Duplicates detected: 2
Style Guide contradictions: 1
Final rules: 19
Rules removed: 6
```

## 🔗 Integration

Add to `ace_agent.py`:

```python
# Periodic validation (every 2 epochs)
if epoch % 2 == 0:
    context_playbook = self.validate_playbook_consistency(context_playbook)
```

## 📚 Full Documentation

- **Usage Guide**: `ace/VALIDATE_PLAYBOOK_GUIDE.md`
- **Summary**: `ace/PLAYBOOK_VALIDATION_SUMMARY.md`
- **Test Playbook**: `ace/test_playbook_with_conflicts.md`
