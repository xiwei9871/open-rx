import { useState } from "react";
import { login, logout, me, orgs, type Me, type Org } from "./api";

export default function App() {
  // No prefilled credentials — demo accounts exist only in the dev seed and
  // are never baked into the UI.
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [user, setUser] = useState<Me | null>(null);
  const [orgList, setOrgs] = useState<Org[]>([]);
  const [err, setErr] = useState("");

  async function onLogin(e: React.FormEvent) {
    e.preventDefault();
    setErr("");
    try {
      const r = await login(email, password);
      if (r.requires_2fa) { setErr("2FA required — not wired in B0 UI"); return; }
      setUser(await me());
      setOrgs(await orgs());
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    }
  }

  async function onLogout() {
    await logout();
    setUser(null); setOrgs([]);
  }

  return (
    <main style={{ fontFamily: "system-ui", maxWidth: 480, margin: "4rem auto" }}>
      <h1>EasyRS</h1>
      {!user ? (
        <form onSubmit={onLogin}>
          <label>Email
            <input name="email" autoComplete="username" value={email}
              onChange={(e) => setEmail(e.target.value)}
              style={{ display: "block", width: "100%" }} />
          </label>
          <label>Password
            <input name="password" type="password" autoComplete="current-password"
              value={password} onChange={(e) => setPassword(e.target.value)}
              style={{ display: "block", width: "100%" }} />
          </label>
          <button type="submit" style={{ marginTop: 12 }}>Sign in</button>
          {err && <p role="alert" style={{ color: "crimson" }}>{err}</p>}
        </form>
      ) : (
        <section>
          <p>Signed in as <strong>{user.display_name}</strong> ({user.email}) — {user.role}</p>
          <h2>Organizations</h2>
          <ul>{orgList.map((o) => <li key={o.id}>{o.name} — {o.kind} ({o.status})</li>)}</ul>
          <button onClick={onLogout}>Sign out</button>
        </section>
      )}
    </main>
  );
}
