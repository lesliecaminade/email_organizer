# Hello World Email Agent

This is a tiny Python AI agent that can run immediately in demo mode, then check today's real emails over IMAP when credentials are ready.

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
cp openai_credentials.example.json openai_credentials.json
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

## Run the demo now

```bash
python email_agent.py
```

Demo mode uses sample emails and a local priority scorer, so it runs without private credentials or OpenAI calls.

## Run against your real inbox

```bash
python email_agent.py --live
```

Optional: check fewer emails from each account:

```bash
python email_agent.py --live --limit 10
```

## Mark emails as important or not important

You can label messages by their index in the list. These labels will be saved to `feedback.json` and affect future runs.

```bash
python email_agent.py --important 1,3
python email_agent.py --not-important 2
python email_agent.py --live --important 1 --not-important 2
```

## What it does

The script prints a hello-world message, gathers emails, and prints a ranked summary of the most important items. If `openai_credentials.json` contains a real API key, it uses OpenAI for the summary. If not, it uses a simple local scorer so the app still runs.