"""Read-only iMessage tools, answered on the Mac mini.

homelab-mcp never touches chat.db. Each imessage_* call travels over the same
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
"""

from __future__ import annotations

from typing import Awaitable, Callable

from fastmcp import FastMCP

READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}

DEFAULT_LIMIT, MAX_LIMIT = 25, 100
DEFAULT_HOURS, MAX_HOURS = 48, 24 * 31

IMESSAGE_INSTRUCTIONS = """\
 The imessage_* tools read Mark's iMessages/SMS from his Mac mini, live (what \
Messages has right now, seconds old) and strictly read-only: nothing can be \
sent, replied to, reacted to, marked read or deleted from here. Use \
imessage_unanswered to see what needs him, imessage_threads for an overview of \
active chats, imessage_recent for the latest messages and imessage_search to \
find one. Verification codes and one-time passwords are removed before anything \
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

    tools = [imessage_recent, imessage_search, imessage_threads, imessage_unanswered]
    for fn in tools:
        mcp.tool(fn, annotations=READ_ONLY)
    return [fn.__name__ for fn in tools]
