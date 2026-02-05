# How We Work Together on ALIS

## Branches

Each developer has their own branch named after them. For example:
- **Deepak** works on the `Deepak` branch
- **[Other Developer]** works on their own branch

The `main` branch is our "finished" code. Don't push directly to main.

---

## Using Jira + Git Together

Here's what each Jira column means and what you should do:

### To Do
The task is waiting for you. You haven't started yet.

### In Progress
You're actively working on it.

**What to do:**
1. Open your terminal
2. Switch to your branch: `git checkout Deepak`
3. Get the latest code: `git pull origin main`
4. Start coding!

### Blocked
You're stuck and need help or waiting for someone else.

**What to do:**
1. Add a comment in Jira explaining what's blocking you
2. Tag the person who can help
3. Work on something else while you wait

### Ready for Review
You finished coding and want someone to check your work.

**What to do:**
1. Save your work:
   ```
   git add .
   git commit -m "Short description of what you did"
   git push
   ```
2. Go to GitHub and create a Pull Request
3. Move the Jira ticket to "Ready for Review"

### Done
Your code has been reviewed, approved, and merged into main.

---

## Before Your Code Gets Approved

The reviewer will check:
- Does the code follow our ALIS architecture rules?
- Does it work correctly?
- Are there any obvious bugs?

---

## Quick Reference

| I want to... | Command |
|--------------|---------|
| Switch to my branch | `git checkout Deepak` |
| Get latest code | `git pull origin main` |
| Save my changes | `git add .` then `git commit -m "message"` |
| Upload my code | `git push` |

---

## Team Branches

| Branch | Owner |
|--------|-------|
| main | Everyone (protected) |
| Deepak | Deepak |
