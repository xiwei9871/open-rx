# EasyRS Preview — User Guide

**Who this is for:** invited evaluators at Canadian dental practices and
orthodontic laboratories. No prior EasyRS experience needed — follow the
workflows top to bottom.

**Where:** `https://easyrx.manqiaotechnology.com`
**Accounts:** you received one practice account and one lab account by
invitation email. There is no public sign-up.

> **Demo Environment — Synthetic Data Only.** Every patient, scan, and
> order in this environment is synthetic. Do **not** upload real patient
> records, identifiable scans, or clinical data — the upload form will
> remind you each time.

---

## 0. At a glance — what the platform does

EasyRS runs the complete digital prescription workflow between a dental
practice and its lab:

```
Practice                          Lab
────────                          ───
Patient chart
  → Treatment Case
    → Digital Scans (STL)
      → Prescription (Rx) ──────→ Inbox
        sign & submit              → Download & Check-in
                                     → In Progress
                                     → Quality Check
                                     → Ship  ──────────→ Receive
                                                         → Delivered
```

Every step is recorded in an audit trail both sides can see. Files travel
as signed, expiring links — neither side emails STL files around.

**Roles in this demo**

| Account | Sees | Can do |
|---|---|---|
| `preview.doctor@demo.easyrs` | Practice nav: Patients, Prescriptions, Inbox, Settings | patients, cases, scans, Rx draft/sign/submit, comments, receive, deliver |
| `preview.lab@demo.easyrs` | Lab nav: Inbox, Prescriptions, Settings | download bundle, check in, complete, QC, ship, comment |

Your two accounts belong to **separate demo organizations** — the practice
`Harbourview Orthodontics (demo)` and the lab `Coastal Ortho Lab (demo)`.
They can only see orders shared between them; nothing else in the system
is visible to either account.

**Conventions used in the UI**

- **Upper arch / Lower arch** — which jaw a scan or appliance targets.
- **FDI tooth numbers** — e.g. tooth 14 is upper-right first premolar.
- **Dates** render as `Oct 25, 2026`; times follow your organization
  timezone (Settings).
- **Statuses are plain English**: Saved → Submitted → Checked-In →
  In Progress → Completed → QC → Shipped → Received → Delivered.
- The amber **Demo Environment** banner and the version tag stay on
  screen after sign-in — that is intentional.

---

## 1. Sign in and pick your starting point

1. Open `https://easyrx.manqiaotechnology.com`.
2. The welcome card offers three real entry points — they are not
   decorative; each one remembers where you wanted to go:

   | Button | After sign-in you land on |
   |---|---|
   | **Try the Practice Workflow** | Patients (start §2) |
   | **Explore the Lab Workflow** | Prescriptions inbox (start §3) |
   | **View a Sample Prescription** | Prescriptions list — open the order marked Completed/Delivered (§4) |

3. Enter the invited email + password → **Sign in**.
4. To switch roles, use **Sign out** (top-right) and sign in with the
   other account. Deep links survive sign-out/sign-in, and you can
   refresh on any page without losing your place.

---

## 2. Workflow A — Practice side: patient → case → scan → prescription

### 2.1 Create a patient

1. **Patients** → **New patient**.
2. Fill **First name**, **Last name**, **Date of birth**; **External ref**
   is your own chart number (optional).
3. **Create patient** → you land on the patient chart. If the
   name+birthday matches an existing patient you get a confirmation
   prompt instead of a silent duplicate.
4. **Search** on the Patients list filters by name or ref — useful once
   the list grows.

The chart shows: demographics, **Treatment Cases**, **Digital Scans**, and
existing prescriptions for this patient.

### 2.2 Open a treatment case

1. On the patient chart → **New case label** (e.g. `Hawley retainer — upper`) →
   **Add case**.
2. Add **Notes** — clinical context the lab should see. **Save**.

A case is the clinical folder: scans and prescriptions attach to it, so
one patient can hold several independent cases.

### 2.3 Upload digital scans (STL)

1. On the patient chart, in **Digital Scans**: choose **STL file**, pick
   the **Jaw** (`upper`/`lower`), then **Upload STL**.
2. Watch the notice: *"Do not upload real patient records, identifiable
   scans, or clinical data."* — synthetic STL files only.
3. After upload the row shows the file size, **SHA-256** fingerprint and
   `valid mesh` when the file parses. Files upload via a signed URL
   straight to object storage — the progress bar is the real transfer,
   and a 200 MB+ file is rejected with a readable message.
4. Per file: **Preview** opens the 3D viewer (drag to orbit, scroll to
   zoom — verify the mesh actually loads), **Download** gets the original
   bytes back, **Hide** removes it from the case view without deleting.

Upload **both** an upper and a lower STL — the lab bundle and the Rx will
reference them.

### 2.4 Write the prescription

1. From the patient chart (or **Prescriptions → New Rx**): pick the
   **patient** (type to filter), then the **treatment case** — the Rx is
   bound to the case so the lab sees its scans.
