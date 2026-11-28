"""iMessage tools, answered on the Mac mini: four read-only ones and imessage_send.

homelab-mcp never touches chat.db or Messages. Each imessage_* call travels over the same
ssh link as the bus_* tools (bus.py: dedicated key, forced command, pinned
host key) to bus-gateway on the mini, which hands it to the iMessage service
there (mac-mini-collector, `collector imessage-serve`): a LaunchAgent under the
collector's Full-Disk-Access launcher that opens chat.db read-only and listens
only on a 0600 Unix socket. No new secret, no new port, nothing new listening.

The service validates every argument and caps every answer (limit 1..100,
each text cut at 1,000 characters, about 50 KB per answer); verification codes
and one-time passwords are dropped there with the nightly collector's filter,
tapbacks and system rows are skipped. The clamps below only keep obviously
out-of-range numbers from making a round trip. Nothing here logs message text,
names or handles.

imessage_send (since 2026-11-28) asks Messages on the mini to send text and/or
one image into a chat that already exists. Every limit is enforced there, not
here (mac-mini-collector's collector/imessage_send.py and bus-gateway): existing
chats only, matched exactly, an ambiguous name is an error listing the matches;
2,000 characters and one PNG/JPEG/HEIC/GIF image up to 10 MB; 10 sends an hour;
an append-only audit log; off switches. This side only rejects obviously
oversized input before it travels, and labels the tool as acting so claude.ai
asks before using it.
"""

from __future__ import annotations

