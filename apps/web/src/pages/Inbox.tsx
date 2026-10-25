import { useCallback, useEffect, useState } from "react";
import {
  decideNotification, listNotifications, markNotificationRead,
  type Me, type Notification,
} from "../api";

import { fmtDateTime, useActionLock } from "../lib";

function kindLabel(kind: string): string {
  return { comment: "Comment", approval_required: "Approval required",
           mention: "Mention" }[kind] ?? kind.replace(/_/g, " ");
}

/** COM-007 message center + COM-004 approval decisions (E2E-09). */
export default function Inbox({ me, onOpenRx }: {
  me: Me; onOpenRx: (rxId: string) => void;
}) {
  const [items, setItems] = useState<Notification[]>([]);
  const [counts, setCounts] = useState({ unread: 0, approval_pending: 0 });
  const [kind, setKind] = useState("");
  const [status, setStatus] = useState("");
  const [err, setErr] = useState("");
  const [sig, setSig] = useState<Record<string, string>>({});
  const lock = useActionLock();
  const canWrite = me.permissions.includes("rx:write");

  const reload = useCallback(async () => {
    try {
      const r = await listNotifications(kind || undefined,
                                        status || undefined);
      setItems(r.items); setCounts(r.counts);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }, [kind, status]);

  useEffect(() => { void reload(); }, [reload]);

  return (
    <section>
      <div className="page-head"><h2>Inbox</h2></div>
      <div className="stats">
        <div className="stat"><div className="n" data-testid="unread-count">
          {counts.unread}</div><div className="l">Unread</div></div>
        <div className="stat"><div className="n">{counts.approval_pending}</div>
          <div className="l">Pending approvals</div></div>
      </div>
      <div className="toolbar">
        <label>Kind{" "}
        <select aria-label="Kind" value={kind}
                onChange={(e) => setKind(e.target.value)}>
          <option value="">all kinds</option>
          <option value="info">info</option>
          <option value="ack_required">ack required</option>
          <option value="approval_required">approval required</option>
        </select></label>
        <label>Status{" "}
        <select aria-label="Status" value={status}
                onChange={(e) => setStatus(e.target.value)}>
          <option value="">all status</option>
          <option value="unread">unread</option>
          <option value="read">read</option>
          <option value="resolved">resolved</option>
        </select></label>
      </div>
      {err && <p role="alert" className="alert">{err}</p>}
      {items.length === 0 ? <p className="empty">No messages.</p> : items.map((n) => (
        <div key={n.id} data-testid="notification"
             className={`msg-card${n.status === "unread" ? " unread" : ""}`}>
          <p>
            <strong>{n.subject}</strong>{" "}
            <small className="muted">
              {kindLabel(n.kind)}{n.status !== "read" ? ` · ${n.status}` : ""}
              {" "}{fmtDateTime(n.created_at)}</small>
          </p>
          {n.body && <p>{n.body}</p>}
          <p className="row">
            <a href={`/rx/${n.rx_id}`}
               onClick={(e) => { e.preventDefault(); onOpenRx(n.rx_id); }}>
              Open Rx
            </a>
            {n.status === "unread" && (
              <button className="small" onClick={() => lock(async () => {
                await markNotificationRead(n.id); await reload();
              })}>mark read</button>
            )}
          </p>
          {n.kind === "approval_required" && n.status !== "resolved" && canWrite && (
            <div style={{ borderTop: "1px dashed var(--line)", paddingTop: 8 }}>
              <label className="field" style={{ maxWidth: 260 }}>
                <span>Signature (typed name)</span>
                <input aria-label={`signature ${n.id}`}
                  value={sig[n.id] ?? ""}
                  onChange={(e) => setSig({ ...sig, [n.id]: e.target.value })} />
              </label>
              <button className="primary" onClick={() => lock(async () => {
                try {
                  await decideNotification(n.id, {
                    decision: "approved",
                    signature_name: sig[n.id] ?? "" });
                  await reload();
                } catch (e) {
                  setErr(e instanceof Error ? e.message : String(e));
                }
              })}>Approve</button>{" "}
              <button onClick={() => lock(async () => {
                try {
                  await decideNotification(n.id, {
                    decision: "rejected",
                    signature_name: sig[n.id] ?? "" });
                  await reload();
                } catch (e) {
                  setErr(e instanceof Error ? e.message : String(e));
                }
              })}>Reject</button>
            </div>
          )}
        </div>
      ))}
    </section>
  );
}
