import { useCallback, useEffect, useState } from "react";
import { listNotifications, login, logout, me, orgs, verify2fa,
         type Me } from "./api";
import { setDisplayTz } from "./lib";
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

function routeToPath(r: Route): string {
  switch (r.name) {
    case "patients": return "/patients";
    case "patient": return `/patients/${r.id}`;
    case "rx": return "/rx";
    case "rx-new": return "/rx/new";
    case "rx-detail": return `/rx/${r.id}`;
    case "inbox": return "/inbox";
    case "settings": return "/settings";
  }
}

function pathToRoute(path: string): Route | null {
  const m = path.match(/^\/(patients|rx|inbox|settings)(?:\/([^/]+))?\/?$/);
  if (!m) return null;
  const [, section, id] = m;
  if (section === "rx" && id === "new") return { name: "rx-new" };
  if (section === "rx" && id) return { name: "rx-detail", id };
  if (section === "patients" && id) return { name: "patient", id };
  if (section === "patients") return { name: "patients" };
  if (section === "rx") return { name: "rx" };
  if (section === "inbox") return { name: "inbox" };
  if (section === "settings") return { name: "settings" };
  return null;
}

const DEMO = import.meta.env.VITE_DEMO === "1";
const APP_VERSION = import.meta.env.VITE_APP_VERSION ?? "dev";

const defaultRoute = (u: Me): Route =>
  u.org_kind === "lab" ? { name: "rx" }
    : u.permissions.includes("patient:read") ? { name: "patients" }
    : { name: "rx" };

