# Dossier — Clinical notifications & approvals (V-08)

Sources read in full: SRC23, SRC-D7. Supporting: SRC02 (index), SRC34.

## Lab → practice: Send Notification (CONFIRMED SRC23)

Entry: Edit buttons on the Rx — **only Submitted and Checked-In prescriptions have Edit options**.
Envelope icon on the workspace; red when a notification exists.

Notify Regarding (multi-select):
- **General Treatment** — comments on parts/appliances/prescription info/dates.
- **Files** — scoped to a specific attached filename (STL, PDF, …).

Requested Action — three levels:

| Level | Portal record | Practice action | Email |
|---|---|---|---|
| Notify Only | Pending notification on dashboard + on the Rx | Acknowledge or comment back | Optional |
| Notify and Require Approval | Recorded both sides | Doctor or authorized signature required; may comment before signing | Optional |
| Notify by Email Only | NOT recorded in EasyRx, nothing shown in portal | none | Always |

Optional free email field for extra recipients (incl. non-EasyRx staff).

## Practice side (CONFIRMED SRC-D7)

- Notifications surface on the Rx dashboard (count per lab + date) and inside the Rx (history +
  comment thread).
- Acknowledge → green "Received"; unanswered = "Pending".
- Signature notifications = doctor authorization requests for major changes/due dates.
- Disagreement path: comment back via Add a Comment — there is no documented hard "reject"
  button; rejection is expressed by commenting (PARTIAL — no documented reject verb or status
  change on the Rx itself).
- Typical uses: 3D setup verification for aligners, due-date changes, missing model info,
  review of lab-made Rx changes.

## Lab tracking (CONFIRMED SRC23)

- Clinical Verification page under Messages: lists sent notifications, status, and whether the
  practice acted/commented — an approval ledger exists.
- Guidance: do NOT un-submit an Rx just to add a notification unless authorized; for checked-out
  cases call the practice — implies lab-side notification requires Rx to be in lab's hands.

## Alert notifications (account-level preferences)

- Two types of alert notifications can be configured: email and pop-up (SRC02 index; SRC-D4
  confirms alerts for connection requests). Alert detail matrix PARTIAL.
- 2025: commercial labs can get email/daily-report/pop-up when a **Production Location** is set on
  an Rx (CONFIRMED SRC34).

## V-08 conclusion for S1b

- A notification entity exists with: target (general | file-ref), severity (notify | approve |
  email-only), message, optional email recipients, status (pending → acknowledged/approved),
  comment thread, requester (lab) and responder (practice incl. signature capture).
- Whether approval/rejection changes Rx state (hold/auto-version) is UNKNOWN — EasyRS design:
  notification is a collaboration object that may *reference* an Rx version; it does not itself
  mutate `rx.status`. PROVISIONAL.
