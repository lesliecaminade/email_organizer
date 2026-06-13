import argparse
import email
import hashlib
import imaplib
import json
from dataclasses import dataclass
from datetime import date
from email.header import decode_header
from email.message import Message
from pathlib import Path
from typing import Any


EMAIL_CREDENTIALS_PATH = Path("email_credentials.json")
OPENAI_CREDENTIALS_PATH = Path("openai_credentials.json")
FEEDBACK_PATH = Path("feedback.json")
CHARS_PER_TOKEN_ESTIMATE = 4
MAX_EMAIL_PREVIEW_TOKENS = 300
MAX_SINGLE_EMAIL_PROMPT_TOKENS = 500
MAX_BATCH_EMAIL_PROMPT_TOKENS = 250
MAX_DIGEST_PROMPT_TOKENS = 5500
PLACEHOLDER_VALUES = {
    "",
    "sk-your-openai-api-key",
    "first-app-password",
    "first@example.com",
    "second-app-password",
    "second@example.com",
    "your-email@example.com",
    "your-email-app-password",
    "your-second-email@example.com",
    "your-second-email-app-password",
}


@dataclass
class EmailMessage:
    sender: str
    subject: str
    date_header: str
    body_preview: str
    message_key: str
    account_name: str = ""


@dataclass
class EmailAccount:
    name: str
    host: str
    port: int
    username: str
    password: str
    mailbox: str

    def as_credentials(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "imap_host": self.host,
            "imap_port": self.port,
            "username": self.username,
            "password": self.password,
            "mailbox": self.mailbox,
        }


def make_message_key(sender: str, subject: str, date_header: str, account_identifier: str = "") -> str:
    raw = f"{account_identifier}|{sender}|{subject}|{date_header}"
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()


def load_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {path}. Copy the matching .example.json file and fill in your credentials."
        )

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def get_email_account_entries(raw_credentials: Any) -> list[dict[str, Any]]:
    if isinstance(raw_credentials, list):
        entries = raw_credentials
    elif isinstance(raw_credentials, dict):
        account_list = None
        for key in ("accounts", "emails", "email_accounts"):
            if isinstance(raw_credentials.get(key), list):
                account_list = raw_credentials[key]
                break
        entries = account_list if account_list is not None else [raw_credentials]
    else:
        raise ValueError("email_credentials.json must contain an account object or a list of account objects.")

    if not entries:
        raise ValueError("email_credentials.json does not contain any email accounts.")
    if not all(isinstance(entry, dict) for entry in entries):
        raise ValueError("Each email account entry in email_credentials.json must be a JSON object.")
    return entries


def load_email_accounts() -> list[EmailAccount]:
    raw_credentials = load_json(EMAIL_CREDENTIALS_PATH)
    accounts = []

    for index, credentials in enumerate(get_email_account_entries(raw_credentials), start=1):
        host = credentials.get("imap_host") or credentials.get("host")
        port = int(credentials.get("imap_port", 993))
        username = credentials.get("username") or credentials.get("email")
        password = credentials.get("password") or credentials.get("app_password")
        mailbox = credentials.get("mailbox", "INBOX")
        name = credentials.get("name") or username or f"Account {index}"

        if not host:
            raise ValueError(f"Email account {index} is missing imap_host.")
        if not looks_configured(username) or not looks_configured(password):
            raise ValueError(
                f"Email account {index} still looks like a placeholder. "
                "Update email_credentials.json or run without --live."
            )

        accounts.append(
            EmailAccount(
                name=name,
                host=host,
                port=port,
                username=username,
                password=password,
                mailbox=mailbox,
            )
        )

    return accounts


def looks_configured(value: str | None) -> bool:
    if not value:
        return False
    normalized = value.strip()
    return bool(
        normalized
        and normalized not in PLACEHOLDER_VALUES
        and not normalized.startswith("your-")
        and "@example." not in normalized
    )


def decode_mime_header(value: str | None) -> str:
    if not value:
        return ""

    parts = decode_header(value)
    decoded_parts = []
    for content, encoding in parts:
        if isinstance(content, bytes):
            decoded_parts.append(content.decode(encoding or "utf-8", errors="replace"))
        else:
            decoded_parts.append(content)
    return "".join(decoded_parts).strip()


