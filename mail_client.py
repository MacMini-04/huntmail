# app/mail_client.py
import subprocess
import json
from typing import List, Dict, Any, Optional


class MailClientError(Exception):
    pass


def _run_osascript(script: str) -> str:
    try:
        completed = subprocess.run(
            ["osascript", "-e", script],
            check=True,
            text=True,
            capture_output=True,
        )
        return completed.stdout.strip()
    except subprocess.CalledProcessError as exc:
        raise MailClientError(
            f"AppleScript error: {exc.stderr or exc.stdout}"
        ) from exc


def get_inbox_emails(limit: int = 20) -> List[Dict[str, Any]]:
    """
    Return a small list of emails from the Inbox.

    For now we just grab subject, sender, and a short preview.
    We invent an id based on message id or a synthetic key.
    """

    # AppleScript returns JSON for simplicity
    script = f'''
    set output to "["
    tell application "Mail"
        set theInbox to inbox
        set theMessages to messages of theInbox
        set cnt to count of theMessages
        set maxCount to {limit}
        repeat with i from 1 to cnt
            if i > maxCount then exit repeat
            set theMessage to item i of theMessages
            set theId to message id of theMessage
            set theSubject to subject of theMessage
            set theSender to sender of theMessage
            set theContent to content of theMessage

            set thePreview to (characters 1 thru 200 of theContent) as string

            set output to output & "{{\\"id\\":\\"" & theId & "\\",\\"subject\\":\\"" & my escape_json(theSubject) & "\\",\\"sender\\":\\"" & my escape_json(theSender) & "\\",\\"preview\\":\\"" & my escape_json(thePreview) & "\\"}},"
        end repeat
    end tell

    if output ends with "," then
        set output to text 1 thru -2 of output
    end if
    set output to output & "]"
    return output

    on escape_json(theText)
        set theText to replace_chars(theText, "\\", "\\\\")
        set theText to replace_chars(theText, "\"", "\\\"")
        set theText to replace_chars(theText, return, " ")
        set theText to replace_chars(theText, linefeed, " ")
        return theText
    end escape_json

    on replace_chars(this_text, search_string, replacement_string)
        set AppleScript's text item delimiters to search_string
        set the item_list to every text item of this_text
        set AppleScript's text item delimiters to replacement_string
        set this_text to the item_list as string
        set AppleScript's text item delimiters to ""
        return this_text
    end replace_chars
    '''

    raw = _run_osascript(script)
    if not raw:
        return []

    try:
        emails = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MailClientError(f"Failed to parse JSON from AppleScript: {exc}\n{raw[:500]}")

    return emails


def move_email_to_mailbox(message_id: str, target_mailbox_name: str) -> None:
    """
    Move a message with the given message id into the specified mailbox.

    For now we look for the mailbox by name in all accounts.
    """
    script = f'''
    tell application "Mail"
        set theMessage to missing value
        set theInbox to inbox
        set theMessages to messages of theInbox

        repeat with m in theMessages
            if (message id of m as string) is "{message_id}" then
                set theMessage to m
                exit repeat
            end if
        end repeat

        if theMessage is missing value then
            error "Message with id {message_id} not found in Inbox"
        end if

        set targetMailbox to missing value
        set theAccounts to every account
        repeat with a in theAccounts
            set theMailboxes to mailboxes of a
            repeat with mb in theMailboxes
                if (name of mb as string) is "{target_mailbox_name}" then
                    set targetMailbox to mb
                    exit repeat
                end if
            end repeat
            if targetMailbox is not missing value then exit repeat
        end repeat

        if targetMailbox is missing value then
            error "Mailbox named {target_mailbox_name} not found"
        end if

        move theMessage to targetMailbox
    end tell
    '''

    _run_osascript(script)
