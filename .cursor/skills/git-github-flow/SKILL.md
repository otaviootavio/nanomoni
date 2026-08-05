---
name: git-github-flow
description: Follows project git commit conventions and GitHub issue creation workflow using gh CLI. Use when committing changes, writing commit messages, creating GitHub issues, searching for existing issues, or when the user asks about git workflow or issue creation.
---

# Git and GitHub Flow

## When to Apply

Apply this skill when the user:
- Commits code or asks for commit message suggestions
- Creates or drafts GitHub issues
- Asks about git workflow, staging, or commit format
- Needs to search for existing issues before creating new ones

## Git Commit Flow

### Commit Message Format

```
Short summary line (50-72 chars)

- Detailed bullet point 1
- Detailed bullet point 2
- List key changes and benefits

Closes #40
```

### DOs

- Use `git add <file>` for specific files; **never** `git add -A` or `git add .`
- Include issue numbers in commit messages (e.g., "Closes #40" or "Issue #40")
- Write multi-line commits for complex changes: summary, blank line, bullets, issue reference
- Check `git status` before committing

### DON'Ts

- Don't write vague messages like "fix bug" or "update code"
- Don't stage without reviewing what's being committed
- Don't forget to reference related issues

### Example

```
Extract payment validation into pure functions (Issue #40)

- Created validator modules for Payment, PayWord, and PayTree
- Extracted validation logic from use case services
- Added comprehensive unit tests for all validators

Closes #40
```

## GitHub Issue Creation Flow

### Before Creating an Issue

1. **Search for existing issues**:
   ```bash
   gh issue list --search "your keywords" --state all
   gh issue list --label "bug" --state open
   ```
2. If a related issue exists: add a comment to it instead of creating a duplicate

### Issue Description Structure

Include:
1. **Problem Description** – clear, concise
2. **Why It's Important** – user, system, or development impact
3. **Where It Occurs** – files, functions, components
4. **Possible Fix Suggestions** – if applicable
5. **Reproduction Steps** – if applicable
6. **Environment** – OS, Python version, if relevant

### Create Issue via GH CLI

```bash
# Basic
gh issue create --title "Title" --body "Description"

# From file with labels
gh issue create --title "Title" --body-file issue.md --label "bug,priority:high"
```

### Issue Template

```markdown
## Problem Description
[Clear description]

## Why This Is Important
[Impact: user, system, development]

## Where This Occurs
[File paths, function names, components]

## Possible Fix Suggestions
[Suggested approach, code changes]

## Reproduction Steps (if applicable)
1. Step one
2. Step two

## Environment (if relevant)
- OS, Python version, dependencies
```

## Quick Reference

| Action           | Command or pattern                          |
|-----------------|---------------------------------------------|
| Stage files     | `git add path/to/file`                      |
| Commit format   | Summary + blank + bullets + `Closes #N`     |
| Search issues   | `gh issue list --search "keywords"`         |
| Create issue    | `gh issue create --title "..." --body "..."`|

## Full References

- Git flow details: [.cursor/git-flow-guidelines.md](.cursor/git-flow-guidelines.md)
- Issue creation details: [.cursor/github-issue-creation-flow.md](.cursor/github-issue-creation-flow.md)