def parse_index_list(raw: str | None) -> list[int]:
    if not raw:
        return []
    return [int(item) for item in raw.replace(" ", "").split(",") if item.strip()]


def extract_text(message: Message) -> str:
    if message.is_multipart():
        for part in message.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition", "")).lower()
            if content_type == "text/plain" and "attachment" not in disposition:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
        return ""

    payload = message.get_payload(decode=True)
    if not payload:
        return ""
    charset = message.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace")


def estimate_token_count(text: str) -> int:
    return max(1, (len(text) + CHARS_PER_TOKEN_ESTIMATE - 1) // CHARS_PER_TOKEN_ESTIMATE)


def guard_text_for_token_budget(text: str, max_tokens: int, label: str = "content") -> str:
    """Trim text to a conservative token budget using a rough character-based estimate."""
    normalized = " ".join((text or "").split())
    if estimate_token_count(normalized) <= max_tokens:
        return normalized

    max_chars = max_tokens * CHARS_PER_TOKEN_ESTIMATE
    notice = f" [truncated {label}; original estimate {estimate_token_count(normalized)} tokens] "
    keep_chars = max(0, max_chars - len(notice))
    if keep_chars <= 0:
        return notice.strip()
    head_chars = max(1, int(keep_chars * 0.75))
    tail_chars = max(0, keep_chars - head_chars)
    tail = normalized[-tail_chars:] if tail_chars else ""
    return f"{normalized[:head_chars]}{notice}{tail}"


def format_email_for_prompt(message: EmailMessage, max_body_tokens: int) -> str:
    account_line = f"Account: {message.account_name}\n" if message.account_name else ""
    safe_preview = guard_text_for_token_budget(message.body_preview, max_body_tokens, "email body")
    return (
        f"{account_line}"
        f"From: {message.sender}\n"
        f"Subject: {message.subject}\n"
        f"Date: {message.date_header}\n"
        f"Preview: {safe_preview}"
    )


def build_email_digest(
    messages: list[EmailMessage],
    max_body_tokens: int,
    max_total_tokens: int = MAX_DIGEST_PROMPT_TOKENS,
) -> str:
    digest_parts = []
    used_tokens = 0

    for index, message in enumerate(messages, start=1):
        entry = format_email_for_prompt(message, max_body_tokens)
        entry_tokens = estimate_token_count(entry)
        if used_tokens + entry_tokens > max_total_tokens:
            remaining = len(messages) - index + 1
            digest_parts.append(f"[{remaining} additional email(s) omitted to stay within the token budget.]")
            break
        digest_parts.append(entry)
        used_tokens += entry_tokens

    return "\n\n".join(digest_parts)


def fetch_todays_emails(
    limit: int = 25,
    accounts: list[EmailAccount] | None = None,
) -> tuple[list[EmailMessage], list[str | None], list[EmailAccount | None]]:
    messages: list[EmailMessage] = []
    message_id_list: list[str | None] = []
    message_accounts: list[EmailAccount | None] = []

    for account in accounts or load_email_accounts():
        with imaplib.IMAP4_SSL(account.host, account.port) as mail:
            mail.login(account.username, account.password)
            mail.select(account.mailbox)

            # Search for messages explicitly with the Gmail "Inbox" label (using X-GM-LABELS).
            status, data = mail.uid('SEARCH', None, '(X-GM-LABELS "\\\\Inbox")')
            if status != "OK" or not data or not data[0]:
                continue

            message_ids = data[0].split()
            if limit is not None:
                message_ids = message_ids[-limit:]
            for message_id in reversed(message_ids):
                uid = message_id.decode() if isinstance(message_id, bytes) else str(message_id)
                status, fetched = mail.uid("FETCH", uid, "(RFC822)")
                if status != "OK" or not fetched:
                    continue

                raw_email = fetched[0][1]
                parsed = email.message_from_bytes(raw_email)
                body = extract_text(parsed)
                sender = decode_mime_header(parsed.get("From"))
                subject = decode_mime_header(parsed.get("Subject")) or "(no subject)"
                date_header = decode_mime_header(parsed.get("Date"))
                messages.append(
                    EmailMessage(
                        sender=sender,
                        subject=subject,
                        date_header=date_header,
                        body_preview=guard_text_for_token_budget(body, MAX_EMAIL_PREVIEW_TOKENS, "email body"),
                        message_key=make_message_key(sender, subject, date_header, account.username),
                        account_name=account.name,
                    )
                )
                message_id_list.append(uid)
                message_accounts.append(account)
    return messages, message_id_list, message_accounts


def demo_emails() -> list[EmailMessage]:
    return [
        EmailMessage(
            sender="Maya Chen <maya@example.org>",
            subject="Incident response tabletop moved to 2 PM today",
            date_header="Today, 8:15 AM",
            body_preview=(
                "Please confirm you can attend the incident response tabletop at 2 PM. "
                "We need one person from each team to review roles and escalation steps."
            ),
            message_key=make_message_key(
                "Maya Chen <maya@example.org>",
                "Incident response tabletop moved to 2 PM today",
                "Today, 8:15 AM",
            ),
        ),
        EmailMessage(
            sender="Billing <billing@example.net>",
            subject="Invoice due tomorrow",
            date_header="Today, 9:05 AM",
            body_preview="Your June platform invoice is due tomorrow. Please review and approve payment.",
            message_key=make_message_key(
                "Billing <billing@example.net>",
                "Invoice due tomorrow",
                "Today, 9:05 AM",
            ),
        ),
        EmailMessage(
            sender="Newsletter <news@example.com>",
            subject="Weekly product updates",
            date_header="Today, 10:40 AM",
            body_preview="Here are this week's release notes, feature highlights, and community stories.",
            message_key=make_message_key(
                "Newsletter <news@example.com>",
                "Weekly product updates",
                "Today, 10:40 AM",
            ),
        ),
    ]


def demo_emails_with_ids() -> tuple[list[EmailMessage], list[None], list[None]]:
    messages = demo_emails()
    return messages, [None] * len(messages), [None] * len(messages)


def summarize_locally(messages: list[EmailMessage]) -> str:
    if not messages:
        return "I did not find any emails from today."

    priority_terms = {
        "incident": 5,
        "urgent": 5,
        "deadline": 4,
        "due": 4,
        "confirm": 3,
        "meeting": 3,
        "invoice": 3,
        "approve": 3,
        "security": 5,
        "response": 4,
    }

    ranked: list[tuple[int, EmailMessage]] = []
    for message in messages:
        searchable_text = f"{message.subject} {message.body_preview}".lower()
        score = sum(weight for term, weight in priority_terms.items() if term in searchable_text)
        ranked.append((score, message))

    ranked.sort(key=lambda item: item[0], reverse=True)

    lines = ["Most important emails for today:"]
    for index, (score, message) in enumerate(ranked[:5], start=1):
        reason = "contains action or timing signals" if score else "lower priority informational message"
        lines.append(
            f"{index}. {message.subject}\n"
            f"   From: {message.sender}\n"
            f"   Why it matters: {reason}.\n"
            f"   Next action: Review this message and respond if it needs your input."
        )

    return "\n".join(lines)


def classify_messages(messages: list[EmailMessage]) -> list[str]:
    """
    Uses OpenAI to decide for each message: 'keep' (INBOX) or 'trash' (move to Trash).
    Key criteria: 'keep' for actionable emails (require a reply, action, or decision), 'trash' for everything else.
    """
    credentials = load_json(OPENAI_CREDENTIALS_PATH)
    api_key = credentials.get("api_key")
    model = credentials.get("model", "gpt-4o-mini")
    if not looks_configured(api_key):
        # fallback: keep old heuristic if OpenAI key is not configured
        actions = []
        trash_terms = ["lottery", "winner", "free money", "viagra", "porn", "click here"]
        for msg in messages:
            text = f"{msg.subject} {msg.body_preview} {msg.sender}".lower()
            if any(term in text for term in trash_terms):
                actions.append("trash")
            else:
                actions.append("keep")
        return actions

    from openai import OpenAI
    client = OpenAI(api_key=api_key)

    email_digest = build_email_digest(messages, max_body_tokens=MAX_BATCH_EMAIL_PROMPT_TOKENS)

    sys_prompt = (
        "You are an email triage assistant. "
        "Classify each message as either 'keep' (if actionable: requires a reply, user action, or decision), or 'trash' (if not actionable, or spam, or irrelevant).\n"
        "Output a JSON array with one value per input email: 'keep' or 'trash'. "
        "Do NOT include any commentary—just output the array."
    )

    # Make the list of emails the user sees
    prompt = (
        f"Classify the following emails as 'keep' or 'trash' based on whether they're actionable or not.\n"
        f"Emails:\n{email_digest}\n---"
    )

    raw = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": prompt},
        ]
    ).choices[0].message.content

    import json as _json
    # Try to robustly extract the list (LLM may sometimes add text)
    if '[' in raw:
        raw = raw[raw.index('['):]
    try:
        parsed = _json.loads(raw)
    except Exception:
        # fallback (just in case OpenAI output is not valid JSON)
        parsed = []
        for line in raw.splitlines():
            v = line.strip().strip('"')
            if v in ("keep", "trash"):
                parsed.append(v)
    # Ensure exactly one action per message
    result = []
    for i in range(len(messages)):
        try:
            v = parsed[i]
        except Exception:
            v = "keep"
        if v not in ("keep", "trash"):
            v = "keep"
        result.append(v)
    return result



