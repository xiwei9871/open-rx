import { useEffect, useRef, useState } from "react";
import {
  checkInRx, completeRx, createNotification, createRxCommentEx, deliverRx,
  downloadRxBundle, getRx, getRxFulfillment,
  listCatalog, listRxAttachments, listRxComments, listRxTransitions,
  receiveRx, recordRxQc, replaceRxItems, shipRx, submitRx, unsubmitRx,
  updateRx,
  type CatalogItem, type Fulfillment, type Me, type Rx, type RxAttachment,
  type RxComment, type RxTransition,
} from "../api";
import {
  fmtDate, fmtDateTime, fulfillmentLabel, QC_LABELS, saveAs, statusLabel,
} from "../lib";
import StlPreview from "../components/StlPreview";

function requiredOptions(c: CatalogItem | undefined): string[] {
  return (c?.option_schema as { required?: string[] } | null)?.required ?? [];
}

export default function RxDetail({ me, rxId, onBack }: {
  me: Me; rxId: string; onBack: () => void;
}) {
  const isLab = me.org_kind === "lab";
  const [rx, setRx] = useState<Rx | null>(null);
  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [comments, setComments] = useState<RxComment[]>([]);
  const [trail, setTrail] = useState<RxTransition[]>([]);
  const [comment, setComment] = useState("");
  const [commentRef, setCommentRef] = useState("");
  const [attachments, setAttachments] = useState<RxAttachment[]>([]);
  const [previewId, setPreviewId] = useState<string | null>(null);
  const [issueKind, setIssueKind] = useState<"info" | "ack_required" | "approval_required">("info");
  const [issueSubject, setIssueSubject] = useState("");
  const [issueBody, setIssueBody] = useState("");
  const [ful, setFul] = useState<Fulfillment | null>(null);
  const [carrier, setCarrier] = useState("");
  const [tracking, setTracking] = useState("");
  const [editNotes, setEditNotes] = useState("");
  const [editDue, setEditDue] = useState("");
  const [sig, setSig] = useState("");
  const [pick, setPick] = useState("");
  const [arch, setArch] = useState("upper");
  const [optVals, setOptVals] = useState<Record<string, string>>({});
  const [err, setErr] = useState("");
  const [info, setInfo] = useState("");
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);

  async function reload() {
    const [r, cs, ts, at] = await Promise.all([
      getRx(rxId), listRxComments(rxId), listRxTransitions(rxId),
      listRxAttachments(rxId)]);
    setRx(r);
    setComments(cs);
    setTrail(ts);
    setAttachments(at);
    if (r.status === "completed" || r.fulfillment_status !== "none") {
      setFul(await getRxFulfillment(rxId));
    }
    setEditNotes(r.notes ?? "");
    setEditDue(r.due_date ?? "");
  }
  useEffect(() => {
    void reload().catch((e) => setErr(e instanceof Error ? e.message : String(e)));
    listCatalog("parts").then((p) =>
      listCatalog("appliances").then((a) => setCatalog([...p, ...a])))
      .catch(() => {});
  }, [rxId]);

  async function act(fn: () => Promise<unknown>, ok: string) {
    // Ref guard: a fast double-click can re-enter before the busy-disabled
    // re-render lands, and act() must be safe against that race.
    if (busyRef.current) return;
    busyRef.current = true;
    setErr(""); setInfo(""); setBusy(true);
    try {
      await fn();
      setInfo(ok);
      await reload();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }

  function itemName(id: string): string {
    const c = catalog.find((x) => x.id === id);
    return c ? `${c.code} — ${c.name}` : id.slice(0, 8);
  }

  if (!rx) return (
    <section>{err
      ? <p role="alert" className="alert">{err}</p>
      : <p className="empty">Loading…</p>}
    </section>);

  const editable = !isLab && rx.status === "draft";
  const picked = catalog.find((c) => c.id === pick);
  const pickedRequired = requiredOptions(picked);

  async function onSave() {
    await act(async () => {
      const updated = await updateRx(rx!.id, rx!.version, {
        notes: editNotes || null, due_date: editDue || null,
      });
      if (pick) {
        const missing = pickedRequired.filter((k) => !optVals[k]?.trim());
        if (missing.length) {
          throw new Error(`Required options missing: ${missing.join(", ")}`);
        }
        const options = pickedRequired.length
          ? Object.fromEntries(
              pickedRequired.map((k) => [k, optVals[k].trim()]))
          : undefined;
        await replaceRxItems(updated.id, updated.version, [
          ...(updated.items ?? []).map((i) => ({
            appliance_id: i.appliance_id, arch: i.arch,
            options: i.options ?? undefined,
          })),
          { appliance_id: pick, arch, options },
        ]);
        setPick("");
        setOptVals({});
      }
    }, "Saved");
  }

  return (
    <section>
      <div className="page-head">
        <h2>{rx.rx_number} — {statusLabel(rx.status)}
          {rx.checked_in_via === "download" &&
            <small className="muted"> (via download)</small>}
        </h2>
        <div className="row">
          <span className={`pill st-${rx.status}`}>{statusLabel(rx.status)}</span>
          {rx.fulfillment_status !== "none" && (
            <span className={`pill st-${rx.fulfillment_status}`}>
              {fulfillmentLabel(rx.fulfillment_status)}
            </span>
          )}
          <button type="button" onClick={onBack}>Back</button>
        </div>
      </div>
      {err && <p role="alert" className="alert">{err}</p>}
      {info && <p role="status" className="notice">{info}</p>}

      <div className="card">
        <h3>Summary</h3>
        <table className="kv"><tbody>
          <tr><td>Patient</td><td>{rx.patient_label ?? "—"}</td></tr>
          <tr><td>{isLab ? "Practice" : "Lab"}</td>
            <td>{isLab
              ? (rx.practice_name ?? "—")
              : (rx.lab_name ?? "— (not assigned)")}</td></tr>
          <tr><td>Doctor</td><td>{rx.doctor_name ?? "—"}</td></tr>
          <tr><td>Location</td><td>{rx.location_name ?? "—"}</td></tr>
          <tr><td>Due</td><td>{fmtDate(rx.due_date)}</td></tr>
          <tr><td>Submitted</td><td>{fmtDateTime(rx.submitted_at)}</td></tr>
          <tr><td>Checked in</td><td>{fmtDateTime(rx.checked_in_at)}</td></tr>
          <tr><td>Signature</td><td>{rx.signature_name ?? "—"}
            {rx.signed_rx_version != null &&
              <small className="muted"> (v{rx.signed_rx_version})</small>}
          </td></tr>
          <tr><td>Notes</td><td>{rx.notes ?? "—"}</td></tr>
        </tbody></table>
      </div>

      {editable && (
        <div className="card">
          <h3>Edit draft</h3>
          <div className="grid2">
            <label className="field"><span>Due date</span>
              <input type="date" value={editDue}
                     onChange={(e) => setEditDue(e.target.value)} />
            </label>
            <label className="field"><span>Notes</span>
              <textarea rows={2} value={editNotes}
                        onChange={(e) => setEditNotes(e.target.value)} />
            </label>
          </div>
          <div className="row">
            <label className="field grow" style={{ marginBottom: 0 }}>
              <span>Add item</span>
              <select value={pick}
                      onChange={(e) => { setPick(e.target.value);
                                         setOptVals({}); }}>
                <option value="">— add item —</option>
                {catalog.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.code} — {c.name}
                  </option>))}
              </select>
            </label>
            <label className="field" style={{ marginBottom: 0 }}>
              <span>Arch</span>
              <select value={arch} onChange={(e) => setArch(e.target.value)}>
                <option value="upper">Upper</option>
                <option value="lower">Lower</option>
                <option value="both">Both</option>
              </select>
            </label>
            {pickedRequired.map((k) => (
              <label className="field" key={k} style={{ marginBottom: 0 }}>
                <span>{k} (required)</span>
                <input aria-label={`Option ${k}`} value={optVals[k] ?? ""}
                  onChange={(e) =>
                    setOptVals({ ...optVals, [k]: e.target.value })} />
              </label>
            ))}
          </div>
        </div>
      )}

      <div className="card">
        <h3>Items</h3>
        <ul>
          {(rx.items ?? []).map((i) => (
            <li key={i.id}>{itemName(i.appliance_id)} ({i.arch})
              {i.options &&
                ` — ${Object.entries(i.options)
                    .map(([k, v]) => `${k}=${v}`).join(", ")}`}
              {i.tooth_ops.length > 0 &&
                ` — ${i.tooth_ops.map((t) => `${t.op} ${t.tooth}`).join(", ")}`}
            </li>
          ))}
          {(rx.items ?? []).length === 0 &&
            <li className="empty">None</li>}
        </ul>
        <div className="row" style={{ marginTop: "0.6rem" }}>
          {editable && <>
            <button type="button" onClick={onSave} disabled={busy}>Save</button>
            <label className="field" style={{ marginBottom: 0 }}>
              <span>Signature</span>
              <input name="signature" value={sig}
                     onChange={(e) => setSig(e.target.value)}
                     placeholder="Type full name to sign" />
            </label>
            <button type="button" className="primary" disabled={busy}
              onClick={() => act(
                () => submitRx(rx.id, rx.version, sig || me.display_name),
                "Submitted to lab")}>Sign &amp; Submit</button>
          </>}
          {!isLab && (rx.status === "submitted" || rx.status === "checked_in") && (
            <button type="button" disabled={busy} onClick={() => act(
              () => unsubmitRx(rx.id, rx.version,
                               "pulled back by practice").then(() => undefined),
              "Returned to draft")}>Unsubmit</button>
          )}
          {isLab && rx.status === "submitted" && (
            <button type="button" className="primary" disabled={busy}
              onClick={() => act(
                () => checkInRx(rx.id, rx.version, "received at bench"),
                "Checked in")}>Check in</button>
          )}
          {isLab && rx.status === "checked_in" && (
            <button type="button" className="primary" disabled={busy}
              onClick={() => act(
                () => completeRx(rx.id, rx.version, "production complete"),
                "Completed")}>Mark complete</button>
          )}
          {rx.status !== "draft" && (
            <button type="button" disabled={busy} onClick={() => act(async () => {
              const b = await downloadRxBundle(rx.id);
              await saveAs(b.download_url, `${rx.rx_number}.zip`);
            }, "Bundle downloaded")}>
              {isLab && rx.status === "submitted"
                ? "Download & Check-in" : "Download bundle"}
            </button>
          )}
        </div>
      </div>

      <div className="card">
        <h3>Attachments</h3>
        {attachments.length === 0
          ? <p className="empty">No attachments.</p>
          : (
            <ul>{attachments.map((a) => (
              <li key={a.id}>
                {a.asset.kind}/{a.asset.jaw} — {a.role} —{" "}
                {a.asset.bytes} bytes — sha256 {a.asset.sha256.slice(0, 12)}…
                {a.asset.kind === "stl" && (
                  <>{" "}<button type="button" className="small"
                    aria-label={`preview ${a.id}`}
                    onClick={() => setPreviewId(
                      previewId === a.asset_id ? null : a.asset_id)}>
                    {previewId === a.asset_id ? "Hide preview" : "Preview"}
                  </button></>
                )}
                {previewId === a.asset_id &&
                  <StlPreview assetId={a.asset_id} />}
              </li>
            ))}</ul>
          )}
      </div>

      {(rx.status === "completed" || rx.fulfillment_status !== "none") && (
        <div className="card">
          <h3>Fulfillment</h3>
          <table className="kv"><tbody>
            <tr><td>Logistics</td><td data-testid="fulfillment-status">
              {rx.fulfillment_status}</td></tr>
            <tr><td>QC</td><td>{QC_LABELS[rx.qc_status] ?? rx.qc_status}</td></tr>
            <tr><td>Carrier</td><td>{rx.carrier ?? "—"}</td></tr>
            <tr><td>Tracking</td><td>{rx.tracking_number ?? "—"}</td></tr>
            <tr><td>Shipped</td><td>{fmtDateTime(rx.shipped_at)}</td></tr>
            <tr><td>Received</td><td>{fmtDateTime(rx.received_at)}</td></tr>
            <tr><td>Delivered</td><td>{fmtDateTime(rx.delivered_at)}</td></tr>
          </tbody></table>
          <div className="row" style={{ marginTop: "0.5rem" }}>
            {isLab && (rx.fulfillment_status === "qc_pending" ||
                       rx.fulfillment_status === "qc_passed") && (
              <>
                <button type="button" disabled={busy} onClick={() => act(
                  () => recordRxQc(rx.id, rx.version, "pass", "manual QC"),
                  "QC passed recorded")}>QC pass</button>
                <button type="button" disabled={busy} onClick={() => act(
                  () => recordRxQc(rx.id, rx.version, "fail", "manual QC"),
                  "QC fail recorded")}>QC fail</button>
              </>
            )}
            {isLab && rx.fulfillment_status === "qc_passed" && (
              <>
                <input aria-label="Carrier" placeholder="carrier"
                       value={carrier}
                       onChange={(e) => setCarrier(e.target.value)} />
                <input aria-label="Tracking number" placeholder="tracking #"
                       value={tracking}
                       onChange={(e) => setTracking(e.target.value)} />
                <button type="button" className="primary"
                  disabled={!carrier || !tracking || busy}
                  onClick={() => act(
                    () => shipRx(rx.id, rx.version, carrier, tracking),
                    "Shipped")}>Ship</button>
              </>
            )}
            {!isLab && rx.fulfillment_status === "shipped" && (
              <button type="button" className="primary" disabled={busy}
                onClick={() => act(() => receiveRx(rx.id, rx.version),
                  "Received")}>Confirm receipt</button>
            )}
            {!isLab && rx.fulfillment_status === "received" && (
              <button type="button" className="primary" disabled={busy}
                onClick={() => act(() => deliverRx(rx.id, rx.version),
                  "Delivered")}>Confirm delivery</button>
            )}
          </div>
          {ful && ful.events.length > 0 && (
            <ul data-testid="fulfillment-events">
              {ful.events.map((e) => (
                <li key={e.id}>{e.event}
                  {e.note && ` — ${e.note}`}
                  <small className="muted"> {fmtDateTime(e.created_at)}</small>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="card">
        <h3>Raise issue / request</h3>
        <div className="row">
          <select aria-label="Issue kind" value={issueKind}
                  onChange={(e) =>
                    setIssueKind(e.target.value as typeof issueKind)}>
            <option value="info">info</option>
            <option value="ack_required">ack required</option>
            <option value="approval_required">approval required</option>
          </select>
          <input aria-label="Issue subject" placeholder="subject"
                 value={issueSubject}
                 onChange={(e) => setIssueSubject(e.target.value)} />
          <input aria-label="Issue body" placeholder="details (optional)"
                 className="grow" value={issueBody}
                 onChange={(e) => setIssueBody(e.target.value)} />
          <button type="button" disabled={!issueSubject || busy}
            onClick={() => act(async () => {
              await createNotification({ rx_id: rx.id, kind: issueKind,
                                         subject: issueSubject,
                                         body: issueBody || undefined });
              setIssueSubject(""); setIssueBody("");
            }, "Sent to counterparty inbox")}>Send</button>
        </div>
      </div>

      <div className="card">
        <h3>Comments</h3>
        <ul>
          {comments.map((c) => (
            <li key={c.id}>
              {c.body}
              {c.file_reference_id && (
                <small className="muted">
                  {" "}[attachment {c.file_reference_id.slice(0, 8)}…]</small>
              )}
              {" "}<small className="muted">({fmtDateTime(c.created_at)})</small>
            </li>
          ))}
          {comments.length === 0 && <li className="empty">None</li>}
        </ul>
        <div className="row">
          <input name="comment" className="grow" value={comment}
                 placeholder="Add comment"
                 onChange={(e) => setComment(e.target.value)} />
          {attachments.length > 0 && (
            <select aria-label="Anchor attachment" value={commentRef}
                    onChange={(e) => setCommentRef(e.target.value)}>
              <option value="">no attachment</option>
              {attachments.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.asset.kind}/{a.asset.jaw} {a.asset.sha256.slice(0, 8)}…
                </option>
              ))}
            </select>
          )}
          <button type="button" disabled={!comment.trim() || busy}
            onClick={() => act(async () => {
              await createRxCommentEx(rx.id, comment, commentRef || undefined);
              setComment(""); setCommentRef("");
            }, "Comment added")}>Post</button>
        </div>
      </div>

      <div className="card">
        <h3>History</h3>
        <ul>
          {trail.map((t) => (
            <li key={t.id}>{t.from_status ?? "∅"} → {t.to_status}
              {t.via !== "button" && ` (${t.via})`}
              {t.note && ` — ${t.note}`}
              <small className="muted"> {fmtDateTime(t.created_at)}</small>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
