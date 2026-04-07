#!/usr/bin/env bash
# Create GitHub labels for the automated pipeline state machine.
# Usage: bash .github/scripts/setup-labels.sh

set -euo pipefail

REPO="${GITHUB_REPOSITORY:-devangpadhiyar/langrove}"

echo "Creating pipeline labels for $REPO..."

# State machine labels
gh label create "triage"                  --color "d4c5f9" --description "Awaiting pickup by automation"          --repo "$REPO" --force
gh label create "planned"                 --color "0e8a16" --description "Architect has posted implementation plan" --repo "$REPO" --force
gh label create "in-progress"             --color "fbca04" --description "Implementer agent working"               --repo "$REPO" --force
gh label create "review"                  --color "1d76db" --description "PR opened, reviewer checking"            --repo "$REPO" --force
gh label create "done"                    --color "0e8a16" --description "Merged and closed"                       --repo "$REPO" --force

# Control labels
gh label create "blocked"                 --color "b60205" --description "Requires human intervention"             --repo "$REPO" --force
gh label create "human-review-required"   --color "e11d48" --description "Must not auto-merge"                     --repo "$REPO" --force
gh label create "force-auto"              --color "5319e7" --description "Override complexity gate"                 --repo "$REPO" --force

# Complexity labels
gh label create "complexity:small"        --color "c5def5" --description "Single file, <100 lines changed"         --repo "$REPO" --force
gh label create "complexity:medium"       --color "bfd4f2" --description "Multi-file, same module"                 --repo "$REPO" --force
gh label create "complexity:large"        --color "0075ca" --description "Cross-module, >300 lines"                --repo "$REPO" --force

echo "Done! All pipeline labels created."
