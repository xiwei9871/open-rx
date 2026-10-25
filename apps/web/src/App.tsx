import { useState } from "react";
import { login, logout, me, verify2fa, type Me } from "./api";
import PatientsPage from "./pages/Patients";
import PatientDetailPage from "./pages/PatientDetail";
import RxListPage from "./pages/RxList";
import RxCreatePage from "./pages/RxCreate";
import RxDetailPage from "./pages/RxDetail";
import OrgSettingsPage from "./pages/OrgSettings";
import InboxPage from "./pages/Inbox";

type Route =
  | { name: "patients" } | { name: "patient"; id: string }
  | { name: "rx" } | { name: "rx-new" } | { name: "rx-detail"; id: string }
  | { name: "settings" } | { name: "inbox" };

const page = { fontFamily: "system-ui", maxWidth: 720, margin: "2rem auto" } as const;
const input = { display: "block", width: "100%", marginBottom: 8, padding: 4 } as const;

export default function App() {
  const [user, setUser] = useState<Me | null>(null);
  const [route, setRoute] = useState<Route>({ name: "patients" });
  // auth stages: credentials -> optional 2FA challenge -> authenticated
  const [challenge, setChallenge] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [err, setErr] = useState("");

  async function onLogin(e: React.FormEvent) {
    e.preventDefault();
    setErr("");
    try {
      const r = await login(email, password);
      if (r.requires_2fa && r.challenge_id) {
        setChallenge(r.challenge_id);
        return;
      }
      const m = await me();
      setUser(m);
      setRoute(m.org_kind === "lab" ? { name: "rx" } : { name: "patients" });
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    }
  }

  async function onVerify(e: React.FormEvent) {
    e.preventDefault();
    setErr("");
    try {
      await verify2fa(challenge!, code);
      setChallenge(null);
      setCode("");
      const m = await me();
      setUser(m);
      setRoute(m.org_kind === "lab" ? { name: "rx" } : { name: "patients" });
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    }
  }

  async function onLogout() {
    await logout();
    setUser(null);
    setRoute({ name: "patients" });
  }



  if (!user) {
    return (
      <main style={page}>
        <h1>EasyRS</h1>
        {challenge === null ? (
          <form onSubmit={onLogin}>
            <label>Email
              <input name="email" autoComplete="username" value={email}
                onChange={(e) => setEmail(e.target.value)} style={input} />
            </label>
            <label>Password
              <input name="password" type="password" autoComplete="current-password"
                value={password} onChange={(e) => setPassword(e.target.value)}
                style={input} />
            </label>
            <button type="submit">Sign in</button>
            {err && <p role="alert" style={{ color: "crimson" }}>{err}</p>}
          </form>
        ) : (
          <form onSubmit={onVerify}>
            <p>Two-factor authentication required.</p>
            <label>Authentication code
              <input name="totp" inputMode="numeric" autoComplete="one-time-code"
                value={code} onChange={(e) => setCode(e.target.value)}
                style={input} />
            </label>
            <button type="submit">Verify</button>
            {err && <p role="alert" style={{ color: "crimson" }}>{err}</p>}
          </form>
        )}
      </main>
    );
  }

  const isPractice = user.org_kind !== "lab";

  return (
    <main style={page}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <h1>EasyRS</h1>
        <nav>
          <span>{user.display_name} — {user.role} @ {user.org_name}</span>{" "}
          {isPractice && route.name !== "patients" && (
            <button onClick={() => setRoute({ name: "patients" })}>Patients</button>
          )}
          {route.name !== "rx" && (
            <button onClick={() => setRoute({ name: "rx" })}>Prescriptions</button>
          )}
          {route.name !== "inbox" && (
            <button onClick={() => setRoute({ name: "inbox" })}>Inbox</button>
          )}
          {route.name !== "settings" && (
            <button onClick={() => setRoute({ name: "settings" })}>Settings</button>
          )}
          <button onClick={onLogout}>Sign out</button>
        </nav>
      </header>
      {route.name === "rx" ? (
        <RxListPage me={user}
          onOpen={(id) => setRoute({ name: "rx-detail", id })}
          onNew={() => setRoute({ name: "rx-new" })} />
      ) : route.name === "rx-new" ? (
        <RxCreatePage me={user}
          onCreated={(id) => setRoute({ name: "rx-detail", id })}
          onCancel={() => setRoute({ name: "rx" })} />
      ) : route.name === "rx-detail" ? (
        <RxDetailPage me={user} rxId={route.id}
          onBack={() => setRoute({ name: "rx" })} />
      ) : route.name === "inbox" ? (
        <InboxPage me={user}
          onOpenRx={(id) => setRoute({ name: "rx-detail", id })} />
      ) : route.name === "settings" ? (
        <OrgSettingsPage me={user} />
      ) : route.name === "patients" ? (
        <PatientsPage me={user} onOpen={(id) => setRoute({ name: "patient", id })} />
      ) : (
        <PatientDetailPage me={user} patientId={route.id}
          onDeleted={() => setRoute({ name: "patients" })}
          onOpenRx={(id) => setRoute({ name: "rx-detail", id })} />
      )}
    </main>
  );
}