from imap_simple_actions import archive_email_by_uid, delete_email_by_uid, important_email_by_uid


def get_mailbox_count(host: str, port: int, username: str, password: str, mailbox: str) -> int:
    """Return total number of messages in the mailbox (ALL)."""
    try:
        with imaplib.IMAP4_SSL(host, port) as mail:
            mail.login(username, password)
            mail.select(mailbox)
            status, data = mail.search(None, "ALL")
            if status != "OK" or not data or not data[0]:
                return 0
            return len(data[0].split())
    except Exception:
        return 0


def confirm_mailbox_reduction(host: str, port: int, username: str, password: str, mailbox: str, before_count: int) -> tuple[int, bool]:
    """Recheck mailbox count after triage and confirm the count has decreased."""
    after_count = get_mailbox_count(host, port, username, password, mailbox)
    return after_count, after_count < before_count


def summarize_with_openai(messages: list[EmailMessage]) -> str:
    credentials = load_json(OPENAI_CREDENTIALS_PATH)
    api_key = credentials.get("api_key")
    if not looks_configured(api_key):
        return summarize_locally(messages)

    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    model = credentials.get("model", "gpt-4o-mini")

    if not messages:
        return "Hello world from your email agent. I did not find any emails from today."

    email_digest = build_email_digest(messages, max_body_tokens=MAX_BATCH_EMAIL_PROMPT_TOKENS)

    prompt = (
        "You are a practical email triage assistant. "
        "Summarize the most important emails from today. "
        "Prioritize deadlines, security issues, direct requests, meetings, invoices, and anything requiring action. "
        + f"Today's emails:\n{email_digest}"
    )

    response = client.responses.create(
        model=model,
        input=prompt,
    )
    return response.output_text


