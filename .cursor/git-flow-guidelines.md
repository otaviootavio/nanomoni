# Git Flow Guidelines

## DOs ✅

### Committing Changes
- **DO** use `git commit` with explicit file paths or staged files
- **DO** write descriptive commit messages that reference issues
- **DO** include issue numbers in commit messages (e.g., "Issue #40" or "Closes #40")
- **DO** write multi-line commit messages with:
  - A clear summary line
  - A blank line
  - Detailed description of changes
  - Reference to related issues

### Commit Message Format
```
Short summary line (50-72 chars)

- Detailed bullet point 1
- Detailed bullet point 2
- List key changes and benefits

Closes #40
```

### Example Good Commit Message
```
Extract business logic validation into pure functions (Issue #40)

- Created validator modules for Payment, PayWord, and PayTree payment processing
- Extracted validation logic from use case services into pure functions
- Added comprehensive unit tests for all validators (39 tests)
- Refactored payment services to use validators for better testability
- Fixed type annotations and linting errors

This enables:
- Unit testing validation rules in isolation (no mocks needed)
- Reusable validation logic across contexts
- Clear separation of business logic from infrastructure
- Better test coverage (>90% for validators)

Closes #40
```

## DON'Ts ❌

### Staging Files
- **DON'T** use `git add -A` (adds all files, including untracked)
- **DON'T** use `git add .` (adds all files in current directory)
- **DON'T** stage files without reviewing what's being committed

### Commit Messages
- **DON'T** write vague commit messages like "fix bug" or "update code"
- **DON'T** forget to reference related issues
- **DON'T** write single-line commits for complex changes

## Best Practices

1. **Review before committing**: Always check `git status` to see what will be committed
2. **Stage selectively**: Use `git add <file>` for specific files you want to commit
3. **Reference issues**: Always include issue numbers in commit messages when applicable
4. **Write meaningful messages**: Future you (and your team) will thank you
5. **Use "Closes #X"**: This automatically closes issues when merged to main branch

## Workflow Example

```bash
# 1. Check what's changed
git status

# 2. Stage specific files (if needed)
git add src/nanomoni/application/vendor/use_cases/payment_validators.py
git add tests/unit/application/vendor/test_payment_validators.py

# 3. Commit with descriptive message
git commit -m "Extract payment validation logic (Issue #40)

- Created payment_validators.py with pure validation functions
- Added unit tests for all validation rules
- Refactored PaymentService to use validators

Closes #40"
```

## Notes

- The `.cursor` folder is for IDE-specific configuration and guidelines
- These guidelines are based on project-specific requirements
- Always follow your team's git workflow conventions
