# SETUP — your one-time checklist

Do these in order. Each takes about 2–10 minutes. **Never paste passwords or keys into the chat**: keys go in the `.env` file (step 6).

## ✅ Already done
- Python 3.13, Git, and VS Code are installed on this PC.

## 1. GitHub account (stores the code, runs nightly jobs)
1. Go to https://github.com/signup and sign up with your Gmail.
2. Tell Claude your GitHub **username** (not your password).

## 2. Supabase (our data warehouse)
1. Go to https://supabase.com and click **Start your project** → **Continue with GitHub**.
2. Click **New project**. Name it `data-hub`, choose the region closest to you, and set a database password. **Save that password somewhere safe.**
3. Choose the **Free** plan. If it asks for a card, stop and tell Claude.
4. When the project is ready, go to **Project Settings → Database → Connection string → URI** and copy it. It goes in `.env` (step 6).

## 3. Google Cloud (lets the code read Google Sheets)
1. Go to https://console.cloud.google.com and sign in with Gmail. Create a project called `data-hub`.
2. Under **APIs & Services → Library**, enable **Google Sheets API** and **Google Drive API**.
3. Under **APIs & Services → Credentials → Create credentials → Service account**, name it `pipeline`. Then go to **Keys → Add key → JSON**. A file downloads.
4. Move that file into this project folder and rename it `google_key.json`.
5. Copy the service account's email (it looks like `pipeline@data-hub-xxxx.iam.gserviceaccount.com`). **Share each source Google Sheet with that email** as Viewer.
   - If you don't own a sheet, use **File → Make a copy** first, or ask the owner to share it.

## 3b. Google login key (reads sheets AS YOU - needed for company-only sheets)
1. https://console.cloud.google.com → top bar: make sure project **data-hub** is selected.
2. Search bar → **Google Auth Platform** → **Get started**.
   - App name: `Data Hub Pipeline` · Support email: your email → Next
   - Audience: **Internal** if offered (company accounts only), otherwise **External** → Next
   - Contact email: your email → Next → tick agree → **Create**
3. If you chose External: left menu **Audience** → **Test users** → **+ Add users** → your work email → Save.
4. Left menu **Clients** → **+ Create client** → Application type **Desktop app** → Name `pipeline` → **Create**.
5. Click **Download JSON**. Rename the file to `google_oauth_client.json` and move it into the project folder.
6. Tell Claude. First run opens a browser: sign in with your work account → **Allow**.
   ("Google hasn't verified this app" → **Continue**: it's your own app.)

## 4. Airtable token (lets the code read Airtable bases)
1. Go to https://airtable.com/create/tokens → **Create token**.
2. Add the scopes `data.records:read` and `schema.bases:read`, then add the bases you need.
3. Copy the token. It goes in `.env`.

## 5. Free data sites that need sign-up
Claude will give you a short list as each one comes up. For each site:
- Sign up yourself with Gmail. Use the free plan only, and never enter card details.
- If you log in inside this app's **built-in browser**, Claude can then browse it for you.

## 6. The `.env` file (where keys live)
Claude will create an empty `.env` file. You open it in VS Code and fill in your values:
```
SUPABASE_DB_URL=postgresql://...
AIRTABLE_TOKEN=pat...
GOOGLE_KEY_FILE=google_key.json
SEC_USER_AGENT=DataHub Pipeline your-email@example.com
```
This file stays on your PC and is never uploaded.
