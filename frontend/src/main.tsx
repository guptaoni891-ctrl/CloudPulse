import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  AreaChart,
  Area,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import {
  Activity,
  Server,
  Bell,
  Cpu,
  HardDrive,
  MemoryStick,
  Plus,
  ArrowLeft,
  RefreshCw,
  LogOut,
  Network,
} from "lucide-react";
import "./style.css";

type Metric = {
  id: number;
  timestamp: string;
  cpu: number;
  memory: number;
  disk: number;
  network_sent_bytes: number;
  network_recv_bytes: number;
};
type Host = {
  id: string;
  name: string;
  enabled: boolean;
  online: boolean;
  last_seen: string | null;
  latest: Metric | null;
};
type Alert = {
  id: number;
  host_id: string;
  metric: string;
  state: string;
  value: number;
  threshold: number;
  timestamp: string;
};
type Rule = { id: number; metric: string; threshold: number; active: boolean };
const fmt = (v: number | undefined) =>
  v === undefined ? "—" : `${v.toFixed(1)}%`;
const date = (s: string | null) =>
  s ? new Date(s).toLocaleString() : "Awaiting first sample";

function readHostHash() {
  const value = window.location.hash.slice(1);
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
    value,
  )
    ? value
    : null;
}

function App() {
  const requestVersion = useRef(0);
  const sessionVersion = useRef(0);
  const [token, setToken] = useState("");
  const [draft, setDraft] = useState("");
  const [hosts, setHosts] = useState<Host[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [selected, setSelected] = useState<string | null>(readHostHash());
  const [page, setPage] = useState<"hosts" | "alerts">("hosts");
  const [history, setHistory] = useState<Metric[]>([]);
  const [rules, setRules] = useState<Rule[]>([]);
  const [range, setRange] = useState(1);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [updated, setUpdated] = useState<string | null>(null);
  const [registration, setRegistration] = useState<{
    id: string;
    key: string;
  } | null>(null);
  const [showRegister, setShowRegister] = useState(false);
  const [name, setName] = useState("");
  const [ruleMetric, setRuleMetric] = useState("cpu");
  const [threshold, setThreshold] = useState(80);
  const [busy, setBusy] = useState(false);
  const current = hosts.find((h) => h.id === selected);
  async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
    const session = sessionVersion.current;
    const response = await fetch(`/api/v1${path}`, {
      signal: AbortSignal.timeout(15000),
      ...options,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
        ...options.headers,
      },
    });
    const body = await response.json().catch(() => ({}));
    if (session !== sessionVersion.current)
      throw new DOMException("Session ended", "AbortError");
    if (!response.ok) {
      if (response.status === 401)
        throw new Error(
          "Authentication failed. Check the admin token and sign in again.",
        );
      throw new Error(
        typeof body.detail === "string"
          ? body.detail
          : `Request failed (${response.status})`,
      );
    }
    return body;
  }
  async function refresh() {
    const version = ++requestVersion.current;
    setLoading(true);
    try {
      const [h, a] = await Promise.all([
        api<Host[]>("/hosts"),
        api<Alert[]>(
          selected
            ? `/alerts?host_id=${encodeURIComponent(selected)}`
            : "/alerts",
        ),
      ]);
      let data: Metric[] = [];
      let r: Rule[] = [];
      if (selected)
        [data, r] = await Promise.all([
          api<Metric[]>(
            `/hosts/${selected}/metrics?start=${encodeURIComponent(new Date(Date.now() - range * 3600000).toISOString())}&limit=5000`,
          ),
          api<Rule[]>(`/hosts/${selected}/rules`),
        ]);
      if (version !== requestVersion.current) return;
      setHosts(h);
      setAlerts(a);
      setHistory(data);
      setRules(r);
      setError("");
      setUpdated(new Date().toLocaleTimeString());
    } catch (e) {
      if (version === requestVersion.current) setError((e as Error).message);
    } finally {
      if (version === requestVersion.current) setLoading(false);
    }
  }
  useEffect(() => {
    if (!token) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    // Schedule after completion, so slow responses cannot starve polling updates.
    const run = async () => {
      await refresh();
      if (active) timer = setTimeout(run, 10000);
    };
    void run();
    return () => {
      active = false;
      requestVersion.current++;
      clearTimeout(timer);
    };
  }, [token, selected, range]);
  useEffect(() => {
    const handler = () => setSelected(readHostHash());
    window.addEventListener("hashchange", handler);
    return () => window.removeEventListener("hashchange", handler);
  }, []);
  function signOut() {
    sessionVersion.current++;
    requestVersion.current++;
    setToken("");
    setDraft("");
    setRegistration(null);
    setHosts([]);
    setAlerts([]);
    setHistory([]);
    setRules([]);
    setShowRegister(false);
    setName("");
    setError("");
    setUpdated(null);
    setLoading(false);
    setBusy(false);
    setPage("hosts");
    setSelected(null);
    window.location.hash = "";
  }
  function navigate(id: string | null) {
    setHistory([]);
    setRules([]);
    setSelected(id);
    window.location.hash = id || "";
    setPage("hosts");
  }
  async function register(e: React.FormEvent) {
    e.preventDefault();
    const session = sessionVersion.current;
    setBusy(true);
    try {
      const r = await api<{ host: Host; api_key: string }>("/hosts", {
        method: "POST",
        body: JSON.stringify({ name }),
      });
      setRegistration({ id: r.host.id, key: r.api_key });
      setName("");
      setShowRegister(false);
      await refresh();
    } catch (e) {
      if (session === sessionVersion.current) setError((e as Error).message);
    } finally {
      if (session === sessionVersion.current) setBusy(false);
    }
  }
  async function saveRule(e: React.FormEvent) {
    e.preventDefault();
    const session = sessionVersion.current;
    setBusy(true);
    try {
      await api(`/hosts/${selected}/rules`, {
        method: "PUT",
        body: JSON.stringify({ metric: ruleMetric, threshold }),
      });
      await refresh();
    } catch (e) {
      if (session === sessionVersion.current) setError((e as Error).message);
    } finally {
      if (session === sessionVersion.current) setBusy(false);
    }
  }
  async function toggleHost() {
    if (!current) return;
    const session = sessionVersion.current;
    setBusy(true);
    try {
      await api(`/hosts/${current.id}`, {
        method: "PATCH",
        body: JSON.stringify({ enabled: !current.enabled }),
      });
      await refresh();
    } catch (e) {
      if (session === sessionVersion.current) setError((e as Error).message);
    } finally {
      if (session === sessionVersion.current) setBusy(false);
    }
  }
  if (!token)
    return (
      <main className="login">
        <div className="login-card">
          <div className="brand">
            <span className="logo">
              <Activity />
            </span>
            CloudPulse
          </div>
          <span className="eyebrow">YOUR INFRASTRUCTURE, IN FOCUS</span>
          <h1>
            Know how your
            <br />
            systems are doing.
          </h1>
          <p>
            Sign in with your local admin token to monitor your machines and
            investigate performance.
          </p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              setToken(draft);
              setDraft("");
            }}
          >
            <label htmlFor="token">Admin token</label>
            <input
              id="token"
              autoComplete="off"
              type="password"
              required
              minLength={32}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Enter your bootstrap token"
            />
            <button className="primary">Open dashboard →</button>
          </form>
          <small>Your token stays in memory and clears when you reload.</small>
        </div>
        <div className="login-art">
          <Activity size={100} />
          <h2>
            A clear signal.
            <br />
            Every machine.
          </h2>
          <p>CPU · Memory · Disk · Network</p>
        </div>
      </main>
    );
  const online = hosts.filter((h) => h.online).length;
  const visibleAlerts = selected
    ? alerts.filter((a) => a.host_id === selected)
    : alerts;
  return (
    <div className="shell">
      <aside>
        <div className="brand">
          <span className="logo">
            <Activity />
          </span>
          CloudPulse<span className="version">v0.1</span>
        </div>
        <div className="nav-label">WORKSPACE</div>
        <button
          className={page === "hosts" ? "nav active" : "nav"}
          onClick={() => navigate(null)}
        >
          <Server size={18} />
          Infrastructure<span>{hosts.length}</span>
        </button>
        <button
          className={page === "alerts" ? "nav active" : "nav"}
          onClick={() => {
            navigate(null);
            setPage("alerts");
          }}
        >
          <Bell size={18} />
          Alert history
        </button>
        <div className="aside-footer">
          <span className="dot" />
          Local workspace
          <button onClick={signOut} aria-label="Sign out">
            <LogOut size={17} />
          </button>
        </div>
      </aside>
      <main>
        <header>
          <span>
            Workspace <span className="muted">/</span>{" "}
            {page === "alerts" ? "Alert history" : "Infrastructure"}{" "}
            {current && <> / {current.name}</>}
          </span>
          <div className="toolbar">
            <span className="muted">
              {updated ? `Updated ${updated}` : "Connecting…"}
            </span>
            <button
              onClick={() => void refresh()}
              disabled={loading}
              aria-label="Refresh"
            >
              <RefreshCw size={16} className={loading ? "spin" : ""} />
            </button>
          </div>
        </header>
        <div className="content">
          {error && (
            <div role="alert" className="error">
              {error} <button onClick={signOut}>Sign in again</button>
            </div>
          )}
          {registration && (
            <div className="notice">
              <strong>Agent registered — save this key now.</strong>
              <p>
                Set these environment variables on the monitored machine, then
                run cloudpulse-agent. The key is only shown once.
              </p>
              <pre>
                CLOUDPULSE_HOST_ID={registration.id}
                {"\n"}CLOUDPULSE_AGENT_KEY={registration.key}
              </pre>
              <button onClick={() => setRegistration(null)}>
                I have saved the key
              </button>
            </div>
          )}
          <div className="page-heading">
            <div>
              {selected && (
                <button className="back" onClick={() => navigate(null)}>
                  <ArrowLeft size={14} /> All machines
                </button>
              )}
              <span className="eyebrow">
                OBSERVABILITY / {page === "alerts" ? "EVENTS" : "OVERVIEW"}
              </span>
              <h1>
                {page === "alerts"
                  ? "Alert history"
                  : current?.name || "Infrastructure"}
              </h1>
              <p>
                {selected
                  ? "Real system metrics. A closer look at your machine."
                  : "A live view of your systems, all in one place."}
              </p>
            </div>
            <div className="toolbar">
              {selected ? (
                <>
                  <span className={`badge ${current?.online ? "online" : ""}`}>
                    {current?.online
                      ? "Online"
                      : current?.enabled === false
                        ? "Disabled"
                        : "Offline"}
                  </span>
                  <button
                    disabled={busy || !current}
                    onClick={() => void toggleHost()}
                  >
                    {current?.enabled ? "Disable agent" : "Enable agent"}
                  </button>
                </>
              ) : (
                page === "hosts" && (
                  <button
                    className="primary"
                    onClick={() => setShowRegister(!showRegister)}
                  >
                    <Plus size={16} />
                    Register machine
                  </button>
                )
              )}
            </div>
          </div>
          {showRegister && (
            <form className="panel inline-form" onSubmit={register}>
              <label htmlFor="hostname">Machine name</label>
              <input
                id="hostname"
                required
                maxLength={100}
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. production-api-01"
              />
              <button className="primary" disabled={busy}>
                Create agent key
              </button>
            </form>
          )}
          {page === "hosts" && !selected && (
            <>
              <div className="summary-grid">
                <div className="summary">
                  <span>
                    Total machines
                    <Server size={18} />
                  </span>
                  <strong>{hosts.length}</strong>
                  <small>Registered in this workspace</small>
                </div>
                <div className="summary">
                  <span>
                    Online now
                    <Activity size={18} />
                  </span>
                  <strong>
                    {online}
                    <em className="green">healthy connection</em>
                  </strong>
                  <small>Within the configured heartbeat window</small>
                </div>
                <div className="summary">
                  <span>
                    Offline machines
                    <Network size={18} />
                  </span>
                  <strong>{hosts.length - online}</strong>
                  <small>Includes disabled and pending agents</small>
                </div>
              </div>
              <section className="panel">
                <div className="panel-heading">
                  <h2>
                    Your machines <span className="count">{hosts.length}</span>
                  </h2>
                  <span className="muted">Auto-refresh · 10s</span>
                </div>
                {hosts.length === 0 ? (
                  <div className="empty">
                    <Server size={36} />
                    <h3>
                      {loading
                        ? "Loading machines…"
                        : "Your first machine starts here"}
                    </h3>
                    <p>
                      Register an agent and send a real sample to see metrics.
                    </p>
                  </div>
                ) : (
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>Machine</th>
                          <th>Status</th>
                          <th>CPU</th>
                          <th>Memory</th>
                          <th>Disk</th>
                          <th>Last seen</th>
                        </tr>
                      </thead>
                      <tbody>
                        {hosts.map((h) => (
                          <tr key={h.id}>
                            <td>
                              <button
                                className="host-link"
                                onClick={() => navigate(h.id)}
                              >
                                <span className="server-icon">
                                  <Server size={18} />
                                </span>
                                <span>
                                  {h.name}
                                  <small>{h.id.slice(0, 8)}</small>
                                </span>
                              </button>
                            </td>
                            <td>
                              <span
                                className={`badge ${h.online ? "online" : ""}`}
                              >
                                {h.online
                                  ? "Online"
                                  : !h.enabled
                                    ? "Disabled"
                                    : "Offline"}
                              </span>
                            </td>
                            {(["cpu", "memory", "disk"] as const).map((k) => (
                              <td key={k}>
                                <div className="meter-value">
                                  {fmt(h.latest?.[k])}
                                </div>
                                <div className="meter">
                                  <i
                                    style={{ width: `${h.latest?.[k] || 0}%` }}
                                  />
                                </div>
                              </td>
                            ))}
                            <td className="muted">{date(h.last_seen)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            </>
          )}
          {selected && page === "hosts" && (
            <>
              <div className="metric-grid">
                {(
                  [
                    { key: "cpu", label: "CPU utilization", Icon: Cpu },
                    { key: "memory", label: "Memory usage", Icon: MemoryStick },
                    { key: "disk", label: "Disk usage", Icon: HardDrive },
                  ] as const
                ).map(({ key, label, Icon }) => (
                  <div className="summary" key={key}>
                    <span>
                      {label}
                      <Icon size={18} />
                    </span>
                    <strong>{fmt(current?.latest?.[key])}</strong>
                    <small>Latest reported observation</small>
                  </div>
                ))}
                <div className="summary">
                  <span>
                    Network total
                    <Network size={18} />
                  </span>
                  <strong className="network-number">
                    {current?.latest
                      ? `${((current.latest.network_sent_bytes + current.latest.network_recv_bytes) / 1024 / 1024).toFixed(1)} MB`
                      : "—"}
                  </strong>
                  <small>Cumulative sent + received</small>
                </div>
              </div>
              <section className="panel">
                <div className="panel-heading">
                  <div>
                    <h2>Resource utilization</h2>
                    <small className="muted">
                      Latest {history.length} samples · local time · percentages
                    </small>
                  </div>
                  <select
                    aria-label="History time range"
                    value={range}
                    onChange={(e) => setRange(Number(e.target.value))}
                  >
                    <option value={1}>Last hour</option>
                    <option value={6}>Last 6 hours</option>
                    <option value={24}>Last 24 hours</option>
                    <option value={168}>Last 7 days</option>
                  </select>
                </div>
                <div className="legend">
                  <span style={{ color: "#60a5fa" }}>● CPU</span>
                  <span style={{ color: "#a78bfa" }}>● Memory</span>
                  <span style={{ color: "#34d399" }}>● Disk</span>
                </div>
                {history.length ? (
                  <div className="chart">
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart
                        data={history.map((m) => ({
                          ...m,
                          time: Date.parse(m.timestamp),
                        }))}
                      >
                        <defs>
                          <linearGradient id="blue" x1="0" y1="0" x2="0" y2="1">
                            <stop
                              offset="0%"
                              stopColor="#3b82f6"
                              stopOpacity={0.25}
                            />
                            <stop
                              offset="100%"
                              stopColor="#3b82f6"
                              stopOpacity={0}
                            />
                          </linearGradient>
                        </defs>
                        <CartesianGrid
                          stroke="#242c38"
                          strokeDasharray="3 5"
                          vertical={false}
                        />
                        <XAxis
                          dataKey="time"
                          type="number"
                          scale="time"
                          domain={["dataMin", "dataMax"]}
                          tickFormatter={(v) =>
                            new Date(v).toLocaleTimeString([], {
                              hour: "2-digit",
                              minute: "2-digit",
                            })
                          }
                          stroke="#7a8598"
                          minTickGap={45}
                        />
                        <YAxis
                          domain={[0, 100]}
                          stroke="#7a8598"
                          tickFormatter={(v) => `${v}%`}
                        />
                        <Tooltip
                          contentStyle={{
                            background: "#141b27",
                            border: "1px solid #303b4e",
                            borderRadius: 8,
                          }}
                          labelFormatter={(v) =>
                            new Date(Number(v)).toLocaleString()
                          }
                        />
                        <Area
                          type="monotone"
                          dataKey="cpu"
                          stroke="#60a5fa"
                          fill="url(#blue)"
                          strokeWidth={2}
                          isAnimationActive={false}
                        />
                        <Area
                          type="monotone"
                          dataKey="memory"
                          stroke="#a78bfa"
                          fill="transparent"
                          strokeWidth={2}
                          isAnimationActive={false}
                        />
                        <Area
                          type="monotone"
                          dataKey="disk"
                          stroke="#34d399"
                          fill="transparent"
                          strokeWidth={2}
                          isAnimationActive={false}
                        />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                ) : (
                  <div className="empty">
                    <Activity size={32} />
                    <h3>No samples in this time range</h3>
                    <p>Start the agent or select a wider range.</p>
                  </div>
                )}
              </section>
              <section className="panel">
                <div className="panel-heading">
                  <h2>Threshold rules</h2>
                  <span className="muted">Evaluated on each new sample</span>
                </div>
                <div className="rules">
                  {rules.map((r) => (
                    <span className="rule" key={r.id}>
                      {r.metric.toUpperCase()} ≥ {r.threshold}%{" "}
                      <span className={r.active ? "red" : "green"}>
                        {r.active ? "Firing" : "Normal"}
                      </span>
                    </span>
                  ))}
                  {!rules.length && (
                    <p className="muted">
                      No rules yet. Set a threshold to track firing and recovery
                      events.
                    </p>
                  )}
                </div>
                <form className="inline-form" onSubmit={saveRule}>
                  <select
                    aria-label="Rule metric"
                    value={ruleMetric}
                    onChange={(e) => setRuleMetric(e.target.value)}
                  >
                    <option value="cpu">CPU</option>
                    <option value="memory">Memory</option>
                    <option value="disk">Disk</option>
                  </select>
                  <label htmlFor="threshold">Threshold %</label>
                  <input
                    id="threshold"
                    type="number"
                    min="0.1"
                    max="100"
                    step="0.1"
                    required
                    value={threshold}
                    onChange={(e) => setThreshold(Number(e.target.value))}
                  />
                  <button className="primary" disabled={busy}>
                    Save rule
                  </button>
                </form>
              </section>
            </>
          )}
          {(selected || page === "alerts") && (
            <section className="panel">
              <div className="panel-heading">
                <h2>Recent events</h2>
                <span className="muted">
                  Latest 100 {selected ? "host" : "workspace"} transitions
                </span>
              </div>
              {!visibleAlerts.length ? (
                <div className="empty">
                  <Bell size={32} />
                  <h3>No alert events</h3>
                  <p>Threshold breaches and recoveries will appear here.</p>
                </div>
              ) : (
                <div className="events">
                  {visibleAlerts.map((a) => (
                    <div className="event" key={a.id}>
                      <span
                        className={`event-icon ${a.state === "firing" ? "red" : "green"}`}
                      >
                        <Bell size={17} />
                      </span>
                      <div>
                        <strong>
                          {a.metric.toUpperCase()}{" "}
                          {a.state === "firing"
                            ? "threshold exceeded"
                            : "recovered"}
                        </strong>
                        <p>
                          {hosts.find((h) => h.id === a.host_id)?.name ||
                            a.host_id}{" "}
                          · {a.value.toFixed(1)}% / {a.threshold}% threshold
                        </p>
                      </div>
                      <span className="muted">{date(a.timestamp)}</span>
                    </div>
                  ))}
                </div>
              )}
            </section>
          )}
          <footer>
            CloudPulse <span>Real signals. Clear decisions.</span>
            <span>All times shown in your local timezone</span>
          </footer>
        </div>
      </main>
    </div>
  );
}
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
