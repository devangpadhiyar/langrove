---
description: Automated pipeline meta-learnings and coordination knowledge
---

# Pipeline Automation

## Label State Machine
```
New Issue → [triage] → [planned] → [in-progress] → [review] → [done]
                                         ↑               |
                                         +-- (changes-requested)
```

## Coordination Rules
- Only ONE issue may be `in-progress` at a time
- `complexity:large` issues skipped unless `force-auto` label present
- Max 2 review cycles before `human-review-required`
- 500-line diff limit on PRs

## Learnings
<!-- Pipeline agents append new learnings below this line -->
