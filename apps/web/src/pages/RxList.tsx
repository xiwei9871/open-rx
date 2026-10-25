import { useCallback, useEffect, useState } from "react";
import {
  checkInRx, getDashboard, listRx, type Dashboard, type Me, type Rx,
} from "../api";

const STATUS_LABELS: Record<string, string> = {
  draft: "Saved", submitted: "Submitted", checked_in: "Checked-In",
  in_progress: "In Progress", on_hold: "On Hold", completed: "Completed",
  reopened: "Reopened", cancelled: "Cancelled",
};

const FULFILLMENT_LABELS: Record<string, string> = {
  none: "—", qc_pending: "QC pending", qc_passed: "QC passed",
  shipped: "Shipped", received: "Received", delivered: "Delivered",
  dispatched: "Dispatched", in_transit: "In transit", exception: "Exception",
};

const th = { textAlign: "left" as const, padding: "4px 10px 4px 0" };
const td = { padding: "4px 10px 4px 0" };

export default function RxList({ me, onOpen, onNew }: {
  me: Me;
  onOpen: (id: string) => void;
  onNew: () => void;
}) {
  const isLab = me.org_kind === "lab";
  const [items, setItems] = useState<Rx[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [dash, setDash] = useState<Dashboard | null>(null);
  const [filter, setFilter] = useState("");
  const [fulFilter, setFulFilter] = useState("");
  const [dueBefore, setDueBefore] = useState("");
  const [err, setErr] = useState("");

  const reload = useCallback(async () => {
    setErr("");
    try {
      const r = await listRx(filter || undefined, {
        fulfillmentStatus: fulFilter || undefined,
        dueBefore: dueBefore || undefined,
      });
      setItems(r.items);
      setCounts(r.counts);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }, [filter, fulFilter, dueBefore]);
  useEffect(() => { void reload(); }, [reload]);
  useEffect(() => { getDashboard().then(setDash).catch(() => {}); }, []);

  async function onCheckIn(e: React.MouseEvent, id: string, version: number) {
    e.stopPropagation();
    setErr("");
    try {
      await checkInRx(id, version);
      await reload();
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    }
  }

  return (
    <section>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <h2>{isLab ? "Received Prescriptions" : "Prescriptions"}</h2>
        {!isLab && me.permissions.includes("rx:write") && (
          <button onClick={onNew}>New Rx</button>
        )}
      </header>
      {dash && (
        <div data-testid="dashboard"
             style={{ display: "flex", gap: 14, marginBottom: 8 }}>
          {Object.entries(dash.by_fulfillment)
            .filter(([k, n]) => k !== "none" && n > 0)
            .map(([k, n]) => (
              <span key={k} style={{ fontSize: 12, color: "#444" }}>
                {FULFILLMENT_LABELS[k] ?? k}: <strong>{n}</strong>
              </span>
            ))}
          {dash.due_soon.length > 0 && (
            <span data-testid="due-soon" role="status"
                  style={{ fontSize: 12, color: "#b45309" }}>
              Due soon ({dash.due_soon_hours}h): {dash.due_soon.length}
            </span>
          )}
        </div>
      )}
      <p>
        <label>Status{" "}
          <select value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="">All</option>
            {Object.entries(STATUS_LABELS).map(([v, l]) => (
              <option key={v} value={v}>{l}</option>
            ))}
          </select>
        </label>{" "}
        <label>Fulfillment{" "}
          <select value={fulFilter}
                  onChange={(e) => setFulFilter(e.target.value)}>
            <option value="">All</option>
            {Object.entries(FULFILLMENT_LABELS)
              .filter(([v]) => v !== "none")
              .map(([v, l]) => (
                <option key={v} value={v}>{l}</option>
              ))}
          </select>
        </label>{" "}
        <label>Due before{" "}
          <input type="date" value={dueBefore}
                 onChange={(e) => setDueBefore(e.target.value)} />
        </label>{" "}
        {Object.entries(counts).map(([k, n]) => (
          <span key={k} style={{ marginRight: 8, fontSize: 12, color: "#555" }}>
            {STATUS_LABELS[k] ?? k}: {n}
          </span>
        ))}
      </p>
      {err && <p role="alert" style={{ color: "crimson" }}>{err}</p>}
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <th style={th}>Rx #</th><th style={th}>Status</th>
            <th style={th}>Due</th><th style={th}>Created</th>
            {isLab && <th style={th}>Action</th>}
          </tr>
        </thead>
        <tbody>
          {items.map((r) => (
            <tr key={r.id} onClick={() => onOpen(r.id)}
                style={{ cursor: "pointer", borderTop: "1px solid #ddd" }}>
              <td style={td}>{r.rx_number}</td>
              <td style={td}>
                {STATUS_LABELS[r.status] ?? r.status}
                {r.checked_in_via === "download" && " (via download)"}
                {r.fulfillment_status !== "none" && (
                  <span style={{ color: "#555", fontSize: 12 }}>
                    {" "}· {FULFILLMENT_LABELS[r.fulfillment_status]
                        ?? r.fulfillment_status}
                  </span>
                )}
              </td>
              <td style={td}>{r.due_date ?? "—"}</td>
              <td style={td}>{r.created_at.slice(0, 10)}</td>
              {isLab && (
                <td style={td}>
                  {r.status === "submitted" && (
                    <button onClick={(e) => onCheckIn(e, r.id, r.version)}>Check in</button>
                  )}
                </td>
              )}
            </tr>
          ))}
          {items.length === 0 && (
            <tr><td colSpan={5} style={td}><em>No prescriptions.</em></td></tr>
          )}
        </tbody>
      </table>
    </section>
  );
}