2. Pick a **Template** if your org saved one, or build items manually.
3. **Add item**: choose a catalog entry (e.g. `Hawley retainer`), the
   **arch** it applies to, and any required options — tooth-numbered
   options like `band_tooth` ask for an FDI number. Repeat for each
   appliance. Remove a line with **remove**.
4. Set the **Due date**, then **Save draft** — the Rx now exists as
   `Saved`, editable and visible only inside your practice.
5. Optional: **Template name** + save to reuse this item set later.

### 2.5 Sign and submit

1. Open the saved Rx. Review items, case, due date; attach anything else
   under **Attachments** (**Patient file** or pick an existing case scan
   and an **Attachment role**).
2. **Type full name to sign** — this is the clinical signature gate; the
   button stays disabled until the name matches.
3. **Sign & submit** → status `Submitted`. The Rx leaves "draft" and
   appears in the lab's inbox; edits are locked.
4. Made a mistake? Before the lab checks it in, **Return to draft**
   pulls it back to `Saved`. After check-in the order is owned by the
   lab's queue and unsubmit is refused — call them via a comment instead.

The detail page keeps a live **history** line — `Saved → Submitted` and
who did it — so both sides see the same truth.

---

## 3. Workflow B — Lab side: inbox → check-in → QC → ship

Sign in as `preview.lab@demo.easyrs`. The lab lands on Prescriptions —
submitted orders are the work queue.

### 3.1 Accept the order (Download & Check-in)

1. Open the `Submitted` Rx.
2. **Download bundle** grabs the ZIP the practice sent: the Rx PDF,
   a manifest, and every attached STL. Check the contents — the manifest
   lists what should be inside.
3. **Download & Check-in** does both in one step and moves the order to
   `Checked-In` — this is the lab's formal acceptance. The practice sees
   `Submitted → Checked-In` in its history immediately.
4. If the files are wrong (missing arch, corrupted mesh), reject the work
   *now* with a comment instead of checking in.

### 3.2 Produce and complete

1. Work the case (outside the system in this demo).
2. **Mark complete** → `Completed`. That means production finished;
   quality review happens next, before anything ships.

### 3.3 Quality Check

Two outcomes, both recorded:

- **QC pass** → recorded in history, order becomes shippable.
- **QC fail** → requires an **Issue kind/subject/body** — e.g. *fit /
  clasp fracture / re-scan needed*. A fail sends the order back; a fix
  later re-runs the cycle.

### 3.4 Ship

1. **Carrier** + **Tracking number** (required pair) → **Ship**.
2. Status `Shipped`; the tracking data shows on the practice side — the
   same row, no email needed.

### 3.5 Comments & approvals (both directions, any time)

- **Add comment** on the Rx thread — visible to both orgs, each entry is
  attributed and timestamped.
- **Sent to counterparty inbox** / **Approval required** messages raise a
  notification on the other side's **Inbox** — filterable by kind
  (Approval required / Comment / Mention) and read state. The nav badge
  counts unread.

---

## 4. Workflow C — Practice fulfillment: receive → deliver → audit

Back on the practice account:

1. Open the shipped Rx → **Confirm receipt** → `Received` (the lab sees
   it instantly — no "did it arrive?" phone call).
2. Fit the appliance to the patient → **Mark delivered** → `Delivered`.
   The lifecycle is closed.
3. Scroll the **History** — every hop is there: created, submitted,
   checked-in, completed, QC, shipped, received, delivered, with actor
   and timestamp. This is the audit trail used for disputes and records.
4. **View a Sample Prescription** shortcut takes you straight to a
   seeded order that already completed this loop — fastest way to see a
   full history without doing the whole dance.

---

## 5. Everything else on the nav bar

| Area | What it does |
|---|---|
| **Patients** | List/search/create charts; duplicate-name guard |
| **Prescriptions** | All Rx for your org — drafts, in-flight, history; the lab's view is its work queue |
| **Inbox** | Cross-org notifications: approvals requested, comments, mentions; kind + read filters, unread badge in nav |
| **Settings** | **Timezone** (dates everywhere follow it), default doctor/location, **locations** (add/list), **roster** (staff entries), **lab connections** (send/accept/reject/withdraw a practice↔lab link — orders only flow between connected orgs), **change password** |
| **Sign out** | Ends the session; deep links still work after re-login |

---

## 6. What is enforced for you (no configuration needed)

- **Tenant isolation** — the two demo orgs cannot see each other's
  patients, only the orders they share.
- **Signed files** — uploads/downloads use expiring SigV4 URLs against
  object storage, not emailed attachments.
- **Integrity** — every stored file carries a SHA-256; a truncated or
  corrupt STL is marked, not silently accepted.
- **Audit** — every state change is attributed and immutable.
- **Safety rails** — oversize files rejected with readable errors,
  double-submits are idempotent, destructive states are gated
  (sign to submit, check-in to lock, receipt to close).
- **Privacy posture** — `noindex` everywhere, secure cookies, synthetic
  data only, and demo data can be reset between evaluation rounds.

## 7. Feedback

Use the in-product thread or reply to your invitation — tell us which
step felt wrong, not just what broke. Do not include real patient
information in feedback.
