import imaplib
from typing import Any


TO_BE_ARCHIVED_LABEL = "TO BE ARCHIVED"
TO_BE_DELETED_LABEL = "TO BE DELETED"
SEEMS_IMPORTANT_LABEL = "SEEMS IMPORTANT"


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
    """Mark a single email for deletion by applying the Gmail label."""
    add_label_by_uid(host, port, username, password, mailbox, uid, TO_BE_DELETED_LABEL, debug=debug)
    return 'trashed'


def archive_email_by_uid(host: str, port: int, username: str, password: str, mailbox: str, uid: str, credentials: dict[str, Any], debug: bool = False):
    """Mark a single email for archive by applying the Gmail label."""
    add_label_by_uid(host, port, username, password, mailbox, uid, TO_BE_ARCHIVED_LABEL, debug=debug)
    return 'archived'


def important_email_by_uid(host: str, port: int, username: str, password: str, mailbox: str, uid: str, debug: bool = False):
    """Mark a single email as important by applying the Gmail label."""
    add_label_by_uid(host, port, username, password, mailbox, uid, SEEMS_IMPORTANT_LABEL, debug=debug)
    return 'kept'
