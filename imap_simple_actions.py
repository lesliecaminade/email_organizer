import imaplib
from typing import Any


TO_BE_ARCHIVED_LABEL = "TO BE ARCHIVED"
DELETED_LABEL = "DELETED"
SEEMS_IMPORTANT_LABEL = "KEEP"


def format_gmail_label(label: str) -> str:
    escaped = label.replace('\\', '\\\\').replace('"', '\\"')
    return f'("{escaped}")'


def add_label_by_uid(host: str, port: int, username: str, password: str, mailbox: str, uid: str, label: str, debug: bool = False) -> None:
    """Add a Gmail label to a single email by UID."""
    with imaplib.IMAP4_SSL(host, port) as mail:
        mail.login(username, password)
        mail.select(mailbox)
        uid_str = uid.decode() if isinstance(uid, bytes) else str(uid)
        typ, data = mail.uid('STORE', uid_str, '+X-GM-LABELS', format_gmail_label(label))
        if typ != 'OK':
            raise RuntimeError(f"LABEL ADD failed for UID {uid_str}: {typ} {data}")
    if debug:
        print(f"Added label '{label}' to email UID {uid_str} in {mailbox}")


def delete_email_by_uid(host: str, port: int, username: str, password: str, mailbox: str, uid: str, debug: bool = False):
    """Permanently delete a single email by UID using IMAP STORE + EXPUNGE."""
    with imaplib.IMAP4_SSL(host, port) as mail:
        mail.login(username, password)
        mail.select(mailbox)
        uid_str = uid.decode() if isinstance(uid, bytes) else str(uid)

        # Mark the email as deleted
        typ, data = mail.uid('STORE', uid_str, '+FLAGS', '\\Deleted')
        if typ != 'OK':
            raise RuntimeError(f"STORE \\Deleted failed for UID {uid_str}: {typ} {data}")

        # Permanently remove the email from the mailbox
        typ, data = mail.expunge()
        if typ != 'OK':
            raise RuntimeError(f"EXPUNGE failed for UID {uid_str}: {typ} {data}")

        if debug:
            print(f"Permanently deleted email UID {uid_str} from {mailbox}")

    return 'DELETED'


def archive_email_by_uid(host: str, port: int, username: str, password: str, mailbox: str, uid: str, credentials: dict[str, Any], debug: bool = False):
    """Archive a single email by UID: remove it from the Inbox label and add the TO BE ARCHIVED label."""
    with imaplib.IMAP4_SSL(host, port) as mail:
        mail.login(username, password)
        mail.select(mailbox)
        uid_str = uid.decode() if isinstance(uid, bytes) else str(uid)

        # Add the TO BE ARCHIVED label for visibility
        add_typ, add_data = mail.uid('STORE', uid_str, '+X-GM-LABELS', format_gmail_label(TO_BE_ARCHIVED_LABEL))
        if add_typ != "OK":
            raise RuntimeError(f"LABEL ADD failed for UID {uid_str}: {add_typ} {add_data}")

        # Remove the Gmail Inbox label so the message leaves the inbox
        # Use the special \\Inbox flag, not the literal label name "Inbox".
        typ, data = mail.uid('STORE', uid_str, '-X-GM-LABELS', '(\\Inbox)')
        if typ != "OK":
            raise RuntimeError(f"ARCHIVE failed for UID {uid_str}: {typ} {data}")

        if debug:
            print(f"Archived email UID {uid_str}: added '{TO_BE_ARCHIVED_LABEL}' label and removed Inbox label")

    return 'TO BE ARCHIVED'


def important_email_by_uid(host: str, port: int, username: str, password: str, mailbox: str, uid: str, debug: bool = False):
    """Mark a single email as KEEP by applying the Gmail label."""
    add_label_by_uid(host, port, username, password, mailbox, uid, SEEMS_IMPORTANT_LABEL, debug=debug)
    return 'KEEP'
