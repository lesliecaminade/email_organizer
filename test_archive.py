import imaplib



# --- CONFIG SETTINGS: Read from email_credentials.json ---
import json
from pathlib import Path
CRED_FILE = Path(__file__).parent / "email_credentials.json"
with CRED_FILE.open() as f:
    creds = json.load(f)
IMAP_HOST = creds["imap_host"]
IMAP_PORT = int(creds.get("imap_port", 993))
EMAIL = creds["username"]
PASSWORD = creds["password"]
MAILBOX = creds.get("mailbox", "INBOX")

def decode_header_value(header_value):
    from email.header import decode_header as dh
    if not header_value:
        return ''
    parts = dh(header_value)
    decoded_parts = []
    for content, encoding in parts:
        try:
            if isinstance(content, bytes):
                decoded_parts.append(content.decode(encoding or 'utf-8', errors='replace'))
            else:
                decoded_parts.append(content)
        except Exception:
            decoded_parts.append(str(content))
    return ''.join(decoded_parts).strip()

def list_uids(host, port, username, password, mailbox='INBOX', num=10):
    """List the most recent 'num' email UIDs in the mailbox, with subject and current labels (Gmail only)."""
    import email
    with imaplib.IMAP4_SSL(host, port) as mail:
        mail.login(username, password)
        mail.select(mailbox)
        typ, data = mail.uid('SEARCH', None, 'ALL')
        if typ != 'OK' or not data or not data[0]:
            print("No messages found!")
            return []
        uids = data[0].split()
        last_uids = uids[-num:]
        print(f"Last {len(last_uids)} message UIDs, subjects, and labels in {mailbox}:")
        import re
        for i, uid in enumerate(last_uids, 1):
            uid_str = uid.decode() if isinstance(uid, bytes) else uid
            # Fetch both Subject and X-GM-LABELS in a single call
            typ, fetched = mail.uid('FETCH', uid_str, '(BODY.PEEK[HEADER.FIELDS (SUBJECT)] X-GM-LABELS)')
            subject = ''
            labels = ''
            if typ == 'OK' and fetched:
                # The first element contains the FETCH response line
                fetch_line = fetched[0][0].decode(errors='replace') if isinstance(fetched[0], tuple) else ''
                # Extract labels using regex from the fetch_line
                label_match = re.search(r'X-GM-LABELS \((.*?)\)', fetch_line)
                if label_match:
                    raw_labels = label_match.group(1).strip()
                    # Find all quoted label names, then strip leading backslashes
                    matches = re.findall(r'"([^"]+)"', raw_labels)
                    cleaned = [m.lstrip('\\') for m in matches]
                    labels = ", ".join(cleaned)
                # Extract subject from header bytes if available
                if isinstance(fetched[0], tuple) and len(fetched[0]) > 1:
                    raw_header = fetched[0][1]
                    msg = email.message_from_bytes(raw_header)
                    subject = decode_header_value(msg.get('Subject'))
            print(f"{i}. UID {uid_str} | Subject: {subject or '[no subject]'} | Labels: {labels}")
        return last_uids


def archive_email_by_uid(host, port, username, password, mailbox, uid, debug=False):
    """Add a Gmail label to a message by UID so it can be archived later."""
    with imaplib.IMAP4_SSL(host, port) as mail:
        mail.login(username, password)
        mail.select(mailbox)
        # Label names with spaces must be quoted inside the X-GM-LABELS list.
        typ, data = mail.uid('STORE', uid, '+X-GM-LABELS', '("TO BE ARCHIVED")')
        if typ != 'OK':
            raise RuntimeError(f'LABEL ADD failed for UID {uid}: {typ} {data}')
    print(f"Added label 'TO BE ARCHIVED' to email UID {uid} in {mailbox}: {typ} {data}")

import sys
import argparse


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Test IMAP: List UIDs and label email by UID on Gmail")
    subparsers = parser.add_subparsers(dest="command", required=True)

    show_parser = subparsers.add_parser("show", help="Show most recent email UIDs")
    show_parser.add_argument("--num", type=int, default=10, help="How many most recent UIDs to show")

    arch_parser = subparsers.add_parser("archive", help="Add the 'TO BE ARCHIVED' label to a message by UID on Gmail")
    arch_parser.add_argument("uid", type=str, help="Exact UID of email to archive")

    args = parser.parse_args()

    if args.command == "show":
        list_uids(IMAP_HOST, IMAP_PORT, EMAIL, PASSWORD, MAILBOX, num=args.num)
    elif args.command == "archive":
        archive_email_by_uid(IMAP_HOST, IMAP_PORT, EMAIL, PASSWORD, MAILBOX, args.uid)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()