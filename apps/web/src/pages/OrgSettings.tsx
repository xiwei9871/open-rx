import { useEffect, useState } from "react";
import {
  changePassword, createLocation, createRosterMember, decideConnection,
  listFullConnections, listLocations, listRoster, orgs, requestConnection,
  updateLocation, updateOrg, updateRosterMember,
  type FullConnection, type Location, type Me, type Org,
} from "../api";

const input = { display: "block", width: "100%", marginBottom: 8, padding: 4 } as const;
const box = { border: "1px solid #ddd", borderRadius: 6, padding: 12,
              marginBottom: 16 } as const;

type Roster = Awaited<ReturnType<typeof listRoster>>[number];

/** M1 practice/lab self-admin: org profile + defaults (IAM-001/010),
 *  locations (IAM-002), roster (IAM-003/004), connections (IAM-007),
 *  password change (IAM-009). Server-side permissions are authoritative —
 *  UI only hides sections the caller cannot use. */
export default function OrgSettings({ me }: { me: Me }) {
  const canManage = me.permissions.includes("org:manage");
  const canLocation = me.permissions.includes("location:write");
  const canRoster = me.permissions.includes("roster:write");
  const canConnection = me.permissions.includes("connection:write");
  const canSeeRoster = me.permissions.includes("roster:read") || canRoster;

  const [org, setOrg] = useState<Org | null>(null);
  const [allOrgs, setAllOrgs] = useState<Org[]>([]);
  const [locations, setLocations] = useState<Location[]>([]);
  const [roster, setRoster] = useState<Roster[]>([]);
  const [conns, setConns] = useState<FullConnection[]>([]);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [loading, setLoading] = useState(true);

  const [tz, setTz] = useState("");
  const [defDoc, setDefDoc] = useState("");
  const [defLoc, setDefLoc] = useState("");
  const [locName, setLocName] = useState("");
  const [rosName, setRosName] = useState("");
  const [rosKind, setRosKind] = useState<"doctor" | "staff">("doctor");
  const [labPick, setLabPick] = useState("");
  const [pwOld, setPwOld] = useState("");
  const [pwNew, setPwNew] = useState("");

  async function reload() {
    if (!me.org_id) { setLoading(false); return; }
    const o = await orgs();
    const mine = o.find((x) => x.id === me.org_id) ?? null;
    setOrg(mine); setAllOrgs(o);
    if (mine) {
      setTz(mine.timezone);
      setDefDoc(mine.default_doctor_id ?? "");
      setDefLoc(mine.default_location_id ?? "");
    }
    try { setLocations(await listLocations(me.org_id)); } catch { /* perms */ }
    try { if (canSeeRoster) setRoster(await listRoster(me.org_id)); } catch { /* */ }
    try { setConns(await listFullConnections(me.org_id)); } catch { /* */ }
    setLoading(false);
  }

  useEffect(() => {
    reload().catch((e) => {
      setErr(e instanceof Error ? e.message : String(e)); setLoading(false);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [me.org_id]);

  async function run(fn: () => Promise<unknown>, ok: string) {
    setErr(""); setMsg("");
    try { await fn(); setMsg(ok); await reload(); }
    catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
  }

  if (loading) return <p>Loading settings…</p>;
  if (!org) return <p role="alert">No organization context.</p>;

  const doctors = roster.filter((r) => r.kind === "doctor" && r.status === "active");
  const candidateLabs = allOrgs.filter(
    (o) => o.id !== org.id && (o.kind === "lab" || o.kind === "hybrid")
      && !conns.some((c) =>
          (c.practice_org_id === org.id || c.lab_org_id === org.id)
          && (c.practice_org_id === o.id || c.lab_org_id === o.id)
          && c.status !== "withdrawn" && c.status !== "rejected"));

  return (
    <section>
      <h2>Organization settings</h2>
      {err && <p role="alert" style={{ color: "crimson" }}>{err}</p>}
      {msg && <p role="status" style={{ color: "green" }}>{msg}</p>}

      {canManage && (
        <div style={box}>
          <h3>Profile &amp; defaults</h3>
          <label>Timezone (org-level)
            <input aria-label="Timezone" value={tz}
                   onChange={(e) => setTz(e.target.value)} style={input} />
          </label>
          <label>Default doctor
            <select aria-label="Default doctor" value={defDoc}
                    onChange={(e) => setDefDoc(e.target.value)} style={input}>
              <option value="">— none —</option>
              {doctors.map((d) => <option key={d.id} value={d.id}>{d.display_name}</option>)}
            </select>
          </label>
          <label>Default location
            <select aria-label="Default location" value={defLoc}
                    onChange={(e) => setDefLoc(e.target.value)} style={input}>
              <option value="">— none —</option>
              {locations.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
            </select>
          </label>
          <button onClick={() => run(() => updateOrg(org.id, {
            timezone: tz || "UTC",
            default_doctor_id: defDoc || null,
            default_location_id: defLoc || null,
          }), "Saved")}>Save</button>
        </div>
      )}

      {canLocation && (
        <div style={box}>
          <h3>Locations</h3>
          <ul>
            {locations.map((l) => (
              <li key={l.id}>{l.name}{l.address ? ` — ${l.address}` : ""}{" "}
                <button onClick={() => {
                  const name = window.prompt("Location name", l.name);
                  if (name) run(() => updateLocation(org.id, l.id, { name }), "Updated");
                }}>rename</button>
              </li>
            ))}
          </ul>
          <label>New location
            <input aria-label="New location" value={locName}
                   onChange={(e) => setLocName(e.target.value)} style={input} />
          </label>
          <button onClick={() => run(async () => {
            await createLocation(org.id, { name: locName }); setLocName("");
          }, "Location added")}>Add location</button>
        </div>
      )}

      {canRoster && (
        <div style={box}>
          <h3>Roster</h3>
          <ul>
            {roster.map((r) => (
              <li key={r.id}>
                {r.display_name} ({r.kind}){r.is_default ? " — default" : ""}
                {r.status === "disabled" ? " — disabled" : ""}{" "}
                {!r.is_default && r.status === "active" && (
                  <button onClick={() => run(() =>
                    updateRosterMember(org.id, r.id, { is_default: true }),
                    "Default updated")}>set default</button>)}
                {r.status === "active" ? (
                  <button onClick={() => run(() =>
                    updateRosterMember(org.id, r.id, { status: "disabled" }),
                    "Disabled")}>disable</button>
                ) : (
                  <button onClick={() => run(() =>
                    updateRosterMember(org.id, r.id, { status: "active" }),
                    "Enabled")}>enable</button>
                )}
              </li>
            ))}
          </ul>
          <label>Name
            <input aria-label="Roster name" value={rosName}
                   onChange={(e) => setRosName(e.target.value)} style={input} />
          </label>
          <label>Kind
            <select aria-label="Roster kind" value={rosKind}
                    onChange={(e) => setRosKind(e.target.value as "doctor" | "staff")}>
              <option value="doctor">doctor</option>
              <option value="staff">staff</option>
            </select>
          </label>
          <button onClick={() => run(async () => {
            await createRosterMember(org.id,
              { kind: rosKind, display_name: rosName }); setRosName("");
          }, "Added")}>Add roster member</button>
        </div>
      )}

      {canConnection && (
        <div style={box}>
          <h3>Connections</h3>
          <ul>
            {conns.map((c) => {
              const otherId = c.practice_org_id === org.id
                ? c.lab_org_id : c.practice_org_id;
              const other = allOrgs.find((o) => o.id === otherId);
              const weInitiated = c.initiated_by_org_id === org.id;
              return (
                <li key={c.id}>
                  {other?.name ?? otherId} — {c.status}
                  {c.status === "pending" && !weInitiated && (<>
                    {" "}<button onClick={() => run(() =>
                      decideConnection(c.id, "accept", c.version), "Accepted")}>
                      accept</button>
                    {" "}<button onClick={() => run(() =>
                      decideConnection(c.id, "reject", c.version), "Rejected")}>
                      reject</button>
                  </>)}
                  {c.status === "pending" && weInitiated && (
                    <>{""}<button onClick={() => run(() =>
                      decideConnection(c.id, "withdraw", c.version),
                      "Withdrawn")}>withdraw</button></>)}
                  {c.status === "accepted" && (
                    <>{""}<button onClick={() => run(() =>
                      decideConnection(c.id, "revoke", c.version), "Revoked")}>
                      revoke</button></>)}
                </li>
              );
            })}
          </ul>
          {org.kind !== "lab" && (
            <>
              <label>Request connection to lab
                <select aria-label="Lab to connect" value={labPick}
                        onChange={(e) => setLabPick(e.target.value)} style={input}>
                  <option value="">— select lab —</option>
                  {candidateLabs.map((o) => (
                    <option key={o.id} value={o.id}>{o.name}</option>))}
                </select>
              </label>
              <button disabled={!labPick} onClick={() => run(async () => {
                await requestConnection(org.id, labPick); setLabPick("");
              }, "Request sent")}>Request connection</button>
            </>
          )}
        </div>
      )}

      <div style={box}>
        <h3>Security</h3>
        <label>Current password
          <input aria-label="Current password" type="password" value={pwOld}
                 onChange={(e) => setPwOld(e.target.value)} style={input}
                 autoComplete="current-password" />
        </label>
        <label>New password
          <input aria-label="New password" type="password" value={pwNew}
                 onChange={(e) => setPwNew(e.target.value)} style={input}
                 autoComplete="new-password" />
        </label>
        <button onClick={() => run(async () => {
          await changePassword(pwOld, pwNew); setPwOld(""); setPwNew("");
        }, "Password changed")}>Change password</button>
      </div>
    </section>
  );
}