from typing import Awaitable, Callable

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
# Sending can't be undone and reaches other people: labelled like the acting bus tools, so claude.ai asks first.
SENDS = {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": True}

DEFAULT_LIMIT, MAX_LIMIT = 25, 100
DEFAULT_HOURS, MAX_HOURS = 48, 24 * 31
MAX_SEND_TEXT = 2000
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_B64 = 4 * ((MAX_IMAGE_BYTES + 2) // 3)

IMESSAGE_INSTRUCTIONS = """\
 The imessage_* tools read Mark's iMessages/SMS from his Mac mini, live (what \
Messages has right now, seconds old). The four read tools are strictly \
read-only. Use imessage_unanswered to see what needs him, imessage_threads for \
an overview of active chats, imessage_recent for the latest messages and \
imessage_search to find one. imessage_send sends a message (text, optionally \
one image) as Mark into a chat that already exists: use it only when Mark asked \
for that message to that chat in this conversation, and show him the exact text \
and recipient first. It can't start a new conversation, react, mark read or \
delete; an ambiguous chat name comes back as an error listing the matches (pick \
one chat_id with Mark, never guess); at most 10 sends an hour. Verification codes and one-time passwords are removed before anything \
is returned; tapbacks and system rows are skipped. Times are ISO 8601 with \
offset in US Eastern; senders are contact names when known, "me" for Mark.\
"""

Call = Callable[[str, dict], Awaitable[dict]]


def clamp(value, lo: int, hi: int, default: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(n, hi))


def register_imessage_tools(mcp: FastMCP, call: Call | None) -> list[str]:
    """Add the four imessage_* tools when the Mac mini bus is configured. Returns their names."""
    if call is None:
        return []

    async def imessage_recent(since: str | None = None, limit: int = DEFAULT_LIMIT) -> dict:
        """Mark's newest iMessages/SMS, read-only and live (seconds old), newest first.

        Each message: time (ISO 8601 with offset, US Eastern), chat (group name or
        contact), sender (contact name, else the number/email; "me" for Mark),
        is_from_me, is_group, text (cut at 1,000 characters). since: an ISO
        date/time or a duration like "24h" or "7d"; omit for the newest overall.
        limit 1-100 (default 25). Verification codes and one-time passwords are
        removed; tapbacks and group-event rows are skipped. Nothing can be sent or
        changed from here.
        """
        return await call("imessage_recent", {"since": since, "limit": clamp(limit, 1, MAX_LIMIT, DEFAULT_LIMIT)})

    async def imessage_search(query: str, contact: str | None = None, since: str | None = None,
                              limit: int = DEFAULT_LIMIT) -> dict:
        """Search the text of Mark's iMessages/SMS (read-only, live), newest first.

        query: case-insensitive substring (max 200 characters). contact: only chats
        that person is in, by contact name, phone number or email (a group chat
        counts if they're a participant); contact_found=false in the answer means
        nobody matched. since: ISO date/time or "24h"/"7d". limit 1-100 (default
        25). Verification codes are removed; tapbacks and system rows are skipped.
        """
        return await call("imessage_search", {"query": query, "contact": contact, "since": since,
                                              "limit": clamp(limit, 1, MAX_LIMIT, DEFAULT_LIMIT)})

    async def imessage_threads(since: str | None = None, limit: int = DEFAULT_LIMIT) -> dict:
        """Chats with recent activity (read-only, live), most recently active first.

        Each thread: chat (group name or contact), is_group, participants, last
        message time, last sender, last message preview (200 characters),
        messages_in_window, my_last_reply_time and incoming_since_my_last_reply:
        incoming messages in the window newer than Mark's last message or tapback
        in that chat (0 means he has replied since). since: ISO date/time or a
        duration, default "7d". limit 1-100 (default 25). Verification codes are
        removed; tapbacks and system rows don't count as messages.
        """
        return await call("imessage_threads", {"since": since, "limit": clamp(limit, 1, MAX_LIMIT, DEFAULT_LIMIT)})

    async def imessage_unanswered(hours: int = DEFAULT_HOURS, limit: int = DEFAULT_LIMIT) -> dict:
        """Incoming iMessages/SMS from the last N hours that Mark hasn't followed up on (read-only, live).

        A message counts as unanswered when Mark has sent nothing (no message, no
        tapback) in that chat since it arrived. Newest first, each with time, chat,
        sender, text and is_group (group chats are included and marked); by_chat
        gives the count per chat and messages_total the number before `limit`.
        hours 1-744 (default 48). limit 1-100 (default 25). Verification codes and
        one-time passwords are removed; tapbacks and system rows are skipped.
        """
        return await call("imessage_unanswered", {"hours": clamp(hours, 1, MAX_HOURS, DEFAULT_HOURS),
                                                  "limit": clamp(limit, 1, MAX_LIMIT, DEFAULT_LIMIT)})

    async def imessage_send(chat: str, text: str, image_base64: str | None = None,
                            image_filename: str | None = None) -> dict:
        """Send an iMessage/SMS as Mark into a chat that already exists, through Messages on his Mac mini.

        Only when Mark asked for this exact message to this chat; it can't be
        unsent. chat: the chat_id from imessage_threads (most precise), a contact's
        full name, a phone number or email Mark already has a chat with, or a group
        chat's name as imessage_threads shows it. Nothing is guessed: no match, or
        more than one (e.g. a contact with both a phone and an email chat, or two
        groups with one name), returns an error listing the candidates with their
        chat_id; ask Mark which one and call again with it. Never a new recipient.
        text: up to 2,000 characters ("" to send only the image). image_base64:
        optional, one PNG, JPEG, HEIC or GIF up to 10 MB; image_filename optional
        (its extension must match). At most 10 sends per hour. Returns the message
        as read back from Messages' database (status sent, delivered or pending),
        or an error saying what went wrong; check imessage_recent before retrying
        an uncertain send.
        """
        if not isinstance(chat, str) or not chat.strip() or len(chat) > 200:
            raise ToolError("`chat` must be a chat_id, contact name, phone number, email or group name "
                            "(up to 200 characters).")
        if text is not None and len(text) > MAX_SEND_TEXT:
            raise ToolError(f"`text` is {len(text)} characters; the limit is {MAX_SEND_TEXT}. Nothing was sent.")
        if image_base64 is not None and len(image_base64) > MAX_IMAGE_B64 + 1024:
            raise ToolError("The image is larger than 10 MB. Nothing was sent.")
        if not (text or "").strip() and not image_base64:
            raise ToolError("Nothing to send: give `text`, an image, or both.")
        return await call("imessage_send", {"chat": chat, "text": text, "image_base64": image_base64 or None,
                                            "image_filename": image_filename if image_base64 else None})

    tools = [imessage_recent, imessage_search, imessage_threads, imessage_unanswered]
    for fn in tools:
        mcp.tool(fn, annotations=READ_ONLY)
    mcp.tool(imessage_send, annotations=SENDS)
    return [fn.__name__ for fn in tools] + [imessage_send.__name__]
