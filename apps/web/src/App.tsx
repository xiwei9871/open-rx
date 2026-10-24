import { useState } from "react";
import { login, logout, me, verify2fa, type Me } from "./api";
import PatientsPage from "./pages/Patients";
import PatientDetailPage from "./pages/PatientDetail";

type Route = { name: "patients" } | { name: "patient"; id: string };

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
      setUser(await me());
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
      setUser(await me());
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

  return (
    <main style={page}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <h1>EasyRS</h1>
        <nav>
          <span>{user.display_name} — {user.role} @ {user.org_name}</span>{" "}
          {route.name !== "patients" && (
            <button onClick={() => setRoute({ name: "patients" })}>Patients</button>
          )}
          <button onClick={onLogout}>Sign out</button>
        </nav>
      </header>
      {route.name === "patients" ? (
        <PatientsPage me={user} onOpen={(id) => setRoute({ name: "patient", id })} />
      ) : (
        <PatientDetailPage me={user} patientId={route.id}
          onDeleted={() => setRoute({ name: "patients" })} />
      )}
    </main>
  );
}
