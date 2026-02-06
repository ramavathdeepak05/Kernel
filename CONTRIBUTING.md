# ALIS Developer Guide

Welcome to the ALIS team! This guide will help you get started and work effectively with the team.

---

## 🚀 Getting Started

### Step 1: Clone the Repository
If you haven't already, clone the repo:
```
git clone https://github.com/ramavathdeepak05/ALIS-Production.git
cd ALIS-Production
```

### Step 2: Create Your Branch
Each developer has their own branch. Ask Deepak to create one for you, or create it yourself:
```
git checkout -b [YourName]
git push -u origin [YourName]
```

### Step 3: Get the Latest Code
Before starting any work, always get the latest code from main:
```
git checkout [YourName]
git pull origin main
```

---

## 📋 Daily Workflow

### Starting a Task

1. **Pick a ticket** from the Jira board (from "To Do")
2. **Move it** to "In Progress"
3. **Get latest code:**
   ```
   git checkout [YourName]
   git pull origin main
   ```
4. **Start coding!**

### Saving Your Work

Save your progress regularly **in your branch**:
```
git add .
git commit -m "Short description of what you did"
git push
```

💡 **Tip:** Commit often! Small, frequent commits are better than one big commit.

### When You're Done

1. Make sure all your changes are pushed (`git push`)
2. Move the Jira ticket to **"Ready for Review"**
3. **That's it!** Deepak will review and merge your code into main

### If You're Stuck

1. Move the Jira ticket to **"Blocked"**
2. Add a comment explaining what's blocking you
3. Tag Deepak or the person who can help
4. Work on something else while you wait

---

## 📌 Jira Board Explained

| Column | What it means |
|--------|---------------|
| **To Do** | Tasks waiting to be picked up |
| **In Progress** | You're actively working on it |
| **Blocked** | You're stuck and need help |
| **Ready for Review** | You're done, waiting for Deepak to review |
| **Done** | Merged into main ✅ |

---

## 🔧 Quick Command Reference

| I want to... | Command |
|--------------|---------|
| Switch to my branch | `git checkout [YourName]` |
| Get latest code from main | `git pull origin main` |
| Save my changes | `git add .` → `git commit -m "message"` |
| Upload my code | `git push` |
| See what branch I'm on | `git branch` |
| See my changes | `git status` |

---

## 👥 Team

| Person | Role | Branch |
|--------|------|--------|
| **Deepak** | Scrum Master / Senior Dev | `Deepak` + manages `main` |
| Akhil | Developer | `Akhil` |
| Srikar | Developer | `Srikar` |
| External | External Contributors | `external` |
| External1 | External Contributors | `external1` |

---

## ❓ Need Help?

- **Git issues?** Ask Deepak
- **Code questions?** Add a comment in Jira or message the team
- **Blocked?** Move your ticket to "Blocked" and tag someone

Happy coding! 🎉
