import imaplib
from typing import Any

def imap_action_single(host: str, port: int, username: str, password: str, mailbox: str, message_uid: str, action: str, credentials: dict[str, Any], debug: bool = False) -> str:
    """Perform IMAP action for a single email. Returns the action actually taken ('kept', 'archived', 'trashed')."""
    trash_mailbox = credentials.get("trash_mailbox") or credentials.get("trash_folder") or "[Gmail]/Trash"
    archive_mailbox = credentials.get("archive_mailbox") or credentials.get("archive_folder") or "[Gmail]/All Mail"
    with imaplib.IMAP4_SSL(host, port) as mail:
        mail.login(username, password)
        mail.select(mailbox)
        seq = message_uid.decode() if isinstance(message_uid, bytes) else str(message_uid)
        if action == "trash":
            try:
                # Move to Trash, prefer MOVE
                res = mail.uid('MOVE', seq, trash_mailbox)
                if res[0] == 'OK':
                    return 'trashed'
            except Exception as e:
                if debug:
                    print(f"[IMAP] UID MOVE failed (trash): {e}, trying COPY/STORE")
            try:
                mail.uid('COPY', seq, trash_mailbox)
                mail.uid('STORE', seq, '+FLAGS', '(\\Deleted)')
                mail.expunge()
                return 'trashed'
            except Exception as e:
                if debug:
                    print(f"[IMAP] Fallback failed for trash: {e}")
                return 'keep'  # If all else fails, keep
        elif action == "archive":
            try:
                # Gmail archive: remove from INBOX, but do not delete; prefer Gmail extension if available
                typ, data = mail.uid('STORE', seq, '-X-GM-LABELS', '(\\Inbox)')
                if debug:
                    print(f"[IMAP] UID STORE -X-GM-LABELS (\\Inbox) -> {typ}, {data}")
                if typ == 'OK':
                    return 'archived'
                raise Exception(f"UID STORE failed: {typ} {data}")
            except Exception as e:
                if debug:
                    print(f"[IMAP] Archive Gmail label remove failed: {e}")
                try:
                    mail.uid('COPY', seq, archive_mailbox)
                    mail.uid('STORE', seq, '+FLAGS', '(\\Deleted)')
                    mail.expunge()
                    return 'archived'
                except Exception as f2:
                    if debug:
                        print(f"[IMAP] Archive fallback failed: {f2}")
                    return 'keep'
        else:
            return 'kept'  # No action, retained in INBOX
