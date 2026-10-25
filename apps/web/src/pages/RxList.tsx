import { useCallback, useEffect, useState } from "react";
import {
  checkInRx, getDashboard, listRx, type Dashboard, type Me, type Rx,
} from "../api";
import {
  fmtDate, fulfillmentLabel, FULFILLMENT_LABELS, statusLabel,
  STATUS_LABELS,
} from "../lib";

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
  const [busyId, setBusyId] = useState<string | null>(null);

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
    if (busyId) return;
    setErr(""); setBusyId(id);
    try {
      await checkInRx(id, version);
      await reload();
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setBusyId(null);
    }
  }

  const total = Object.values(counts).reduce((a, b) => a + b, 0);

  return (
    <section>
      <div className="page-head">
        <h2>{isLab ? "Received Prescriptions" : "Prescriptions"}</h2>
        {!isLab && me.permissions.includes("rx:write") && (
          <button className="primary" onClick={onNew}>New Rx</button>
        )}
      </div>
      <div className="stats" data-testid="dashboard">
        <div className="stat">
          <div className="n">{total}</div>
          <div className="l">Total shown</div>
        </div>
        {Object.entries(counts).filter(([, n]) => n > 0).map(([k, n]) => (
          <div className="stat" key={k}>
            <div className="n">{n}</div>
            <div className="l">{statusLabel(k)}</div>
          </div>
        ))}
        {dash && Object.entries(dash.by_fulfillment)
          .filter(([k, n]) => k !== "none" && n > 0)
          .map(([k, n]) => (
            <div className="stat" key={k}>
              <div className="n">{n}</div>
              <div className="l">{fulfillmentLabel(k)}</div>
            </div>
          ))}
        {dash && dash.due_soon.length > 0 && (
          <div className="stat warn" data-testid="due-soon" role="status">
            <div className="n">{dash.due_soon.length}</div>
            <div className="l">Due soon ({dash.due_soon_hours}h)</div>
          </div>
        )}
      </div>
      <div className="toolbar">
        <label>Status{" "}
          <select value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="">All</option>
            {Object.entries(STATUS_LABELS).map(([v, l]) => (
              <option key={v} value={v}>{l}</option>
            ))}
          </select>
        </label>
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
        </label>
        <label>Due before{" "}
          <input type="date" value={dueBefore}
                 onChange={(e) => setDueBefore(e.target.value)} />
        </label>
      </div>
      {err && <p role="alert" className="alert">{err}</p>}
      <div className="card" style={{ padding: 0 }}>
      <div className="table-wrap">
      <table className="data">
        <thead>
          <tr>
            <th>Rx #</th><th>Patient</th>
            <th className="hide-sm">{isLab ? "Practice" : "Lab"}</th>
            <th>Status</th><th className="hide-sm">Fulfillment</th>
            <th>Due</th><th className="hide-sm">Created</th>
            {isLab && <th>Action</th>}
          </tr>
        </thead>
        <tbody>
          {items.map((r) => (
            <tr key={r.id} className="clickable" onClick={() => onOpen(r.id)}>
              <td><strong>{r.rx_number}</strong></td>
              <td>{r.patient_label ?? r.patient_id.slice(0, 8) + "…"}</td>
              <td className="hide-sm">
                {(isLab ? r.practice_name : r.lab_name) ?? "—"}</td>
              <td>
                <span className={`pill st-${r.status}`}>
                  {statusLabel(r.status)}
                </span>
                {r.checked_in_via === "download" &&
                  <small className="muted"> (dl)</small>}
              </td>
              <td className="hide-sm">
                {r.fulfillment_status !== "none" ? (
                  <span className={`pill st-${r.fulfillment_status}`}>
                    {fulfillmentLabel(r.fulfillment_status)}
                  </span>
                ) : "—"}
              </td>
              <td>{fmtDate(r.due_date)}</td>
              <td className="hide-sm">{fmtDate(r.created_at)}</td>
              {isLab && (
                <td>
                  {r.status === "submitted" && (
                    <button className="small" disabled={busyId === r.id}
                      onClick={(e) => onCheckIn(e, r.id, r.version)}>
                      {busyId === r.id ? "…" : "Check in"}
                    </button>
                  )}
                </td>
              )}
            </tr>
          ))}
          {items.length === 0 && (
            <tr><td colSpan={8}><em className="empty">No prescriptions.</em></td></tr>
          )}
        </tbody>
      </table>
      </div>
      </div>
    </section>
  );
}
