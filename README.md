# Email Agent

This is a tiny Python AI agent that triages your inbox. It runs immediately in demo mode, then can check today's real emails over IMAP when credentials are ready.

## Step 1: Create a virtual environment

From this folder, run:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

## Step 2: Install dependencies

```bash
pip install -r requirements.txt
```

## Step 3: Create credential files

Copy the example files:

```bash
cp email_credentials.example.json email_credentials.json
cp ollama_credentials.example.json ollama_credentials.json
cp google_credentials.example.json google_credentials.json
```

Then edit these new files with your real values.

To check more than one inbox, put each account in the `accounts` array in `email_credentials.json`:

```json
{
	"accounts": [
		{
			"name": "Primary Gmail",
			"imap_host": "imap.gmail.com",
			"imap_port": 993,
			"username": "first@example.com",
			"password": "first-app-password",
			"mailbox": "INBOX"
		},
		{
			"name": "Second Gmail",
			"imap_host": "imap.gmail.com",
			"imap_port": 993,
			"username": "second@example.com",
			"password": "second-app-password",
			"mailbox": "INBOX"
		}
	]
}
```

For Gmail, use an app password rather than your normal account password. Common IMAP hosts include:

- Gmail: `imap.gmail.com`
- Outlook / Microsoft 365: `outlook.office365.com`
- Yahoo: `imap.mail.yahoo.com`

## Configure the AI backend

The agent uses a local Ollama server by default. Edit `ollama_credentials.json` to point at your server and model:

```json
{
	"url": "http://localhost:11434",
	"model": "llama3.1"
}
```

## Run the demo now

```bash
python email_agent.py
```

Demo mode uses sample emails and a local priority scorer, so it runs without private credentials or AI calls.

## Run against your real inbox

```bash
python email_agent.py --live
```

Optional: check fewer emails from each account:

```bash
python email_agent.py --live --limit 10
```

## How it triages emails

For each email, the agent asks the AI to classify it into one of three labels:

- **KEEP** — Actionable now: needs a reply, decision, approval, meeting, payment, or task.
- **TO BE ARCHIVED** — Not actionable but worth saving: newsletters, FYIs, automated reports, completed threads.
- **DELETE** — Spam, junk, scams, or irrelevant.

In `--live` mode the agent applies the corresponding Gmail action:

- **KEEP** → adds the `KEEP` label and leaves the email in the inbox.
- **TO BE ARCHIVED** → adds the `TO BE ARCHIVED` label and removes the email from the Inbox.
- **DELETE** → permanently deletes the email.

## Calendar integration

If `google_credentials.json` is configured, the agent also scans **KEEP** and **TO BE ARCHIVED** emails for calendar-worthy dates and creates events in the corresponding Gmail account's primary Google Calendar. On first run, a browser OAuth prompt will appear and a `google_token.json` file will be saved for future runs.

To set up Google Calendar access:

1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a project and enable the **Google Calendar API**.
3. Create OAuth 2.0 credentials for a **Desktop app**.
4. Download the client secrets JSON and paste the values into `google_credentials.json`.
5. Run the agent with `--live`; authorize access when prompted.

## What it does

The script prints a hello-world message, gathers emails, classifies them, applies IMAP actions in live mode, creates calendar events when configured, and prints a ranked summary of the most important kept items.