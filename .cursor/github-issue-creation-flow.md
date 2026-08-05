# GitHub Issue Creation Flow

## Overview

This guide describes the workflow for creating GitHub issues using the GitHub CLI (`gh`). The process ensures we avoid duplicate issues, provide comprehensive context, and follow best practices for issue reporting.

## Prerequisites

1. **Install GitHub CLI**: Ensure `gh` is installed and authenticated
   ```bash
   gh auth login
   ```

2. **Verify authentication**:
   ```bash
   gh auth status
   ```

## Workflow Steps

### Step 1: Check for Existing Related Issues

Before creating a new issue, search for existing issues that might be related to the problem you're reporting.

#### Search by Title/Keywords
```bash
# Search for issues with specific keywords
gh issue list --search "payment channel validation" --state all

# Search for open issues
gh issue list --search "your keywords here" --state open

# Search for closed issues (might be duplicates or already fixed)
gh issue list --search "your keywords here" --state closed
```

#### Search by Label
```bash
# List issues with specific labels
gh issue list --label "bug" --state open
gh issue list --label "enhancement" --state open
```

#### View Issue Details
```bash
# View a specific issue to check if it's related
gh issue view <issue-number>
```

**If you find a related issue:**
- Add a comment to the existing issue instead of creating a duplicate
- Reference the existing issue number in your comment
- If the issue is closed but the problem persists, consider reopening it or creating a new one with a reference

### Step 2: Prepare Issue Description

A well-structured issue should include:

1. **Problem Description**: Clear, concise explanation of the issue
2. **Why It's Important**: Impact on users, system, or development
3. **Where It Occurs**: Specific files, functions, or components affected
4. **Possible Fix Suggestions**: Ideas for resolution (if applicable)
5. **Reproduction Steps**: How to reproduce the issue (if applicable)
6. **Environment Details**: OS, Python version, dependencies (if relevant)

### Step 3: Create the Issue Using GH CLI

#### Basic Issue Creation
```bash
# Create issue with title and body from command line
gh issue create \
  --title "Issue Title Here" \
  --body "Issue description here"
```

#### Create Issue from File
```bash
# Create issue with body from a markdown file
gh issue create \
  --title "Issue Title Here" \
  --body-file issue-description.md
```

#### Create Issue with Labels
```bash
# Create issue with appropriate labels
gh issue create \
  --title "Issue Title Here" \
  --body "Issue description" \
  --label "bug,priority:high"
```

#### Create Issue with Assignee
```bash
# Create issue and assign to a team member
gh issue create \
  --title "Issue Title Here" \
  --body "Issue description" \
  --assignee @username
```

## Issue Description Template

Use this template when creating issues:

```markdown
## Problem Description
[Clear, concise description of the issue]

## Why This Is Important
[Explain the impact and why this issue matters:
- User impact (if applicable)
- System impact
- Development impact
- Security implications (if any)]

## Where This Occurs
[Specify the location:
- File paths: `src/nanomoni/path/to/file.py`
- Function/class names: `PaymentChannelService.validate()`
- Component: Payment processing, API endpoint, etc.
- Related code snippets (if helpful)]

## Possible Fix Suggestions
[Ideas for resolution:
- Suggested approach
- Code changes needed
- Alternative solutions
- References to similar fixes]

## Reproduction Steps (if applicable)
1. Step one
2. Step two
3. Expected vs actual behavior

## Environment (if relevant)
- OS: [Linux/macOS/Windows]
- Python version: [3.x]
- Dependencies: [specific versions if relevant]
```

## Complete Workflow Example

```bash
# Step 1: Search for existing issues
gh issue list --search "payment channel validation error" --state all

# Step 2: If no related issue found, prepare issue description
cat > /tmp/issue-description.md << 'EOF'
## Problem Description
Payment channel validation fails silently when invalid payment index is provided, causing incorrect state updates.

## Why This Is Important
- **User Impact**: Users may experience incorrect payment processing without clear error messages
- **System Impact**: Payment state can become inconsistent, leading to reconciliation issues
- **Security**: Invalid payments might be accepted, causing financial discrepancies

## Where This Occurs
- **File**: `src/nanomoni/application/issuer/use_cases/payment_channel.py`
- **Function**: `PaymentChannelService.process_payment()`
- **Line**: ~145-160
- **Related**: `src/nanomoni/domain/vendor/payment_channel.py`

## Possible Fix Suggestions
1. Add explicit validation for payment index bounds before processing
2. Raise `PaymentIndexOutOfBoundsError` instead of silently failing
3. Add logging for validation failures
4. Update unit tests to cover edge cases

## Reproduction Steps
1. Create a payment channel with max index 100
2. Attempt to process payment with index 101
3. Observe: No error raised, state updated incorrectly
4. Expected: `PaymentIndexOutOfBoundsError` should be raised
EOF

# Step 3: Create the issue
gh issue create \
  --title "Payment channel validation fails silently for out-of-bounds index" \
  --body-file /tmp/issue-description.md \
  --label "bug,priority:medium" \
  --assignee @maintainer

# Clean up
rm /tmp/issue-description.md
```

## Best Practices

### DOs ✅

1. **DO** search thoroughly before creating new issues
2. **DO** provide clear, actionable descriptions
3. **DO** include file paths and line numbers when possible
4. **DO** explain why the issue matters (impact)
5. **DO** suggest possible fixes if you have ideas
6. **DO** use appropriate labels (bug, enhancement, documentation, etc.)
7. **DO** reference related issues or PRs if applicable
8. **DO** include code snippets or examples when helpful

### DON'Ts ❌

1. **DON'T** create duplicate issues without checking first
2. **DON'T** write vague descriptions like "it doesn't work"
3. **DON'T** forget to specify where the issue occurs
4. **DON'T** skip explaining why it's important
5. **DON'T** create issues without context or reproduction steps
6. **DON'T** assign issues without checking with the assignee first

## Useful GH CLI Commands

```bash
# List all open issues
gh issue list

# List issues with specific state
gh issue list --state open
gh issue list --state closed
gh issue list --state all

# View issue details
gh issue view <number>

# Add comment to existing issue
gh issue comment <number> --body "Additional information"

# Close an issue
gh issue close <number>

# Reopen a closed issue
gh issue reopen <number>

# List available labels
gh label list

# Create issue interactively (prompts for title and body)
gh issue create
```

## Integration with Development Workflow

1. **During Development**: Create issues for bugs found during testing
2. **Code Review**: Create issues for improvements suggested in PRs
3. **Production Issues**: Create issues for bugs reported by users
4. **Technical Debt**: Create issues for refactoring opportunities

## Notes

- Always check for existing issues to avoid duplicates
- Well-documented issues are easier to triage and fix
- Include fix suggestions when possible to accelerate resolution
- Reference issue numbers in commit messages and PRs
- Use "Closes #X" in PR descriptions to auto-close issues
