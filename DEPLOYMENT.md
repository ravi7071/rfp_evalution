# Deployment Checklist (GitHub + Streamlit Community Cloud)

This checklist covers:
1) Pushing your local project to GitHub
2) Deploying from GitHub to Streamlit Community Cloud
3) Securely configuring `GEMINI_API_KEY` in Streamlit Secrets

---

## 1) Pre-Deployment Checks (Local)

- [ ] Confirm app runs locally:

```powershell
venv\Scripts\activate
streamlit run streamlit_app.py
```

- [ ] Confirm required files exist:
  - `streamlit_app.py`
  - `requirements.txt`
  - `README.md`

- [ ] Ensure `.env` is ignored and not committed.

---

## 2) Push Local Repository to GitHub

Run these commands from project root in PowerShell.

### 2.1 Initialize Git (if not already initialized)

```powershell
git init
```

### 2.2 Set main branch

```powershell
git branch -M main
```

### 2.3 Stage all files

```powershell
git add .
```

### 2.4 Commit

```powershell
git commit -m "Complete Phases 1-5: ingestion, validation gate, scoring, persistence, past-runs viewer"
```

### 2.5 Create a new GitHub repo

- Go to `https://github.com/new`
- Create a repository (public or private)
- Do **not** initialize with README if your local repo already has one

### 2.6 Add remote and push

Replace `<YOUR_GITHUB_USERNAME>` and `<YOUR_REPO_NAME>`:

```powershell
git remote add origin https://github.com/<YOUR_GITHUB_USERNAME>/<YOUR_REPO_NAME>.git
git push -u origin main
```

If remote already exists:

```powershell
git remote set-url origin https://github.com/<YOUR_GITHUB_USERNAME>/<YOUR_REPO_NAME>.git
git push -u origin main
```

---

## 3) Deploy to Streamlit Community Cloud

### 3.1 Sign in

- Go to `https://share.streamlit.io/`
- Sign in with GitHub

### 3.2 Create app

- Click **New app**
- Select:
  - **Repository**: `<YOUR_GITHUB_USERNAME>/<YOUR_REPO_NAME>`
  - **Branch**: `main`
  - **Main file path**: `streamlit_app.py`
- Click **Deploy**

### 3.3 Verify first build

- Wait for dependency install and app startup logs
- Open the generated public URL

---

## 4) Configure Secrets Securely (`GEMINI_API_KEY`)

Because Gemini provider requires an API key, configure it in Streamlit Cloud Secrets.

### 4.1 Open app settings

- In Streamlit Cloud dashboard, open your deployed app
- Click **Settings** (gear icon)
- Open **Secrets**

### 4.2 Add secret value

Paste this in Secrets editor:

```toml
GEMINI_API_KEY = "your_real_gemini_api_key_here"
```

Click **Save**.

### 4.3 Redeploy/restart

- Streamlit usually restarts automatically after secrets update.
- If not, click **Reboot app**.

### 4.4 Runtime usage note

- This app supports direct API key input in UI for `gemini` and `openai`.
- You can optionally use Secrets-backed env vars for fallback behavior in hosted deployments.
- Never hardcode keys in source files or commit them to GitHub.

---

## 5) Post-Deployment Validation Checklist

- [ ] App URL loads successfully
- [ ] PDF upload works
- [ ] `gemini` provider evaluation works with valid key
- [ ] API key missing case is properly blocked in UI
- [ ] Final leaderboard and scorecards render
- [ ] Past Runs viewer loads historical runs
- [ ] Download JSON works

---

## 6) Optional: Ollama on Cloud Note

Ollama local endpoint (`http://localhost:11434`) is intended for local development and is typically **not** available in Streamlit Cloud runtime.

For deployed cloud usage, prefer hosted providers (`gemini`, `openai`).

