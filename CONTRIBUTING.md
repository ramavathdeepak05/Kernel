# How We Work Together on ALIS

## Branches

Each developer has their own branch named after them:
- **Deepak** (you) — manages main
- **[Developer 2]** — works on their branch
- **[Developer 3]** — works on their branch

The `main` branch is the production code. **Only Deepak merges into main.**

---

## For Developers: Your Workflow

### When you start a task (To Do → In Progress)
1. Move the Jira ticket to "In Progress"
2. Switch to your branch and get latest code:
   ```
   git checkout [YourName]
   git pull origin main
   ```
3. Start coding

### While you're working
Save your progress regularly **in your branch**:
```
git add .
git commit -m "What you did"
git push
```

### When you're done (In Progress → Ready for Review)
1. Make sure all your changes are pushed
2. Move the Jira ticket to "Ready for Review"
3. **That's it!** Deepak will review and merge your code

### If you're stuck (Blocked)
1. Move the Jira ticket to "Blocked"
2. Add a comment explaining what's blocking you
3. Tag the person who can help

---

## For Deepak: Merging Code

When a developer moves their ticket to "Ready for Review":

1. Review their code on GitHub
2. If it looks good, merge their branch into main:
   ```
   git checkout main
   git pull origin main
   git merge origin/[DeveloperName]
   git push
   ```
3. Move the Jira ticket to "Done"

---

## Quick Commands

| I want to... | Command |
|--------------|---------|
| Switch to my branch | `git checkout [YourName]` |
| Get latest code | `git pull origin main` |
| Save my changes | `git add .` then `git commit -m "message"` |
| Upload my code | `git push` |

---

## Team

| Branch | Person | Role |
|--------|--------|------|
| main | Deepak | Scrum Master (manages merges) |
| Deepak | Deepak | Senior Dev |
