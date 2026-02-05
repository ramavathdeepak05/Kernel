# Contributing to ALIS Production

## Branch Strategy

```
main                ← Production-ready code (protected)
  ├── Deepak        ← Developer branch
  ├── [Developer2]  ← Developer branch
  └── [Developer3]  ← Developer branch
```

Each developer works on their own named branch. When work is complete, create a Pull Request to `main`.

---

## Git + Jira Workflow

### Jira Board Columns

| Column | When to Use | Git Action |
|--------|-------------|------------|
| **To Do** | Story is assigned but not started | — |
| **In Progress** | Actively coding | Create/switch to your branch |
| **Blocked** | Waiting on dependency or clarification | Add blocker comment in Jira |
| **Ready for Review** | Code complete, PR created | Push + Create PR |
| **Done** | PR merged to main | Merge PR |

---

## Step-by-Step Workflow

### 1. Pick a Story (To Do → In Progress)
```bash
# Switch to your branch
git checkout Deepak
git pull origin main  # Get latest from main
```
Move the Jira ticket to **In Progress**.

### 2. Code & Commit
```bash
git add .
git commit -m "E01-S03: Implement RBAC middleware"
```
Commit message format: `<Epic-Story>: <Description>`

### 3. Push & Create PR (In Progress → Ready for Review)
```bash
git push origin Deepak
```
- Create a Pull Request on GitHub: `Deepak` → `main`
- Link the Jira ticket in the PR description
- Move Jira ticket to **Ready for Review**

### 4. Address Review Feedback
If changes are requested:
```bash
git add .
git commit -m "E01-S03: Address review feedback"
git push
```

### 5. Merge (Ready for Review → Done)
Once approved:
- Squash and merge the PR
- Delete the feature branch (optional)
- Move Jira ticket to **Done**

---

## Handling Blockers

If blocked:
1. Move Jira ticket to **Blocked**
2. Add a comment explaining the blocker
3. Tag the relevant person
4. Continue with other work if possible

---

## Code Review Checklist

Before approving a PR, verify:
- [ ] Layer(s) referenced in docstrings
- [ ] State transitions are legal (Layer 3)
- [ ] Global Locks are checked (Layer 4)
- [ ] No cloud LLM dependencies
- [ ] Tests pass (if applicable)

---

## Current Team Branches

| Branch | Developer |
|--------|-----------|
| `main` | Protected (production) |
| `Deepak` | Deepak |
