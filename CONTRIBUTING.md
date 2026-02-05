# Contributing to ALIS Production

## Branch Strategy

```
main          ← Production-ready code (protected)
  └── develop ← Integration branch for features
        ├── feature/E02-xxx  ← Epic/Story branches
        ├── feature/M1-xxx   ← Module-specific work
        └── fix/xxx          ← Bug fixes
```

## Workflow

### 1. Starting New Work
```bash
# Always start from develop
git checkout develop
git pull origin develop

# Create your feature branch
git checkout -b feature/E02-S01-domain-models
```

### 2. Naming Conventions
- **Features**: `feature/<epic>-<story>-<short-description>`
  - Example: `feature/E02-S01-domain-models`
- **Module work**: `feature/<module>-<description>`
  - Example: `feature/M1-admissions-wizard`
- **Bug fixes**: `fix/<issue-id>-<description>`
  - Example: `fix/123-state-transition-error`

### 3. Committing
```bash
git add .
git commit -m "E02-S01: Add domain models for student entity"
```

Commit message format: `<Epic-Story>: <Description>`

### 4. Pushing & Pull Requests
```bash
git push -u origin feature/E02-S01-domain-models
```

Then create a Pull Request on GitHub targeting `develop`.

### 5. Merging to Main
- Only after PR review and approval
- Squash merge preferred for clean history
- `main` should always be deployable

## Code Review Checklist

Before approving a PR, verify:
- [ ] Layer(s) are explicitly referenced in docstrings
- [ ] Decision is declared (for wizards)
- [ ] State transitions are legal (Layer 3)
- [ ] Global Locks are checked (Layer 4)
- [ ] Authority is respected (Layer 5)
- [ ] Failure modes are handled
- [ ] No cloud LLM dependencies

## Current Branches

| Branch | Purpose |
|--------|---------|
| `main` | Production code |
| `develop` | Integration branch |
