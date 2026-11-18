# Spec: Share a conversation by link

Status: approved 2026-11-08 · Owner: you · Change log at the bottom

## Problem

People get a good answer from the assistant and want to show it to a colleague or a friend.
Today they take screenshots, which lose formatting, cannot be searched and leak more than
intended. They want to send a link that shows one conversation, read-only, and that they can
switch off again.

## Users and stories

- As an **owner**, I can create a link for one of my conversations and choose how long it
  works, so I control how long it is visible.
- As an **owner**, I can see my links and turn any of them off, so I can take back a mistake.
- As a **viewer** with the link (no account), I can read the conversation in my browser, so
  I do not have to sign up to see what my colleague sent me.
- As an **owner on my phone**, I can share the link through the phone's own share menu, so
  I can send it with the app I already use.

## Acceptance criteria

- AC-1: A signed-in owner can create a share link for one of their own conversations and choose its lifetime: 1 day, 7 days (the default), 30 days or never.
- AC-2: The full link is returned only once, when it is created. Afterwards the API shows only each link's state, dates and view count, never the link itself.
- AC-3: Anyone holding an active link can read the conversation's title and messages without signing in. The view is read-only.
- AC-4: Messages written after the link was created are never visible through it.
- AC-5: An owner can revoke a link, and it stops working at once.
- AC-6: An unknown, expired or revoked link gives exactly the same 404 response, so nobody can tell the three apart.
- AC-7: A user cannot create, list or revoke links for another user's conversation (the API answers 404).
- AC-8: Creating links is limited to 20 per user per day, and public reads are limited per client address (60 per minute).
- AC-9: Creating a link and revoking a link each write one audit event.
- AC-10: The public page and the public API response are not indexed by search engines and are not cached.
- AC-11: The web app has a Share dialog with a copy button. The mobile app opens the phone's native share sheet.
- AC-12: Deleting a conversation deletes its links.
- AC-13: The owner sees how many times each link was opened. (Added by change request CR-1, see the change log.)

## Non-goals

- Editing or commenting on a shared conversation.
- Passwords on links, or sharing with named people.
- Sharing a whole workspace, or sharing files and images attached to a conversation.
- Detailed analytics: a single view count is enough.

## Data

One new table, `SharedLink`: public id, the conversation, who created it, the SHA-256 hash
of the token (never the token itself), created_at, expires_at (empty means never),
revoked_at (empty means active), view_count. The public view shows the messages created at
or before the link's created_at.

## API

The contract is `contracts/openapi.json`. This spec describes behaviour; the contract
describes shape. If they disagree, fix the spec first, then the contract.

## Security and privacy

- The token has 256 bits of randomness, travels in the URL path, and only its hash is stored.
- The public endpoint returns role, content and timestamp for each message. It never returns
  the owner's name, email or id.
- Public responses carry `Cache-Control: no-store` and `X-Robots-Tag: noindex`; the page sends
  `Referrer-Policy: no-referrer` so the link is not leaked to other sites.
- The owner is told in the dialog that anyone with the link can read the conversation.
- Creating and revoking links are audited (Chapter 17).

## Open questions

- Should a link show messages added later? [resolved] No: it is a snapshot (AC-4).
- Should viewers see the model name? [resolved] No.
- Do we need a limit on active links per conversation? [resolved] No: the daily limit is enough.

## Change log

- 2026-11-08: first approved version (AC-1 to AC-12).
- 2026-11-08: CR-1 adds AC-13, the view count (additive change: no existing client breaks).
