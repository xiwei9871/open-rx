import { useCallback, useEffect, useState } from "react";
import {
  decideNotification, listNotifications, markNotificationRead,
  type Me, type Notification,
} from "../api";

const box = { border: "1px solid #ddd", borderRadius: 6, padding: 12,
              marginBottom: 10 } as const;

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
      <h2>Inbox</h2>
      <p>
        Unread: <strong data-testid="unread-count">{counts.unread}</strong> ·
        Pending approvals: <strong>{counts.approval_pending}</strong>
      </p>
      <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
        <select aria-label="Kind" value={kind}
                onChange={(e) => setKind(e.target.value)}>
          <option value="">all kinds</option>
          <option value="info">info</option>
          <option value="ack_required">ack required</option>
          <option value="approval_required">approval required</option>
        </select>
        <select aria-label="Status" value={status}
                onChange={(e) => setStatus(e.target.value)}>
          <option value="">all status</option>
          <option value="unread">unread</option>
          <option value="read">read</option>
          <option value="resolved">resolved</option>
        </select>
      </div>
      {err && <p role="alert" style={{ color: "crimson" }}>{err}</p>}
      {items.length === 0 ? <p>No messages.</p> : items.map((n) => (
        <div key={n.id} data-testid="notification" style={box}>
          <p>
            <strong>{n.subject}</strong>{" "}
            <small>[{n.kind} · {n.status}] {n.created_at.slice(0, 16).replace("T", " ")}</small>
          </p>
          {n.body && <p>{n.body}</p>}
          <p>
            <a href="#" onClick={(e) => { e.preventDefault(); onOpenRx(n.rx_id); }}>
              Open Rx
            </a>
            {n.status === "unread" && (
              <>{" "}<button onClick={async () => {
                await markNotificationRead(n.id); await reload();
              }}>mark read</button></>
            )}
          </p>
          {n.kind === "approval_required" && n.status !== "resolved" && canWrite && (
            <div style={{ borderTop: "1px dashed #ccc", paddingTop: 8 }}>
              <label>Signature (typed name)
                <input aria-label={`signature ${n.id}`}
                  value={sig[n.id] ?? ""}
                  onChange={(e) => setSig({ ...sig, [n.id]: e.target.value })} />
              </label>
              <button onClick={async () => {
                try {
                  await decideNotification(n.id, {
                    decision: "approved",
                    signature_name: sig[n.id] ?? "" });
                  await reload();
                } catch (e) {
                  setErr(e instanceof Error ? e.message : String(e));
                }
              }}>Approve</button>{" "}
              <button onClick={async () => {
                try {
                  await decideNotification(n.id, {
                    decision: "rejected",
                    signature_name: sig[n.id] ?? "" });
                  await reload();
                } catch (e) {
                  setErr(e instanceof Error ? e.message : String(e));
                }
              }}>Reject</button>
            </div>
          )}
        </div>
      ))}
    </section>
  );
}