def apply_labels(messages: list[EmailMessage], feedback: dict[str, int], indices: list[int], label: int) -> list[int]:
    updated = []
    for index in indices:
        if 1 <= index <= len(messages):
            key = messages[index - 1].message_key
            feedback[key] = label
            updated.append(index)
    return updated


def print_messages(messages: list[EmailMessage], feedback: dict[str, int]) -> None:
    print("Today's emails:")
    for index, message in enumerate(messages, start=1):
        label = feedback.get(message.message_key)
        label_text = " [important]" if label == 1 else " [not important]" if label == 0 else ""
        print(
            f"{index}. {message.subject}{label_text}\n"
            f"   From: {message.sender}\n"
            f"   Date: {message.date_header}\n"
            f"   Preview: {message.body_preview[:140]}...\n"
        )
    print()


def classify_message_single(message, credentials, debug=False):
    """Use OpenAI to classify a single EmailMessage: return 'keep', 'archive', or 'trash'."""
    api_key = credentials.get("api_key")
    model = credentials.get("model", "gpt-4o-mini")
    if not api_key or api_key.startswith("sk-your-openai-api-key"):
        return 'keep'  # fallback demo only
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    sys_prompt = (
        "You are an email triage assistant. "
        "Classify this message as 'keep', 'archive', or 'trash'. "
        "'archive' means it is not actionable but worth saving and should be labeled TO BE ARCHIVED. "
        "'trash' means it should be labeled TO BE DELETED. "
        "'keep' means it is actionable and should be labeled SEEMS IMPORTANT. "
        "Only output one word: keep, archive, or trash."
    )
    email_body = format_email_for_prompt(message, max_body_tokens=MAX_SINGLE_EMAIL_PROMPT_TOKENS)
    response = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": email_body}],
    ).choices[0].message.content.strip().lower()
    if response in ('keep', 'archive', 'trash'):
        return response
    return 'keep'

