import imaplib
from typing import Any, List

def apply_imap_actions(host: str, port: int, username: str, password: str, mailbox: str, message_ids: list[str | None], actions: list[str], credentials: dict[str, Any], debug: bool = False) -> tuple[List[int], List[int]]:
    """
    Apply 'trash' (move to Trash) actions for Gmail using IMAP. No 'archive'.
    Only messages marked 'trash' will be moved (all others left in INBOX).
    Returns ([], trashed_indices)  (no archive targets; kept in inbox).
    """
    trashed_indices = []
    trash_mailbox = credentials.get("trash_mailbox") or credentials.get("trash_folder") or "[Gmail]/Trash"
    with imaplib.IMAP4_SSL(host, port) as mail:
        mail.login(username, password)
        mail.select(mailbox)
        for idx, (mid, action) in enumerate(zip(message_ids, actions), start=1):
            if not mid or action != "trash":
                continue
            if debug:
                print(f"[NEW-IMAP] Processing trash UID {mid}")
            seq = mid.decode() if isinstance(mid, bytes) else str(mid)
            try:
                # Move email to Trash using IMAP MOVE (RFC 6851)
                # Not all servers support MOVE; fallback to COPY+STORE+EXPUNGE
                res = mail.uid('MOVE', seq, trash_mailbox)
                if res[0] == 'OK':
                    trashed_indices.append(idx)
                    continue
            except Exception as e:
                if debug:
                    print(f"[NEW-IMAP] UID MOVE failed: {e}, trying fallback COPY/STORE")
            try:
                # Fallback: COPY, flag as deleted, expunge
                mail.uid('COPY', seq, trash_mailbox)
                mail.uid('STORE', seq, '+FLAGS', '(\\Deleted)')
                trashed_indices.append(idx)
            except Exception as e:
                if debug:
                    print(f"[NEW-IMAP] Failed FINAL fallback on trash UID {seq}: {e}")
        mail.expunge()
    return [], trashed_indices
