import { useEffect, useState } from "react";
import {
  checkInRx, completeRx, createNotification, createRxCommentEx,
  downloadRxBundle, getRx,
  listCatalog, listRxAttachments, listRxComments, listRxTransitions,
  replaceRxItems, submitRx, unsubmitRx, updateRx,
  type CatalogItem, type Me, type Rx, type RxAttachment, type RxComment,
  type RxTransition,
} from "../api";
import StlPreview from "../components/StlPreview";

const input = { display: "block", width: "100%", marginBottom: 8, padding: 4 } as const;

const STATUS_LABELS: Record<string, string> = {
  draft: "Saved", submitted: "Submitted", checked_in: "Checked-In",
  in_progress: "In Progress", on_hold: "On Hold", completed: "Completed",
  reopened: "Reopened", cancelled: "Cancelled",
};

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
  const [editNotes, setEditNotes] = useState("");
  const [editDue, setEditDue] = useState("");
  const [sig, setSig] = useState("");
  const [pick, setPick] = useState("");
  const [arch, setArch] = useState("upper");
  const [err, setErr] = useState("");
  const [info, setInfo] = useState("");

  async function reload() {
    const [r, cs, ts, at] = await Promise.all([
      getRx(rxId), listRxComments(rxId), listRxTransitions(rxId),
      listRxAttachments(rxId)]);
    setRx(r);
    setComments(cs);
    setTrail(ts);
    setAttachments(at);
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
    setErr(""); setInfo("");
    try {
      await fn();
      setInfo(ok);
      await reload();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }

  function itemName(id: string): string {
    const c = catalog.find((x) => x.id === id);
    return c ? `${c.code} — ${c.name}` : id.slice(0, 8);
  }

  if (!rx) return <section>{err ? <p role="alert" style={{ color: "crimson" }}>{err}</p> : <p>Loading…</p>}</section>;

  const editable = !isLab && rx.status === "draft";

  async function onSave() {
    await act(async () => {
      const updated = await updateRx(rx!.id, rx!.version, {
        notes: editNotes || null, due_date: editDue || null,
      });
      if (pick) {
        const required: string[] =
          (catalog.find((c) => c.id === pick)?.option_schema as { required?: string[] } | null)
            ?.required ?? [];
        const options = required.length
          ? Object.fromEntries(required.map((k) => [k, window.prompt(`${k} (required)`) ?? ""]))
          : undefined;
        await replaceRxItems(updated.id, updated.version, [
          ...(updated.items ?? []).map((i) => ({
            appliance_id: i.appliance_id, arch: i.arch,
            options: i.options ?? undefined,
          })),
          { appliance_id: pick, arch, options },
        ]);
        setPick("");
      }
    }, "Saved");
  }

  return (
    <section>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <h2>{rx.rx_number} — {STATUS_LABELS[rx.status] ?? rx.status}
          {rx.checked_in_via === "download" && <small> (via download)</small>}
        </h2>
        <button onClick={onBack}>Back</button>
      </header>
      {err && <p role="alert" style={{ color: "crimson" }}>{err}</p>}
      {info && <p role="status" style={{ color: "seagreen" }}>{info}</p>}

      <table><tbody>
        <tr><td>Patient</td><td>{rx.patient_id.slice(0, 8)}…</td></tr>
        <tr><td>Lab</td><td>{rx.lab_org_id ? rx.lab_org_id.slice(0, 8) + "…" : "—"}</td></tr>
        <tr><td>Submitted</td><td>{rx.submitted_at?.slice(0, 19) ?? "—"}</td></tr>
        <tr><td>Checked in</td><td>{rx.checked_in_at?.slice(0, 19) ?? "—"}</td></tr>
        <tr><td>Signature</td><td>{rx.signature_name ?? "—"}</td></tr>
      </tbody></table>

      {editable ? (
        <>
          <label>Due date
            <input type="date" value={editDue}
                   onChange={(e) => setEditDue(e.target.value)} style={input} />
          </label>
          <label>Notes
            <textarea value={editNotes}
                      onChange={(e) => setEditNotes(e.target.value)} style={input} />
          </label>
          <div style={{ display: "flex", gap: 8 }}>
            <select value={pick} onChange={(e) => setPick(e.target.value)}>
              <option value="">— add item —</option>
              {catalog.map((c) => (
                <option key={c.id} value={c.id}>{c.code} — {c.name}</option>))}
            </select>
            <select value={arch} onChange={(e) => setArch(e.target.value)}>
              <option value="upper">Upper</option>
              <option value="lower">Lower</option>
              <option value="both">Both</option>
            </select>
          </div>
        </>
      ) : (
        <>
          <p><strong>Due:</strong> {rx.due_date ?? "—"}</p>
          <p><strong>Notes:</strong> {rx.notes ?? "—"}</p>
        </>
      )}

      <h3>Items</h3>
      <ul>
        {(rx.items ?? []).map((i) => (
          <li key={i.id}>{itemName(i.appliance_id)} ({i.arch})
            {i.options && ` — ${Object.entries(i.options).map(([k, v]) => `${k}=${v}`).join(", ")}`}
            {i.tooth_ops.length > 0 &&
              ` — ${i.tooth_ops.map((t) => `${t.op} ${t.tooth}`).join(", ")}`}
          </li>
        ))}
        {(rx.items ?? []).length === 0 && <li><em>None</em></li>}
      </ul>

      <div style={{ display: "flex", gap: 8, margin: "1rem 0" }}>
        {editable && <>
          <button onClick={onSave}>Save</button>
          <label>Signature
            <input name="signature" value={sig}
                   onChange={(e) => setSig(e.target.value)}
                   placeholder="Type full name to sign" />
          </label>
          <button onClick={() => act(
            () => submitRx(rx.id, rx.version, sig || me.display_name),
            "Submitted to lab")}>Sign &amp; Submit</button>
        </>}
        {!isLab && (rx.status === "submitted" || rx.status === "checked_in") && (
          <button onClick={() => act(
            () => unsubmitRx(rx.id, rx.version,
                             "pulled back by practice").then(() => undefined),
            "Returned to draft")}>Unsubmit</button>
        )}
        {isLab && rx.status === "submitted" && (
          <button onClick={() => act(
            () => checkInRx(rx.id, rx.version, "received at bench"),
            "Checked in")}>Check in</button>
        )}
        {isLab && rx.status === "checked_in" && (
          <button onClick={() => act(
            () => completeRx(rx.id, rx.version, "production complete"),
            "Completed")}>Mark complete</button>
        )}
        {rx.status !== "draft" && (
          <button onClick={() => act(async () => {
            const b = await downloadRxBundle(rx.id);
            window.open(b.download_url, "_blank", "noopener");
          }, "Bundle ready — download started")}>
            {isLab && rx.status === "submitted"
              ? "Download & Check-in" : "Download bundle"}
          </button>
        )}
      </div>

      <h3>Attachments</h3>
      {attachments.length === 0 ? <p>No attachments.</p> : (
        <ul>{attachments.map((a) => (
          <li key={a.id}>
            {a.asset.kind}/{a.asset.jaw} — {a.role} — {a.asset.bytes} bytes —
            sha256 {a.asset.sha256.slice(0, 12)}…
            {a.asset.kind === "stl" && (
              <>{" "}<button type="button" aria-label={`preview ${a.id}`}
                onClick={() => setPreviewId(
                  previewId === a.asset_id ? null : a.asset_id)}>Preview</button></>
            )}
            {previewId === a.asset_id && <StlPreview assetId={a.asset_id} />}
          </li>
        ))}</ul>
      )}

      <h3>Raise issue / request</h3>
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        <select aria-label="Issue kind" value={issueKind}
                onChange={(e) => setIssueKind(e.target.value as typeof issueKind)}>
          <option value="info">info</option>
          <option value="ack_required">ack required</option>
          <option value="approval_required">approval required</option>
        </select>
        <input aria-label="Issue subject" placeholder="subject"
               value={issueSubject}
               onChange={(e) => setIssueSubject(e.target.value)} />
        <input aria-label="Issue body" placeholder="details (optional)"
               value={issueBody}
               onChange={(e) => setIssueBody(e.target.value)} />
        <button disabled={!issueSubject} onClick={() => act(async () => {
          await createNotification({ rx_id: rx.id, kind: issueKind,
                                     subject: issueSubject,
                                     body: issueBody || undefined });
          setIssueSubject(""); setIssueBody("");
        }, "Sent to counterparty inbox")}>Send</button>
      </div>

      <h3>Comments</h3>
      <ul>
        {comments.map((c) => (
          <li key={c.id}>
            {c.body}
            {c.file_reference_id && (
              <small> [attachment {c.file_reference_id.slice(0, 8)}…]</small>
            )}
            {" "}<small>({c.created_at.slice(0, 16)})</small>
          </li>
        ))}
        {comments.length === 0 && <li><em>None</em></li>}
      </ul>
      <div style={{ display: "flex", gap: 8 }}>
        <input name="comment" value={comment} placeholder="Add comment"
               onChange={(e) => setComment(e.target.value)} style={{ flex: 1 }} />
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
        <button onClick={() => act(async () => {
          await createRxCommentEx(rx.id, comment, commentRef || undefined);
          setComment(""); setCommentRef("");
        }, "Comment added")}>Post</button>
      </div>

      <h3>History</h3>
      <ul>
        {trail.map((t) => (
          <li key={t.id}>{t.from_status ?? "∅"} → {t.to_status}
            {t.via !== "button" && ` (${t.via})`}
            {t.note && ` — ${t.note}`}
            <small> {t.created_at.slice(0, 19)}</small></li>
        ))}
      </ul>
    </section>
  );
}