def main() -> None:
    parser = argparse.ArgumentParser(description="Triage and automate your email inbox, one message at a time.")
    parser.add_argument("--limit", type=int, default=25, help="Maximum emails per account to inspect")
    parser.add_argument("--live", action="store_true", help="Use your real inbox instead of demo emails")
    parser.add_argument("--debug", action="store_true", help="Show IMAP debug output during live triage")
    args = parser.parse_args()

    print("Hello world from your email agent.\n")
    if args.live:
        email_accounts = load_email_accounts()
        account_names = ", ".join(account.name for account in email_accounts)
        print(f"Checking today's inbox across {len(email_accounts)} account(s): {account_names}\n")
        messages, message_uids, message_accounts = fetch_todays_emails(limit=args.limit, accounts=email_accounts)
        credentials = load_json(OPENAI_CREDENTIALS_PATH)
        debug = args.debug
    else:
        debug = False
        print("Running demo mode with sample emails. Add --live when your credentials are ready.\n")
        messages, message_uids, message_accounts = demo_emails_with_ids()
        credentials = load_json(OPENAI_CREDENTIALS_PATH)

    kept = []
    archived = []
    trashed = []

    for idx, (msg, uid, account) in enumerate(zip(messages, message_uids, message_accounts), start=1):
        action = classify_message_single(msg, credentials, debug=debug)
        result = action
        # IMAP labeling for triage decisions (only live mode)
        if args.live and uid and account:
            if action == 'trash':
                result = delete_email_by_uid(
                    account.host,
                    account.port,
                    account.username,
                    account.password,
                    account.mailbox,
                    uid,
                    debug=debug,
                )
            elif action == 'archive':
                result = archive_email_by_uid(
                    account.host,
                    account.port,
                    account.username,
                    account.password,
                    account.mailbox,
                    uid,
                    account.as_credentials(),
                    debug=debug,
                )
            else:
                result = important_email_by_uid(
                    account.host,
                    account.port,
                    account.username,
                    account.password,
                    account.mailbox,
                    uid,
                    debug=debug,
                )
        if result in ('keep', 'kept'):
            kept.append(msg)
        elif result == 'archive' or result == 'archived':
            archived.append(msg)
        elif result == 'trash' or result == 'trashed':
            trashed.append(msg)
        account_label = f" | Account: {msg.account_name}" if msg.account_name else ""
        print(f"[{idx}/{len(messages)}] Action: {action.upper()}{account_label} | Subject: {msg.subject}")

    # Most important kept emails
    print('\n----- MOST IMPORTANT KEPT EMAILS -----')
    print(summarize_with_openai(kept))
    print('\nTriage Summary:')
    print(f' KEPT:     {len(kept)}')
    print(f' ARCHIVED: {len(archived)}')
    print(f' TRASHED:  {len(trashed)}')


if __name__ == "__main__":
    main()