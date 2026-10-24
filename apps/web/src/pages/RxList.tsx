import { useEffect, useState } from "react";
import { checkInRx, listRx, type Me, type Rx } from "../api";

const STATUS_LABELS: Record<string, string> = {
  draft: "Saved", submitted: "Submitted", checked_in: "Checked-In",
  in_progress: "In Progress", on_hold: "On Hold", completed: "Completed",
  reopened: "Reopened", cancelled: "Cancelled",
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
  const [filter, setFilter] = useState("");
  const [err, setErr] = useState("");

  async function reload(status?: string) {
    setErr("");
    try {
      const r = await listRx(status || undefined);
      setItems(r.items);
      setCounts(r.counts);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }
  useEffect(() => { void reload(filter); }, [filter]);

  async function onCheckIn(e: React.MouseEvent, id: string, version: number) {
    e.stopPropagation();
    setErr("");
    try {
      await checkInRx(id, version);
      await reload(filter);
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
      <p>
        <label>Status{" "}
          <select value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="">All</option>
            {Object.entries(STATUS_LABELS).map(([v, l]) => (
              <option key={v} value={v}>{l}</option>
            ))}
          </select>
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