export default function App() {
  const [user, setUser] = useState<Me | null>(null);
  const [booting, setBooting] = useState(true);
  const [route, setRoute] = useState<Route>(() =>
    pathToRoute(window.location.pathname) ?? { name: "patients" });
  // auth stages: credentials -> optional 2FA challenge -> authenticated
  const [challenge, setChallenge] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [err, setErr] = useState("");
  const [unread, setUnread] = useState(0);

  const navigate = useCallback((r: Route, replace = false) => {
    const path = routeToPath(r);
    if (path !== window.location.pathname) {
      if (replace) window.history.replaceState(null, "", path);
      else window.history.pushState(null, "", path);
    }
    setRoute(r);
  }, []);

  // Browser back/forward.
  useEffect(() => {
    const onPop = () => {
      const r = pathToRoute(window.location.pathname);
      if (r) setRoute(r);
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  // Session restore on reload — keeps the user on the deep-linked page.
  // The readable hint cookie lets us skip the /auth/me probe (and its 401
  // console noise) for visitors who were never signed in.
  useEffect(() => {
    const hinted = document.cookie.includes("easyrs_session_hint=");
    if (!hinted) { setBooting(false); return; }
    me().then(setUser).catch(() => {}).finally(() => setBooting(false));
  }, []);

  const refreshUnread = useCallback(async (u: Me) => {
    try {
      const r = await listNotifications();
      setUnread(r.counts.unread);
    } catch { /* badge is best-effort */ }
    void u;
  }, []);
  useEffect(() => { if (user) void refreshUnread(user); },
             [user, route, refreshUnread]);

  async function afterAuth() {
    const m = await me();
    setUser(m);
    // Display timestamps in the clinic/lab's configured timezone.
    try {
      const mine = (await orgs()).find((o) => o.id === m.org_id);
      setDisplayTz(mine?.timezone);
    } catch { /* tz display is best-effort */ }
    // Demo welcome shortcuts: a pre-login choice wins over the URL default.
    const demoTarget = sessionStorage.getItem("easyrs_demo_target");
    sessionStorage.removeItem("easyrs_demo_target");
    const fromUrl = pathToRoute(window.location.pathname);
    const demo = demoTarget === "patients" && m.org_kind !== "lab"
      ? { name: "patients" } as Route
      : demoTarget ? { name: "rx" } as Route : null;
    navigate(demo ?? fromUrl ?? defaultRoute(m), true);
  }

  async function onLogin(e: React.FormEvent) {
    e.preventDefault();
    setErr("");
    try {
      const r = await login(email, password);
      if (r.requires_2fa && r.challenge_id) {
        setChallenge(r.challenge_id);
        return;
      }
      await afterAuth();
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
      await afterAuth();
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    }
  }

  async function onLogout() {
    await logout();
    setUser(null);
    window.history.pushState(null, "", "/");
    setRoute({ name: "patients" });
  }

  if (booting) {
    return <main className="container"><p className="empty">Loading…</p></main>;
  }

  if (!user) {
    const demoEntry = (label: string, target: string, hint: string) => (
      <button type="button" className="demo-entry"
        onClick={() => sessionStorage.setItem("easyrs_demo_target", target)}>
        <strong>{label}</strong><br/><span className="muted">{hint}</span>
      </button>
    );
    return (
      <main className="container" style={{ maxWidth: 560 }}>
        <h1 className="brand" style={{ fontSize: "1.8rem", margin: "2rem 0 0.4rem" }}>
          EasyRS
        </h1>
        <p className="muted" style={{ marginTop: 0 }}>
          Welcome — explore the complete digital workflow between your
          dental practice and laboratory.
        </p>
        {DEMO && (
          <div className="card demo-welcome" role="group"
               aria-label="Demo shortcuts">
            <p className="demo-banner">Demo Environment — Synthetic Data Only</p>
            <div className="row">
              {demoEntry("Try the Practice Workflow", "patients",
                "Patients → cases → scans → prescriptions")}
              {demoEntry("Explore the Lab Workflow", "rx",
                "Inbox → bundle check-in → QC → delivery")}
              {demoEntry("View a Sample Prescription", "rx",
                "A completed order with files and history")}
            </div>
            <p className="muted" style={{ marginBottom: 0 }}>
              Sign in with your invited demo account; the selected workflow
              opens automatically.
            </p>
          </div>
        )}
        <div className="card">
        {challenge === null ? (
          <form onSubmit={onLogin}>
            <label className="field"><span>Email</span>
              <input name="email" autoComplete="username" value={email}
                onChange={(e) => setEmail(e.target.value)} />
            </label>
            <label className="field"><span>Password</span>
              <input name="password" type="password" autoComplete="current-password"
                value={password} onChange={(e) => setPassword(e.target.value)} />
            </label>
            <button type="submit" className="primary">Sign in</button>
            {err && <p role="alert" className="alert">{err}</p>}
          </form>
        ) : (
          <form onSubmit={onVerify}>
            <p>Two-factor authentication required.</p>
            <label className="field"><span>Authentication code</span>
              <input name="totp" inputMode="numeric" autoComplete="one-time-code"
                value={code} onChange={(e) => setCode(e.target.value)} />
            </label>
            <button type="submit" className="primary">Verify</button>
            {err && <p role="alert" className="alert">{err}</p>}
          </form>
        )}
        </div>
      </main>
    );
  }

  const isPractice = user.org_kind !== "lab";
  const canPatients = user.permissions.includes("patient:read");
  const navSection =
    route.name === "patient" ? "patients"
    : route.name === "rx-detail" || route.name === "rx-new" ? "rx"
    : route.name;
  const navBtn = (r: Route, label: string, badge = 0) => (
    <button type="button"
      aria-current={navSection === r.name ? "page" : undefined}
      onClick={() => navigate(r)}>
      {label}{badge > 0 && <span className="badge">{badge}</span>}
    </button>
  );

  // Guard: lab users / no patient:read land on rx list for patient URLs.
  const effective =
    (route.name === "patients" || route.name === "patient") && !canPatients
      ? { name: "rx" } as Route : route;

  return (
    <>
      {DEMO && (
        <div className="demo-banner" role="status">
          Demo Environment — Synthetic Data Only · EasyRS Preview {APP_VERSION}
        </div>
      )}
      <header className="appbar">
        <span className="brand">EasyRS</span>
        <span className="whoami">
          {user.display_name} — {user.role} @ {user.org_name}
        </span>
        <nav className="nav" aria-label="Primary">
          {isPractice && canPatients && navBtn({ name: "patients" }, "Patients")}
          {navBtn({ name: "rx" }, "Prescriptions")}
          {navBtn({ name: "inbox" }, "Inbox", unread)}
          {navBtn({ name: "settings" }, "Settings")}
          <button type="button" onClick={onLogout}>Sign out</button>
        </nav>
      </header>
      <main className="container">
      {effective.name === "rx" ? (
        <RxListPage me={user}
          onOpen={(id) => navigate({ name: "rx-detail", id })}
          onNew={() => navigate({ name: "rx-new" })} />
      ) : effective.name === "rx-new" ? (
        <RxCreatePage me={user}
          initialPatientId={new URLSearchParams(window.location.search)
            .get("patient") ?? undefined}
          onCreated={(id) => navigate({ name: "rx-detail", id })}
          onCancel={() => navigate({ name: "rx" })} />
      ) : effective.name === "rx-detail" ? (
        <RxDetailPage me={user} rxId={effective.id}
          onBack={() => navigate({ name: "rx" })} />
      ) : effective.name === "inbox" ? (
        <InboxPage me={user}
          onOpenRx={(id) => navigate({ name: "rx-detail", id })} />
      ) : effective.name === "settings" ? (
        <OrgSettingsPage me={user} />
      ) : effective.name === "patients" ? (
        <PatientsPage me={user}
          onOpen={(id) => navigate({ name: "patient", id })} />
      ) : (
        <PatientDetailPage me={user} patientId={effective.id}
          onDeleted={() => navigate({ name: "patients" })}
          onOpenRx={(id) => navigate({ name: "rx-detail", id })}
          onNewRx={(pid) => {
            window.history.pushState(null, "", `/rx/new?patient=${pid}`);
            setRoute({ name: "rx-new" });
          }} />
      )}
      </main>
    </>
  );
}
