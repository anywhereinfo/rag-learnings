# Playbook Validation Script - Usage Guide

## Overview

The `validate_playbook.py` script analyzes existing context playbooks to detect and prune:
1. **Conflicting rules** - Contradictory statements (e.g., "Use snake_case" vs "Use camelCase")
2. **Duplicate rules** - Semantically similar rules (>0.85 similarity)
3. **Style Guide contradictions** - Rules that contradict the authoritative Style Guide

## Installation

No additional dependencies needed beyond the existing ACE environment:
```bash
source ~/envs/tf/bin/activate
# Already have: google-cloud-aiplatform, scikit-learn, pypdf
```

## Usage

### Basic Usage (Detect Only)
```bash
python ace/validate_playbook.py
```
This will:
- Load `ace/context_playbook.md`
- Detect conflicts and duplicates
- Print results to stdout

### With Style Guide Validation
```bash
python ace/validate_playbook.py --style-guide docs/style_guide.pdf
```
This adds Style Guide validation to detect contradictions.

### Save Cleaned Playbook
```bash
python ace/validate_playbook.py --output ace/context_playbook_cleaned.md
```
This saves the pruned playbook to a new file.

### Full Validation with All Options
```bash
python ace/validate_playbook.py \
    --playbook ace/context_playbook.md \
    --style-guide docs/style_guide.pdf \
    --output ace/context_playbook_cleaned.md
```

## Command-Line Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--playbook` | `ace/context_playbook.md` | Path to playbook file to validate |
| `--style-guide` | None | Path to Style Guide PDF (optional) |
| `--output` | None | Path to save cleaned playbook (if omitted, prints to stdout) |

## What It Does

### Phase 1: Conflict Detection
- Compares all rules pairwise
- Uses LLM to detect semantic conflicts
- Example conflict: "Use snake_case for operationId" vs "Use camelCase for operationId"

### Phase 2: Duplicate Detection
- Embeds all rules using text-embedding-004
- Calculates cosine similarity
- Flags duplicates with >0.85 similarity

### Phase 3: Style Guide Validation (Optional)
- Loads Style Guide PDF
- Validates each rule against Style Guide
- Rejects rules that contradict authoritative standards

### Pruning Strategy
1. **Conflicts**: Keeps the more specific rule (longer text)
2. **Duplicates**: Keeps the first occurrence
3. **Style Guide contradictions**: Removes all contradicting rules

## Example Output

```
============================================================
PLAYBOOK VALIDATION & CONFLICT PRUNING
============================================================
✓ Loaded playbook from ace/context_playbook.md
✓ Parsed 25 rules from playbook

🔍 Detecting conflicts among 25 rules...
  ⚠ Conflict #1:
    Rule A: Use snake_case for operationId
    Rule B: Use camelCase for operationId
    Reason: Contradictory naming conventions
✓ Found 1 conflicts

🔍 Detecting duplicates among 25 rules...
  ⚠ Duplicate #1 (similarity: 0.92):
    Rule A: Use camelCase for operationId
    Rule B: operationId should be in camelCase format
✓ Found 1 duplicates

✂️ Pruning 1 conflicts...
  ✂️ Removing (less specific): Use snake_case for operationId
✓ Pruned 1 rules, 24 remaining

✂️ Pruning 1 duplicates...
  ✂️ Removing duplicate: operationId should be in camelCase format
✓ Pruned 1 rules, 23 remaining

============================================================
SUMMARY
============================================================
Original rules: 25
Conflicts detected: 1
Duplicates detected: 1
Style Guide contradictions: 0
Final rules: 23
Rules removed: 2
============================================================
```

## Integration with ACE Agent

You can also add this as a periodic validation step in the main agent:

```python
# In ace_agent.py, add a method:
def validate_playbook_consistency(self, playbook_text):
    """
    Validate entire playbook for internal consistency.
    Run this every N epochs.
    """
    from validate_playbook import PlaybookValidator
    
    validator = PlaybookValidator(model_name=self.model_name)
    
    # Parse and validate
    rules = validator.parse_playbook_rules(playbook_text)
    conflicts = validator.detect_conflicts(rules)
    
    if conflicts:
        print(f"⚠️  Found {len(conflicts)} internal conflicts!")
        rules = validator.prune_conflicts(rules, conflicts)
        return validator.generate_cleaned_playbook(rules)
    
    return playbook_text

# In run() method:
if epoch % 2 == 0:  # Every 2 epochs
    context_playbook = self.validate_playbook_consistency(context_playbook)
```

## Performance Notes

- **LLM Calls**: ~N*(N-1)/2 for conflict detection (pairwise comparison)
- **Execution Time**: ~30-60s for 25 rules (depends on LLM latency)
- **Cost**: ~$0.01-0.05 per validation (using Gemini Flash)

## Troubleshooting

### "GOOGLE_API_KEY not set"
```bash
export GOOGLE_API_KEY='your-api-key-here'
```

### "Playbook not found"
Check the path:
```bash
ls -la ace/context_playbook.md
```

### "Too many LLM calls"
For large playbooks (>50 rules), consider:
- Running validation less frequently
- Using a faster model (gemini-2.0-flash-exp)
- Implementing caching for conflict checks

## Best Practices

1. **Run before committing**: Validate playbook before saving to version control
2. **Periodic validation**: Run every 2-3 epochs during agent execution
3. **Manual review**: Always review pruned rules before accepting changes
4. **Backup first**: Keep a copy of the original playbook before pruning

## Example Workflow

```bash
# 1. Backup current playbook
cp ace/context_playbook.md ace/context_playbook.backup.md

# 2. Run validation with Style Guide
python ace/validate_playbook.py \
    --style-guide docs/style_guide.pdf \
    --output ace/context_playbook_cleaned.md

# 3. Review changes
diff ace/context_playbook.md ace/context_playbook_cleaned.md

# 4. If satisfied, replace original
mv ace/context_playbook_cleaned.md ace/context_playbook.md
```
