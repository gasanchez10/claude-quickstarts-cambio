# Review readiness checklist

Use this checklist to satisfy requirements for a private GitHub repository with comprehensive README and reviewer access.

## 0. Don’t own the repo? Create your own private copy

If you cloned someone else’s repo (e.g. `anthropics/claude-quickstarts`), you need a repo you control to make it private and add collaborators.

- **Option A – Fork (recommended):** On GitHub, open the original repo → **Fork** → create the fork under your account/org. Then in your fork: **Settings → General → Danger zone → Change repository visibility** → set to **Private**.
- **Option B – New repo:** On GitHub, **New repository** → name it (e.g. `claude-quickstarts`) → set to **Private** → Create (no README/gitignore).

Then point your local clone at your new repo and push:

```bash
# Add your repo as remote (use your GitHub username or org and repo name)
git remote add myrepo https://github.com/YOUR_USERNAME/claude-quickstarts.git

# Or if you prefer to replace origin instead:
# git remote set-url origin https://github.com/YOUR_USERNAME/claude-quickstarts.git

# Push main and your branch
git push myrepo main
git push -u myrepo docs/readme-and-collaborators
```

Use `myrepo` or `origin` consistently when you push and open PRs.

---

## 1. Repository and README

- [ ] Ensure the GitHub repository is **private**  
  (Repo → Settings → General → Danger zone → Change repository visibility)
- [ ] Ensure the repository has a **comprehensive README**  
  (Root [README.md](README.md) and per-quickstart READMEs as needed)

## 2. Invite collaborators for review

Invite the following GitHub users as **collaborators** with at least **Read** (or **Write**) access so they can review:

| GitHub username   | Role (suggested) |
|-------------------|------------------|
| `lingjiekong`    | Collaborator     |
| `ghamry03`       | Collaborator     |
| `goldmermaid`    | Collaborator     |
| `EnergentAI`     | Collaborator     |

### How to invite (GitHub web)

1. Open the repo on GitHub.
2. Go to **Settings** → **Collaborators** (or **Collaborators and teams**).
3. Click **Add people**.
4. Search for each username above and send an invite (e.g. **Read** or **Write** for review).

### How to invite (GitHub CLI)

If you use [GitHub CLI](https://cli.github.com/) and are logged in (`gh auth login`):

```bash
gh repo add-collaborator <owner>/<repo> lingjiekong --permission read
gh repo add-collaborator <owner>/<repo> ghamry03 --permission read
gh repo add-collaborator <owner>/<repo> goldmermaid --permission read
gh repo add-collaborator <owner>/<repo> EmergentAI --permission read
```

Replace `<owner>/<repo>` with your repository (e.g. `your-org/claude-quickstarts` or `your-username/claude-quickstarts`).
