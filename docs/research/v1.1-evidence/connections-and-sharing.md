# Dossier — Connections & sharing (V-14)

Sources read in full: SRC-D1, SRC-D3, SRC-D4. Supporting: SRC03, SRC29.

## Connection lifecycle (CONFIRMED)

Request path (SRC-D4): practice admin login → `[Labs]` → EasyRx Connected Labs list →
`[Connect to this lab]` → lab dashboard shows pending request → lab **Approve or Deny** →
on approve, practice can submit. Alerts (email/pop-up) can be configured for requests.

Auto-connect path (SRC-D1): lab creates the practice account + `[Invite]` → practice activates,
chooses plan, enters payment → automatically connected to that lab. Lab-created practices skip
the request step.

Durability (SRC-D4): once approved, the practice can submit "permanently … unless they remove
your lab from their Connected Labs list." → **practice-side disconnect exists** (removing the lab
from the practice's own Connected Labs list).

**Update (post-review, SRC-D9 Jan-2024 release notes)**: "For Lab users, the option to disconnect
from an EasyRx Practice account is now found here" → **lab-side disconnect exists since Jan 2024**.
Direction confirmed both ways; what happens to in-flight Rxs remains undocumented.

## V-14 — what is NOT documented

| Question | Finding |
|---|---|
| Can the LAB revoke a connection? | CONFIRMED that a lab-side disconnect control exists (SRC-D9, Jan 2024); its effects are not described |
| Are new orders blocked after disconnect? | Not documented. Reasonable inference only — EasyRS policy applies (below) |
| Do already-submitted Rxs stay visible to the lab? | UNKNOWN |
| Do checked-in Rxs continue fulfillment? | UNKNOWN |
| Do file accesses change post-disconnect? | UNKNOWN |
| Who retains history? | Practice keeps its patient/Rx history (files also on patient record — CONFIRMED SRC01/SRC-D6); lab keeps its case history ("running history" for its practices — SRC-D2). Both-sides retention is consistent but not explicitly stated for post-disconnect views |

## EasyRS-owned safety policy (PROVISIONAL — not EasyRx fact)

EasyRS adopts the following rules and labels them as OUR design, not copied behavior:

1. Disconnect (either direction) blocks NEW submissions immediately — the connection check runs
   at submit time.
2. Rxs already `submitted`/`checked_in` remain readable by both orgs and continue to completion —
   severing in-flight work would lose clinical data both sides need.
3. Object access stays bound to the Rx, not the live connection: a lab that received an Rx keeps
   read access to that Rx and its referenced assets; it loses the ability to see NEW patients/Rxs.
4. History retention is symmetric: both orgs retain their own audit/event records.
5. Re-connecting restores the catalog/template visibility but does not resurrect deleted data.

Rationale: matches our consent boundary model (connection = submit grant) while avoiding data
loss; every point above is marked PROVISIONAL in the permission matrix.

## Share with Colleague (CONFIRMED SRC-D3)

- From edit/view Rx → email anyone (EasyRx account or not) a view link to that Rx.
- **Link limits: 72 hours (extended from 24h, SRC-D8 Sept-2023) AND max 5 opens — whichever hits
  first**; sender shown as Support@EasyRxOrtho.com; **multiple recipients allowed via
  comma-separated emails** (SRC-D8).
- Recipient sees the Rx + can download attached files; STL viewing requires own viewer/account.
- Permanent alternative: Download to PDF.
- 2016+: all connected labs can use it (outsourcing STL sharing).
- EasyRS mapping: our `access_grant` TTL model already covers this — add an open-count cap
  alongside expires_at (PROVISIONAL enhancement, documented).

## Message Center (CONFIRMED SRC-D5/SRC02)

Secure in-platform messaging between connected orgs; comments/notification history consolidate on
the Rx so "everyone is on the same page".
