import React, { useCallback, useEffect, useMemo, useState } from "react";
import { api, download, getToken, login, setToken } from "./api.js";

/* ------------------------------- primitives ------------------------------ */

const cx = (...a) => a.filter(Boolean).join(" ");

function Icon({ name, size = 18 }) {
  const paths = {
    overview: "M3 13h8V3H3v10zm10 8h8V11h-8v10zM3 21h8v-6H3v6zm10-12h8V3h-8v6z",
    blocks: "M4 4h7v7H4V4zm9 0h7v7h-7V4zM4 13h7v7H4v-7zm9 0h7v7h-7v-7z",
    servers: "M3 5h18v6H3V5zm0 8h18v6H3v-6zM6 7v2m0 6v2",
    containers: "M3 8l9-5 9 5-9 5-9-5zm0 5l9 5 9-5",
    ai: "M12 3v3m0 12v3M3 12h3m12 0h3M6 6l2 2m8 8l2 2m0-12l-2 2M8 16l-2 2M12 8a4 4 0 100 8 4 4 0 000-8z",
    monitor: "M3 4h18v12H3V4zm6 16h6m-3-4v4",
    logs: "M5 3h11l3 3v15H5V3zm3 6h8M8 12h8M8 15h5",
    security: "M12 3l8 3v6c0 4-3.5 7.5-8 9-4.5-1.5-8-5-8-9V6l8-3z",
    settings: "M12 8a4 4 0 100 8 4 4 0 000-8zM12 2v3m0 14v3M2 12h3m14 0h3M5 5l2 2m10 10l2 2m0-14l-2 2M7 17l-2 2",
    plus: "M12 5v14M5 12h14",
    play: "M8 5l11 7-11 7V5z",
    stop: "M6 6h12v12H6z",
    restart: "M4 12a8 8 0 1114 5.3M4 12V6m0 6h6",
    trash: "M4 7h16M9 7V4h6v3m-8 0l1 13h8l1-13",
    terminal: "M4 5h16v14H4V5zm3 4l3 3-3 3m5 0h4",
    download: "M12 3v12m0 0l-4-4m4 4l4-4M5 21h14",
    x: "M6 6l12 12M18 6L6 18",
  };
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d={paths[name] || ""} />
    </svg>
  );
}

function StatusDot({ status }) {
  return (
    <span className={cx("dot", `dot-${status}`)} title={status}>
      <span />
    </span>
  );
}

function Bar({ value = 0, max = 0, color, label, hint, format }) {
  const pct = max > 0 ? Math.min(100, Math.max(0, (value / max) * 100)) : value > 0 ? 100 : 0;
  const level = pct >= 90 ? "danger" : pct >= 70 ? "warn" : "ok";
  const fmt = format || ((v) => `${Math.round(v)}`);
  return (
    <div className="bar-block">
      <div className="bar-head">
        <span>{label}</span>
        <span className="bar-vals">
          {fmt(value)}
          {max > 0 ? <span className="muted"> / {fmt(max)}</span> : null}
        </span>
      </div>
      <div className="bar-track">
        <div className={cx("bar-fill", level)} style={{ width: `${pct}%`, background: color }} />
      </div>
      {hint && <div className="bar-hint muted">{hint}</div>}
    </div>
  );
}

function AreaChart({ points, color = "#5b8cff", height = 120 }) {
  if (!points || points.length < 2) return <div className="empty-chart muted">Собираем данные…</div>;
  const w = 600, h = height, pad = 8;
  const max = Math.max(...points, 1);
  const min = Math.min(...points, 0);
  const span = max - min || 1;
  const coords = points.map((v, i) => {
    const x = pad + (i / (points.length - 1)) * (w - pad * 2);
    const y = h - pad - ((v - min) / span) * (h - pad * 2);
    return [x, y];
  });
  const line = coords.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const area = `${line} L${w - pad},${h - pad} L${pad},${h - pad} Z`;
  const id = useMemo(() => "g" + Math.random().toString(36).slice(2), []);
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="area-chart" preserveAspectRatio="none">
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.45" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${id})`} />
      <path d={line} fill="none" stroke={color} strokeWidth="2.2" />
    </svg>
  );
}

function Modal({ title, subtitle, children, onClose, wide }) {
  return (
    <div className="modal-backdrop" onMouseDown={onClose}>
      <div className={cx("modal", wide && "wide")} onMouseDown={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <div>
            <h3>{title}</h3>
            {subtitle && <p className="muted small">{subtitle}</p>}
          </div>
          <button className="icon-btn" onClick={onClose}><Icon name="x" /></button>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
}

function usePolling(fn, interval = 5000, deps = []) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const load = useCallback(async () => {
    try {
      setData(await fn());
      setError(null);
    } catch (e) {
      setError(e.message);
    }
  }, deps);
  useEffect(() => {
    load();
    if (!interval) return;
    const pref = Number(localStorage.getItem("nexus_refresh"));
    const ms = pref > 0 ? pref * 1000 : interval;
    const t = setInterval(load, ms);
    return () => clearInterval(t);
  }, [load, interval]);
  return { data, error, reload: load };
}

const PRESET_FALLBACK = { name: "Custom", color: "#8b97b8" };

const ACCENTS = [
  { id: "blue", label: "Синий", color: "#5b8cff", color2: "#22d3ee" },
  { id: "violet", label: "Фиолетовый", color: "#8b5cf6", color2: "#ec4899" },
  { id: "green", label: "Изумруд", color: "#22c55e", color2: "#14b8a6" },
  { id: "orange", label: "Янтарь", color: "#f59e0b", color2: "#ef4444" },
];

function useLocalStorage(key, initial) {
  const [value, setValue] = useState(() => {
    try {
      const raw = localStorage.getItem(key);
      return raw === null ? initial : JSON.parse(raw);
    } catch {
      return initial;
    }
  });
  const set = useCallback((next) => {
    setValue((prev) => {
      const v = typeof next === "function" ? next(prev) : next;
      try { localStorage.setItem(key, JSON.stringify(v)); } catch { /* ignore */ }
      return v;
    });
  }, [key]);
  return [value, set];
}

function applyAccent(id) {
  const a = ACCENTS.find((x) => x.id === id) || ACCENTS[0];
  const root = document.documentElement.style;
  root.setProperty("--accent", a.color);
  root.setProperty("--accent-2", a.color2);
}

/* --------------------------------- login --------------------------------- */

function Login({ onLogin, notice }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await login(password);
      setToken(res.token);
      onLogin();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="login-wrap">
      <div className="login-glow" />
      <form className="login-card" onSubmit={submit}>
        <div className="brand big"><span className="brand-mark">N</span> NEXUS<span className="accent">CLOUD</span></div>
        <p className="muted">Панель управления распределённым кластером.</p>
        {notice && <div className="notice">{notice}</div>}
        <label>Пароль администратора
          <input type="password" placeholder="••••••••" value={password} onChange={(e) => setPassword(e.target.value)} autoFocus />
        </label>
        {error && <div className="error">{error}</div>}
        <button className="btn-primary" type="submit" disabled={busy || !password}>{busy ? "Входим…" : "Войти"}</button>
      </form>
    </div>
  );
}

/* -------------------------------- overview ------------------------------- */

function Overview() {
  const { data, error } = usePolling(() => api("/api/v1/overview"), 4000);
  if (error) return <div className="error">{error}</div>;
  if (!data) return <div className="skeleton-grid">{[...Array(4)].map((_, i) => <div className="skeleton" key={i} />)}</div>;
  const t = data.totals;
  const gb = (v) => `${(v / 1024).toFixed(1)} GB`;
  return (
    <div className="stack">
      <div className="kpi-grid">
        <div className="kpi"><div className="kpi-icon"><Icon name="blocks" /></div><div><div className="kpi-value">{data.blocks_online}<span className="muted">/{data.blocks_total}</span></div><div className="kpi-label">Блоки онлайн</div></div></div>
        <div className="kpi"><div className="kpi-icon"><Icon name="ai" /></div><div><div className="kpi-value">{t.cpu_physical.toFixed(1)}</div><div className="kpi-label">CPU физически · отдано {t.cpu_offered.toFixed(1)}</div></div></div>
        <div className="kpi"><div className="kpi-icon"><Icon name="monitor" /></div><div><div className="kpi-value">{gb(t.ram_physical)}</div><div className="kpi-label">RAM физически · отдано {gb(t.ram_offered)}</div></div></div>
        <div className="kpi"><div className="kpi-icon"><Icon name="servers" /></div><div><div className="kpi-value">{gb(t.disk_physical)}</div><div className="kpi-label">Диск (ФС)</div></div></div>
      </div>

      <div className="panel">
        <div className="panel-title">Загрузка мощностей кластера</div>
        <div className="bars-3">
          <Bar label="CPU" value={t.cpu_allocated} max={t.cpu_offered} format={(v) => `${v.toFixed(1)} яд`} />
          <Bar label="RAM" value={t.ram_allocated} max={t.ram_offered} format={(v) => gb(v)} />
          <Bar label="Disk" value={t.disk_allocated} max={t.disk_offered} format={(v) => gb(v)} />
        </div>
      </div>

      <div className="panel">
        <div className="panel-title">Блоки</div>
        <div className="mini-blocks">
          {data.blocks.length === 0 && <div className="muted">Пока нет подключённых блоков.</div>}
          {data.blocks.map((b) => (
            <div className="mini-block" key={b.id}>
              <div className="row between">
                <div className="row gap"><StatusDot status={b.status} /><strong>{b.name}</strong></div>
                <span className="muted small">{b.last_heartbeat ? new Date(b.last_heartbeat * 1000).toLocaleTimeString() : "—"}</span>
              </div>
              <Bar label="CPU" value={b.quotas.cpu.allocated} max={b.quotas.cpu.offered} format={(v) => `${v.toFixed(1)}/${b.quotas.cpu.offered.toFixed(1)}`} />
              <Bar label="RAM" value={b.quotas.ram.allocated} max={b.quotas.ram.offered} format={(v) => `${gb(v)} / ${gb(b.quotas.ram.offered)}`} />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ------------------------------- code server ----------------------------- */

function CodeServer() {
  const { data: blocks, error } = usePolling(() => api("/api/v1/blocks"), 5000);
  const [taskCmd, setTaskCmd] = useState("nproc && free -m");
  const [scope, setScope] = useState("all");
  const [cwd, setCwd] = useState("");
  const [timeoutS, setTimeoutS] = useState(60);
  const [running, setRunning] = useState(false);
  const [taskError, setTaskError] = useState(null);
  const [results, setResults] = useState(null);
  if (error) return <div className="error">{error}</div>;
  const online = (blocks || []).filter((b) => b.status === "ONLINE");
  const sum = (k, f) => online.reduce((a, b) => a + (b.quotas?.[k]?.[f] || 0), 0);
  const gb = (v) => `${(v / 1024).toFixed(1)} GB`;
  const url = `${window.location.origin}/`;

  async function runTask() {
    setRunning(true);
    setTaskError(null);
    setResults(null);
    try {
      const res = await api("/api/v1/cluster/exec", {
        method: "POST",
        body: {
          command: taskCmd,
          block_ids: scope === "all" ? null : [scope],
          cwd: cwd.trim() || null,
          timeout: Number(timeoutS) || 60,
        },
      });
      setResults(res.results || []);
    } catch (e) {
      setTaskError(e.message);
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="stack">
      <div className="panel">
        <div className="panel-title">Главный Code Server</div>
        <p className="muted">Интерфейс живёт здесь, на этом аккаунте. Остальные блоки дают мощность для задач.</p>
        <a className="btn-primary" href={url} target="_blank" rel="noreferrer">Открыть Code Server</a>
        <p className="muted small">Ссылка ведёт на реальный Code Server этого аккаунта (порт 45137).</p>
      </div>

      <div className="kpi-grid">
        <div className="kpi"><div className="kpi-icon"><Icon name="blocks" /></div><div><div className="kpi-value">{online.length}</div><div className="kpi-label">Блоков онлайн</div></div></div>
        <div className="kpi"><div className="kpi-icon"><Icon name="ai" /></div><div><div className="kpi-value">{sum("cpu", "physical").toFixed(1)}</div><div className="kpi-label">CPU суммарно (физически)</div></div></div>
        <div className="kpi"><div className="kpi-icon"><Icon name="monitor" /></div><div><div className="kpi-value">{gb(sum("ram", "physical"))}</div><div className="kpi-label">RAM суммарно (физически)</div></div></div>
        <div className="kpi"><div className="kpi-icon"><Icon name="servers" /></div><div><div className="kpi-value">{gb(sum("disk", "physical"))}</div><div className="kpi-label">Диск (ФС)</div></div></div>
      </div>

      <div className="panel">
        <div className="panel-title">Задачи на блоках</div>
        <p className="muted small">Команда выполняется параллельно на выбранных блоках. Это реально задействует их CPU/RAM.</p>
        <p className="muted small">В терминале главного Code Server доступна команда <code>nexus-run "..."</code>. Учти: <code>nproc</code> и <code>free</code> показывают хост, а реальные лимиты блока — из cgroup (в карточке блока).</p>
        <div className="task-form">
          <input value={taskCmd} onChange={(e) => setTaskCmd(e.target.value)} placeholder="npm install && npm test" />
          <select value={scope} onChange={(e) => setScope(e.target.value)}>
            <option value="all">Все блоки</option>
            {online.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
          </select>
          <input value={cwd} onChange={(e) => setCwd(e.target.value)} placeholder="папка (по умолчанию home)" />
          <input type="number" min="1" max="300" value={timeoutS} onChange={(e) => setTimeoutS(e.target.value)} title="Таймаут, сек" />
          <button className="btn-primary" onClick={runTask} disabled={running || !taskCmd.trim()}>{running ? "Выполняем…" : "Выполнить"}</button>
        </div>
        {taskError && <div className="error">{taskError}</div>}
        {(results || []).map((r) => (
          <div className="task-result" key={r.block_id}>
            <div className="row between">
              <strong>{r.block_name}</strong>
              <span className={cx("pill", r.ok ? "pill-ONLINE" : "pill-ERROR")}>
                {r.ok ? "OK" : "FAIL"} · {r.duration_ms != null ? `${r.duration_ms} ms` : "—"}{r.exit_code != null ? ` · exit ${r.exit_code}` : ""}
              </span>
            </div>
            {r.error && <div className="error">{r.error}</div>}
            <div className="console"><pre>{r.output || "(пусто)"}</pre></div>
          </div>
        ))}
      </div>

      <div className="panel">
        <div className="panel-title">Подключённые блоки</div>
        <div className="mini-blocks">
          {online.length === 0 && <div className="muted">Нет онлайн-блоков.</div>}
          {online.map((b) => (
            <div className="mini-block" key={b.id}>
              <div className="row between"><div className="row gap"><StatusDot status={b.status} /><strong>{b.name}</strong></div><span className="muted small">{b.last_heartbeat ? new Date(b.last_heartbeat * 1000).toLocaleTimeString() : "—"}</span></div>
              <div className="muted small">Физически: {b.quotas.cpu.physical.toFixed(1)} CPU · {Math.round(b.quotas.ram.physical)} MB RAM · {gb(b.quotas.disk.physical)} disk</div>
              <div className="muted small">Отдано: {b.quotas.cpu.offered.toFixed(1)} CPU · {Math.round(b.quotas.ram.offered)} MB RAM</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* --------------------------------- blocks -------------------------------- */

function ResourceForm({ block, onClose, onSaved }) {
  const offers = block.offers || {};
  const init = (kind) => ({ enabled: false, full: false, amount: "", reserved_for_host: 0, ...(offers[kind] || {}) });
  const [form, setForm] = useState({ cpu: init("cpu"), ram: init("ram"), disk: init("disk"), gpu: init("gpu") });
  const [error, setError] = useState(null);
  const update = (k, f, v) => setForm((s) => ({ ...s, [k]: { ...s[k], [f]: v } }));
  async function save() {
    setError(null);
    const payload = {};
    for (const k of ["cpu", "ram", "disk", "gpu"]) {
      const o = form[k];
      payload[k] = { enabled: !!o.enabled, full: !!o.full, amount: o.amount === "" ? null : Number(o.amount), reserved_for_host: Number(o.reserved_for_host || 0) };
    }
    try {
      await api(`/api/v1/blocks/${block.id}/resources`, { method: "PUT", body: { offers: payload } });
      onSaved();
      onClose();
    } catch (e) {
      setError(e.message);
    }
  }
  return (
    <Modal title={`Мощности блока — ${block.name}`} subtitle="Выбери, какие ресурсы этот блок отдаёт NEXUS. Ресурсы разных блоков не объединяются." onClose={onClose} wide>
      <div className="res-grid">
        {["cpu", "ram", "disk", "gpu"].map((k) => (
          <div className="res-card" key={k}>
            <div className="row between">
              <strong>{k.toUpperCase()}</strong>
              <label className="switch">
                <input type="checkbox" checked={form[k].enabled} onChange={(e) => update(k, "enabled", e.target.checked)} />
                <span />
              </label>
            </div>
            <div className="muted small">Физически: {block.quotas?.[k]?.physical ?? 0} · Свободно: {block.quotas?.[k]?.available ?? 0}</div>
            <label className="check-inline"><input type="checkbox" checked={form[k].full} onChange={(e) => update(k, "full", e.target.checked)} /> Отдать всё</label>
            <label>Лимит {form[k].full && <span className="muted">(всё)</span>}
              <input type="number" min="0" value={form[k].amount ?? ""} disabled={form[k].full} onChange={(e) => update(k, "amount", e.target.value)} />
            </label>
            <label>Резерв для хоста
              <input type="number" min="0" value={form[k].reserved_for_host} onChange={(e) => update(k, "reserved_for_host", e.target.value)} />
            </label>
          </div>
        ))}
      </div>
      {error && <div className="error">{error}</div>}
      <div className="actions"><button className="btn-primary" onClick={save}>Сохранить</button></div>
    </Modal>
  );
}

function PackageDownload({ compact = false }) {
  const [info, setInfo] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api("/api/v1/package/info").then(setInfo).catch((e) => setError(e.message));
  }, []);
  async function go() {
    setBusy(true);
    setError(null);
    try {
      await download("/api/v1/package/latest");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  const label = busy ? "Скачиваем…" : "Скачать установщик";
  if (compact) {
    return (
      <>
        <button className="btn-ghost" onClick={go} disabled={busy || info?.available === false} title={info?.name || "Последний собранный пакет"}>
          <Icon name="download" /> {label}
        </button>
        {error && <span className="error">{error}</span>}
      </>
    );
  }
  return (
    <div className="panel">
      <div className="panel-title">Установщик для второго сервера</div>
      {info?.available ? (
        <p className="muted small">{info.name} · {Math.round(info.size / 1024)} KB · обновлён {new Date(info.updated_at * 1000).toLocaleString()}</p>
      ) : (
        <p className="muted small">Пока нет собранного пакета.</p>
      )}
      <div className="row">
        <button className="btn-primary" onClick={go} disabled={busy || info?.available === false}><Icon name="download" /> {label}</button>
      </div>
      {error && <div className="error">{error}</div>}
      <p className="muted small">Скачай → загрузи на второй Code Server → распакуй → <code>bash deployment/install.sh</code>.</p>
    </div>
  );
}

function AddBlock({ onClose, onCreated }) {
  const [form, setForm] = useState({ name: "", ip: "", port: "", description: "" });
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const { data: cfg } = usePolling(() => api("/api/v1/settings"), 0);
  const masterUrl = cfg?.public_url || "https://<этот-master>";
  async function submit() {
    setError(null);
    try {
      const body = { name: form.name };
      if (form.ip) body.ip = form.ip;
      if (form.port) body.port = Number(form.port);
      if (form.description) body.description = form.description;
      setResult(await api("/api/v1/blocks", { method: "POST", body }));
      onCreated();
    } catch (e) {
      setError(e.message);
    }
  }
  if (result) {
    return (
      <Modal title="Токен подключения блока" onClose={onClose}>
        <p>Одноразовый токен. На сервере блока выполни:</p>
        <pre className="code">nexus up block --master {masterUrl} --token {result.pairing_token}</pre>
        <p className="muted small">Токен одноразовый — после подключения блок появится в панели.</p>
      </Modal>
    );
  }
  return (
    <Modal title="Добавить блок" subtitle="Создай токен и подключи новый сервер как блок." onClose={onClose}>
      <PackageDownload />
      <div className="form-col">
        <label>Название<input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="block-eu-1" /></label>
        <label>IP (необязательно)<input value={form.ip} onChange={(e) => setForm({ ...form, ip: e.target.value })} placeholder="203.0.113.10" /></label>
        <label>Порт (необязательно)<input value={form.port} onChange={(e) => setForm({ ...form, port: e.target.value })} placeholder="8787" /></label>
        <label>Описание<input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></label>
      </div>
      {error && <div className="error">{error}</div>}
      <div className="actions"><button className="btn-primary" onClick={submit} disabled={!form.name}>Создать токен</button></div>
    </Modal>
  );
}

function Blocks() {
  const { data: blocks, error, reload } = usePolling(() => api("/api/v1/blocks"), 4000);
  const [showAdd, setShowAdd] = useState(false);
  const [resBlock, setResBlock] = useState(null);
  const [notice, setNotice] = useState(null);
  const act = async (id, a) => { try { await api(`/api/v1/blocks/${id}/${a}`, { method: "POST" }); reload(); } catch (e) { setNotice(e.message); } };
  const remove = async (id) => { if (!confirm("Удалить блок?")) return; try { await api(`/api/v1/blocks/${id}`, { method: "DELETE" }); reload(); } catch (e) { setNotice(e.message); } };
  const revoke = async (id) => { try { const r = await api(`/api/v1/blocks/${id}/revoke`, { method: "POST" }); setNotice(`Новый секрет блока: ${r.block_secret}`); reload(); } catch (e) { setNotice(e.message); } };
  return (
    <div className="stack">
      <div className="row between">
        <div><h2>Блоки</h2><p className="muted small">Серверы, которые отдают мощности кластеру.</p></div>
        <div className="row gap">
          <PackageDownload compact />
          <button className="btn-primary" onClick={() => setShowAdd(true)}><Icon name="plus" /> Добавить блок</button>
        </div>
      </div>
      {notice && <div className="notice" onClick={() => setNotice(null)}>{notice}</div>}
      {error && <div className="error">{error}</div>}
      <div className="block-grid">
        {(blocks || []).map((b) => (
          <div className="block-card" key={b.id}>
            <div className="row between">
              <div className="row gap"><StatusDot status={b.status} /><strong>{b.name}</strong></div>
              <span className={cx("pill", `pill-${b.status}`)}>{b.status}</span>
            </div>
            <div className="muted small mono">{b.ip || "—"}{b.port ? `:${b.port}` : ""} · {b.id}</div>
            <div className="muted small">
              Физически: {b.quotas.cpu.physical.toFixed(1)} CPU · {Math.round(b.quotas.ram.physical)} MB RAM · {Math.round(b.quotas.disk.physical / 1024)} GB disk{b.quotas.gpu.physical ? ` · GPU ${b.quotas.gpu.physical}` : ""}
            </div>
            <div className="muted small">Отдано кластеру: {b.quotas.cpu.offered.toFixed(1)} CPU · {Math.round(b.quotas.ram.offered)} MB RAM · {Math.round(b.quotas.disk.offered / 1024)} GB</div>
            <div className="bars-2">
              <Bar label="CPU занято/отдано" value={b.quotas.cpu.allocated} max={b.quotas.cpu.offered} format={(v) => `${v.toFixed(1)}/${b.quotas.cpu.offered.toFixed(1)}`} />
              <Bar label="RAM занято/отдано" value={b.quotas.ram.allocated} max={b.quotas.ram.offered} format={(v) => `${Math.round(v)}/${Math.round(b.quotas.ram.offered)} MB`} />
              <Bar label="Disk занято/отдано" value={b.quotas.disk.allocated} max={b.quotas.disk.offered} format={(v) => `${Math.round(v / 1024)}/${Math.round(b.quotas.disk.offered / 1024)} GB`} />
              <Bar label="GPU занято/отдано" value={b.quotas.gpu.allocated} max={b.quotas.gpu.offered} />
            </div>
            <div className="muted small">{b.app_count} серверов · beat {b.last_heartbeat ? new Date(b.last_heartbeat * 1000).toLocaleTimeString() : "—"}</div>
            <div className="caps-row">
              {Object.entries(CAP_LABELS).map(([k, label]) => (
                <span key={k} className={cx("cap", b.capabilities?.[k] ? "on" : "off")} title={b.capabilities?.[k] || "не установлено"}>
                  {label}{b.capabilities?.[k] ? ` ${b.capabilities[k]}` : ""}
                </span>
              ))}
            </div>
            <div className="card-actions">
              <button className="btn-ghost sm" onClick={() => setResBlock(b)}>Мощности</button>
              {b.status === "DISABLED"
                ? <button className="btn-ghost sm" onClick={() => act(b.id, "enable")}>Включить</button>
                : <button className="btn-ghost sm" onClick={() => act(b.id, "disable")}>Отключить</button>}
              <button className="btn-ghost sm" onClick={() => act(b.id, "restart-agent")}>Рестарт агента</button>
              <button className="btn-ghost sm" onClick={() => revoke(b.id)}>Отозвать</button>
              <button className="btn-ghost sm danger" onClick={() => remove(b.id)}><Icon name="trash" size={15} /></button>
            </div>
          </div>
        ))}
        {(!blocks || blocks.length === 0) && <div className="empty">Нет блоков. Нажми «Добавить блок».</div>}
      </div>
      {showAdd && <AddBlock onClose={() => setShowAdd(false)} onCreated={reload} />}
      {resBlock && <ResourceForm block={resBlock} onClose={() => setResBlock(null)} onSaved={reload} />}
    </div>
  );
}

/* -------------------------------- servers -------------------------------- */

function presetOf(presets, id) {
  return (presets || []).find((p) => p.id === id) || PRESET_FALLBACK;
}

function portUrl(port) {
  const { origin, pathname, protocol, hostname } = window.location;
  const idx = pathname.indexOf("/proxy/");
  if (idx >= 0) return `${origin}${pathname.slice(0, idx)}/proxy/${port}/`;
  return `${protocol}//${hostname}:${port}/`;
}

const CAP_LABELS = {
  docker: "Docker",
  python: "Python",
  node: "Node",
  npm: "npm",
  git: "Git",
  "code-server": "VS Code",
  opencode: "OpenCode",
  gpu: "GPU",
};

function presetNeeds(preset) {
  if (!preset) return [];
  if (preset.kind === "docker") return ["docker"];
  const c = (preset.command || "").toLowerCase();
  const need = [];
  if (/(^|[\s;|&])python3?(\s|$)/.test(c)) need.push("python");
  if (/(^|[\s;|&])node(\s|$)/.test(c)) need.push("node");
  if (/(^|[\s;|&])np[mnx](\s|$)/.test(c)) need.push("npm");
  if (c.includes("code-server")) need.push("code-server");
  if (/(^|[\s;|&])opencode(\s|$)/.test(c)) need.push("opencode");
  return need;
}

function ServerCard({ app, presets, blocks, onAction, onLogs, onDelete, onOpen }) {
  const preset = presetOf(presets, app.spec?.preset);
  const cpuCores = (app.cpu_percent || 0) / 100;
  const cpuLimit = app.spec?.cpu_limit || 0;
  const ram = app.ram_mb || 0;
  const ramLimit = app.spec?.ram_limit_mb || 0;
  const running = app.status === "RUNNING";
  const blockName = (blocks || []).find((b) => b.id === app.block_id)?.name || app.block_id || "—";
  return (
    <div className={cx("server-card", `server-${app.status}`)} style={{ "--accent": preset.color }}>
      <div className="server-head">
        <div className="server-badge" style={{ background: `${preset.color}22`, color: preset.color }}>{preset.name.slice(0, 2).toUpperCase()}</div>
        <div className="grow">
          <div className="row between"><strong>{app.name}</strong><span className={cx("pill", `pill-${app.status}`)}>{app.status}</span></div>
          <div className="muted small">{preset.name} · {app.kind} · {blockName}</div>
        </div>
      </div>
      <div className="server-bars">
        <Bar label="CPU" value={cpuCores} max={cpuLimit || 0} color={preset.color} format={(v) => `${v.toFixed(2)}${cpuLimit ? ` / ${cpuLimit} яд` : " яд"}`} />
        <Bar label="RAM" value={ram} max={ramLimit || 0} format={(v) => `${Math.round(v)}${ramLimit ? ` / ${Math.round(ramLimit)} MB` : " MB"}`} />
      </div>
      {running && (app.spec?.ports || []).length > 0 && (
        <div className="port-links">
          {app.spec.ports.map((p) => (
            <a key={p} className="btn-ghost sm" href={portUrl(p)} target="_blank" rel="noreferrer">Открыть :{p}</a>
          ))}
        </div>
      )}
      <div className="card-actions">
        <button className="btn-ghost sm" onClick={() => onOpen(app.id)}><Icon name="terminal" size={14} /> Панель</button>
        <button className="btn-ghost sm" onClick={() => onAction(app.id, "start")} disabled={running}><Icon name="play" size={14} /> Старт</button>
        <button className="btn-ghost sm" onClick={() => onAction(app.id, "stop")} disabled={!running}><Icon name="stop" size={14} /> Стоп</button>
        <button className="btn-ghost sm" onClick={() => onAction(app.id, "restart")}><Icon name="restart" size={14} /> Рестарт</button>
        <button className="btn-ghost sm" onClick={() => onLogs(app)}><Icon name="terminal" size={14} /> Логи</button>
        <button className="btn-ghost sm danger" onClick={() => onDelete(app.id)}><Icon name="trash" size={14} /></button>
      </div>
    </div>
  );
}

function CreateServer({ presets, blocks, onClose, onCreated }) {
  const [presetId, setPresetId] = useState(presets?.[0]?.id || "custom");
  const [name, setName] = useState("");
  const [blockId, setBlockId] = useState("");
  const [cpu, setCpu] = useState(1);
  const [ram, setRam] = useState(512);
  const [disk, setDisk] = useState(2048);
  const [ports, setPorts] = useState("");
  const [command, setCommand] = useState("");
  const [image, setImage] = useState("");
  const [envText, setEnvText] = useState("");
  const [files, setFiles] = useState([]);
  const [startNow, setStartNow] = useState(true);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const preset = presetOf(presets, presetId);
  const block = (blocks || []).find((b) => b.id === blockId);
  const totals = (blocks || []).reduce(
    (a, b) => ({
      cpu: a.cpu + (b.quotas.cpu.available || 0),
      ram: a.ram + (b.quotas.ram.available || 0),
      disk: a.disk + (b.quotas.disk.available || 0),
    }),
    { cpu: 0, ram: 0, disk: 0 },
  );
  const avail = block
    ? { cpu: block.quotas.cpu.available || 0, ram: block.quotas.ram.available || 0, disk: block.quotas.disk.available || 0 }
    : totals;
  const availKey = (blocks || []).map((b) => `${b.id}:${b.quotas.cpu.available}:${b.quotas.ram.available}`).join("|");
  const noCapacity = avail.cpu < 0.5 || avail.ram < 128;
  const targetCaps = block
    ? block.capabilities || {}
    : (blocks || []).reduce((acc, b) => {
        for (const [k, v] of Object.entries(b.capabilities || {})) if (!acc[k]) acc[k] = v;
        return acc;
      }, {});
  const needs = presetNeeds(preset);
  const missing = needs.filter((k) => !targetCaps[k]);
  const blocked = noCapacity || missing.length > 0 || !blocks || blocks.length === 0;

  useEffect(() => {
    const p = presetOf(presets, presetId);
    setCpu(Math.min(p.cpu, Math.max(avail.cpu, 0.5)));
    setRam(Math.min(p.ram_mb, Math.max(avail.ram, 128)));
    setDisk(Math.min(p.disk_mb, Math.max(avail.disk, 512)));
    setPorts((p.ports || []).join(","));
    setCommand(p.command || "");
    setImage(p.image || "");
    setEnvText(Object.entries(p.env || {}).map(([k, v]) => `${k}=${v}`).join("\n"));
    setName((cur) => cur || p.name);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [presetId, blockId, availKey]);

  async function submit() {
    setError(null);
    setBusy(true);
    const env = {};
    envText.split("\n").forEach((line) => {
      const i = line.indexOf("=");
      if (i > 0) env[line.slice(0, i).trim()] = line.slice(i + 1).trim();
    });
    const spec = {
      name: name || preset.name,
      kind: preset.kind,
      preset: presetId,
      command: command,
      image: preset.kind === "docker" ? image : null,
      cpu_limit: Number(cpu) || null,
      ram_limit_mb: Number(ram) || null,
      disk_limit_mb: Number(disk) || null,
      ports: ports ? ports.split(",").map((p) => Number(p.trim())).filter(Boolean) : [],
      block_id: blockId || null,
      env,
    };
    const uploadFirst = files.length > 0;
    try {
      const res = await api("/api/v1/apps", {
        method: "POST",
        body: { spec, auto_place: !blockId, start: uploadFirst ? false : startNow },
      });
      if (uploadFirst) {
        for (const file of files) {
          const content = await file.text();
          const up = await api(`/api/v1/apps/${res.app_id}/files/content`, {
            method: "PUT",
            body: { path: file.name, content },
          });
          if (!up.ok) throw new Error(`Не удалось загрузить ${file.name}: ${up.error}`);
        }
        if (startNow) await api(`/api/v1/apps/${res.app_id}/start`, { method: "POST" });
      }
      onCreated();
      onClose();
    } catch (e) {
      setError(e.message);
      onCreated?.();
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="Создать сервер" subtitle="Лимиты берутся из реально свободных мощностей блоков." onClose={onClose} wide>
      {(!blocks || blocks.length === 0) && (
        <div className="notice">Нет подключённых блоков. Сначала добавь блок в разделе «Блоки».</div>
      )}
      {blocks && blocks.length > 0 && (
        <div className="capacity">
          <span>Свободно {block ? "в блоке" : "в кластере"}:</span>
          <strong>{avail.cpu.toFixed(1)} CPU</strong>
          <strong>{Math.round(avail.ram)} MB RAM</strong>
          <strong>{Math.round(avail.disk)} MB disk</strong>
        </div>
      )}
      <div className="preset-grid">
        {(presets || []).map((p) => {
          const miss = presetNeeds(p).filter((k) => !targetCaps[k]);
          const disabled = miss.length > 0;
          return (
            <button
              key={p.id}
              className={cx("preset", presetId === p.id && "active", disabled && "preset-disabled")}
              style={{ "--accent": p.color }}
              onClick={() => setPresetId(p.id)}
              disabled={disabled}
              title={disabled ? `Недоступно: нужно ${miss.map((k) => CAP_LABELS[k] || k).join(", ")}` : p.description}
            >
              <span className="preset-badge" style={{ background: `${p.color}22`, color: p.color }}>{p.name.slice(0, 2).toUpperCase()}</span>
              <span className="preset-name">{p.name}</span>
              <span className="muted small">{p.category}</span>
              {disabled && <span className="preset-missing">нет {miss.map((k) => CAP_LABELS[k] || k).join(", ")}</span>}
            </button>
          );
        })}
      </div>

      <div className="create-grid">
        <div className="form-col">
          <label>Название сервера<input value={name} onChange={(e) => setName(e.target.value)} placeholder={preset.name} /></label>
          <label>Блок
            <select value={blockId} onChange={(e) => setBlockId(e.target.value)}>
              <option value="">Авто-выбор (планировщик)</option>
              {(blocks || []).map((b) => <option key={b.id} value={b.id}>{b.name} — CPU {b.quotas.cpu.available.toFixed(1)}, RAM {Math.round(b.quotas.ram.available)}MB</option>)}
            </select>
          </label>
          {block && (
            <>
              <div className="caps-row">
                {Object.entries(CAP_LABELS).map(([k, label]) => (
                  <span key={k} className={cx("cap", block.capabilities?.[k] ? "on" : "off")} title={block.capabilities?.[k] || "не установлено"}>
                    {label}{block.capabilities?.[k] ? ` ${block.capabilities[k]}` : ""}
                  </span>
                ))}
              </div>
              <div className="muted small">Свободно на блоке: {block.quotas.cpu.available.toFixed(1)} CPU · {Math.round(block.quotas.ram.available)} MB RAM · {Math.round(block.quotas.disk.available / 1024)} GB disk</div>
            </>
          )}
          {preset.kind === "process" ? (
            <label>Команда<input value={command} onChange={(e) => setCommand(e.target.value)} placeholder="node index.js" /></label>
          ) : (
            <label>Docker образ<input value={image} onChange={(e) => setImage(e.target.value)} placeholder="nginx:alpine" /></label>
          )}
          <label>Порты (через запятую)<input value={ports} onChange={(e) => setPorts(e.target.value)} placeholder="3000" /></label>
          <label>Переменные окружения (KEY=VALUE, по строке)
            <textarea className="env-input" rows="3" value={envText} onChange={(e) => setEnvText(e.target.value)} placeholder={"NODE_ENV=production\nTOKEN=..."} />
          </label>
          <label>Файлы проекта (опционально)
            <input type="file" multiple onChange={(e) => setFiles(Array.from(e.target.files || []))} />
          </label>
          {files.length > 0 && (
            <p className="muted small">Загрузим: {files.map((f) => f.name).join(", ")}</p>
          )}
        </div>

        <div className="form-col">
          <div className="slider-field">
            <div className="row between"><span>CPU (ядра)</span><strong>{Number(cpu).toFixed(1)}</strong></div>
            <input type="range" min="0.5" max={Math.max(avail.cpu, 0.5)} step="0.5" value={cpu} onChange={(e) => setCpu(e.target.value)} />
            <div className="muted small">Доступно: {avail.cpu.toFixed(1)} ядер</div>
          </div>
          <div className="slider-field">
            <div className="row between"><span>RAM (MB)</span><strong>{Math.round(Number(ram))}</strong></div>
            <input type="range" min="128" max={Math.max(avail.ram, 128)} step="128" value={ram} onChange={(e) => setRam(e.target.value)} />
            <div className="muted small">Доступно: {Math.round(avail.ram)} MB</div>
          </div>
          <div className="slider-field">
            <div className="row between"><span>Disk (MB)</span><strong>{Math.round(Number(disk))}</strong></div>
            <input type="range" min="512" max={Math.max(avail.disk, 512)} step="512" value={disk} onChange={(e) => setDisk(e.target.value)} />
            <div className="muted small">Доступно: {Math.round(avail.disk)} MB</div>
          </div>
          <label className="check-inline"><input type="checkbox" checked={startNow} onChange={(e) => setStartNow(e.target.checked)} /> Запустить сразу</label>
          <p className="muted small">Если выключить — сервер создастся остановленным, закинешь файлы и нажмёшь «Старт».</p>
        </div>
      </div>
      {preset.description && <p className="muted small">{preset.description}</p>}
      {missing.length > 0 && (
        <div className="error">
          Этому пресету нужно: {missing.map((k) => CAP_LABELS[k] || k).join(", ")}.
          {" "}{block ? "На выбранном блоке этого нет." : "Ни на одном подключённом блоке этого нет."}
          {" "}Выбери другой пресет/блок или поставь нужный рантайм на блоке.
        </div>
      )}
      {noCapacity && blocks && blocks.length > 0 && <div className="error">Недостаточно свободных ресурсов. Освободи мощности на блоках.</div>}
      {error && <div className="error">{error}</div>}
      <div className="actions">
        <button className="btn-ghost" onClick={onClose}>Отмена</button>
        <button className="btn-primary" onClick={submit} disabled={busy || blocked}>{busy ? "Создаём…" : "Создать и запустить"}</button>
      </div>
    </Modal>
  );
}

function FileManager({ appId }) {
  const [path, setPath] = useState("");
  const [entries, setEntries] = useState([]);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [editor, setEditor] = useState(null);
  const join = (a, b) => (a ? `${a}/${b}` : b);

  const load = useCallback(async (p) => {
    setBusy(true);
    setError(null);
    try {
      const r = await api(`/api/v1/apps/${appId}/files?path=${encodeURIComponent(p)}`);
      if (!r.ok) throw new Error(r.error);
      setEntries(r.entries || []);
      setPath(r.path || "");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }, [appId]);

  useEffect(() => { load(""); }, [load]);

  async function open(entry) {
    if (entry.type === "dir") return load(join(path, entry.name));
    setBusy(true);
    setError(null);
    try {
      const r = await api(`/api/v1/apps/${appId}/files/content?path=${encodeURIComponent(join(path, entry.name))}`);
      if (!r.ok) throw new Error(r.error);
      setEditor(r);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const r = await api(`/api/v1/apps/${appId}/files/content`, { method: "PUT", body: { path: editor.path, content: editor.content } });
      if (!r.ok) throw new Error(r.error);
      setEditor(null);
      load(path);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function remove(entry) {
    if (!confirm(`Удалить ${entry.name}?`)) return;
    try {
      const r = await api(`/api/v1/apps/${appId}/files?path=${encodeURIComponent(join(path, entry.name))}`, { method: "DELETE" });
      if (!r.ok) throw new Error(r.error);
      load(path);
    } catch (e) {
      setError(e.message);
    }
  }

  async function mkdir() {
    const name = prompt("Имя новой папки");
    if (!name) return;
    try {
      const r = await api(`/api/v1/apps/${appId}/files/mkdir`, { method: "POST", body: { path: join(path, name) } });
      if (!r.ok) throw new Error(r.error);
      load(path);
    } catch (e) {
      setError(e.message);
    }
  }

  async function newFile() {
    const name = prompt("Имя нового файла");
    if (!name) return;
    setEditor({ path: join(path, name), content: "", binary: false, size: 0 });
  }

  async function upload(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const content = await file.text();
      const r = await api(`/api/v1/apps/${appId}/files/content`, { method: "PUT", body: { path: join(path, file.name), content } });
      if (!r.ok) throw new Error(r.error);
      load(path);
    } catch (err) {
      setError(err.message);
    } finally {
      e.target.value = "";
    }
  }

  const crumbs = path ? path.split("/") : [];
  const fmtSize = (n) => (n > 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} MB` : n > 1024 ? `${(n / 1024).toFixed(1)} KB` : `${n} B`);

  if (editor) {
    return (
      <div className="filemgr">
        <div className="filebar">
          <button className="btn-ghost sm" onClick={() => setEditor(null)}>← Назад</button>
          <span className="mono small grow">{editor.path}</span>
          {!editor.binary && <button className="btn-primary sm" onClick={save} disabled={busy}>Сохранить</button>}
        </div>
        {error && <div className="error">{error}</div>}
        {editor.binary ? (
          <div className="empty">Бинарный файл — редактирование недоступно.</div>
        ) : (
          <textarea className="file-editor" value={editor.content} onChange={(e) => setEditor({ ...editor, content: e.target.value })} spellCheck={false} />
        )}
      </div>
    );
  }

  return (
    <div className="filemgr">
      <div className="filebar">
        <div className="crumbs">
          <button className="crumb" onClick={() => load("")}>/{appId ? "" : ""}</button>
          {crumbs.map((c, i) => (
            <button key={i} className="crumb" onClick={() => load(crumbs.slice(0, i + 1).join("/"))}>{c}/</button>
          ))}
        </div>
        <div className="row gap">
          <button className="btn-ghost sm" onClick={newFile}>Файл</button>
          <button className="btn-ghost sm" onClick={mkdir}>Папка</button>
          <label className="btn-ghost sm upload">Загрузить<input type="file" onChange={upload} hidden /></label>
        </div>
      </div>
      {error && <div className="error">{error}</div>}
      <div className="file-list">
        {busy && <div className="muted small">Загрузка…</div>}
        {!busy && entries.length === 0 && <div className="empty">Папка пуста.</div>}
        {entries.map((e) => (
          <div className="file-row" key={e.name}>
            <button className="file-name" onClick={() => open(e)}>
              <span className={cx("file-icon", e.type)}>{e.type === "dir" ? "DIR" : "FILE"}</span>
              {e.name}
            </button>
            <span className="muted small">{e.type === "file" ? fmtSize(e.size) : "—"}</span>
            <span className="muted small">{new Date(e.mtime * 1000).toLocaleString()}</span>
            <button className="icon-btn" onClick={() => remove(e)}><Icon name="trash" size={15} /></button>
          </div>
        ))}
      </div>
    </div>
  );
}

function Console({ appId }) {
  const [logs, setLogs] = useState("");
  const [extra, setExtra] = useState([]);
  const [cmd, setCmd] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const r = await api(`/api/v1/apps/${appId}/logs`);
        if (alive) setLogs(r.logs || "");
      } catch { /* ignore */ }
    };
    load();
    const t = setInterval(load, 3000);
    return () => { alive = false; clearInterval(t); };
  }, [appId]);

  async function run() {
    if (!cmd.trim() || busy) return;
    const command = cmd;
    setCmd("");
    setBusy(true);
    setExtra((x) => [...x, `$ ${command}`]);
    try {
      const r = await api(`/api/v1/apps/${appId}/exec`, { method: "POST", body: { command } });
      setExtra((x) => [...x, r.output || r.error || `(exit ${r.exit_code})`]);
    } catch (e) {
      setExtra((x) => [...x, `Ошибка: ${e.message}`]);
    } finally {
      setBusy(false);
    }
  }

  const text = logs + (extra.length ? `\n\n--- команды ---\n${extra.join("\n")}` : "");
  return (
    <div className="filemgr">
      <div className="console console-tall"><pre>{text || "(пусто)"}</pre></div>
      <div className="row gap console-input">
        <input value={cmd} onChange={(e) => setCmd(e.target.value)} onKeyDown={(e) => e.key === "Enter" && run()} placeholder="ls -la / node -v / npm install" className="mono" />
        <button className="btn-primary" onClick={run} disabled={busy}>{busy ? "…" : "Выполнить"}</button>
      </div>
      <p className="muted small">Команды выполняются в папке сервера на блоке.</p>
    </div>
  );
}

function ServerSettings({ app, onSaved }) {
  const [form, setForm] = useState(null);
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!app) return;
    setForm({
      name: app.spec?.name || app.name,
      command: app.spec?.command || "",
      image: app.spec?.image || "",
      ports: (app.spec?.ports || []).join(","),
      env: Object.entries(app.spec?.env || {}).map(([k, v]) => `${k}=${v}`).join("\n"),
      cpu_limit: app.spec?.cpu_limit || 1,
      ram_limit_mb: app.spec?.ram_limit_mb || 512,
      disk_limit_mb: app.spec?.disk_limit_mb || 2048,
      restart: false,
    });
  }, [app?.id]);

  if (!form) return <div className="muted">Загрузка…</div>;
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  async function save() {
    setBusy(true);
    setMsg(null);
    const env = {};
    form.env.split("\n").forEach((line) => {
      const i = line.indexOf("=");
      if (i > 0) env[line.slice(0, i).trim()] = line.slice(i + 1).trim();
    });
    try {
      await api(`/api/v1/apps/${app.id}`, {
        method: "PATCH",
        body: {
          name: form.name,
          command: form.command,
          image: form.image || null,
          ports: form.ports ? form.ports.split(",").map((p) => Number(p.trim())).filter(Boolean) : [],
          env,
          cpu_limit: Number(form.cpu_limit) || null,
          ram_limit_mb: Number(form.ram_limit_mb) || null,
          disk_limit_mb: Number(form.disk_limit_mb) || null,
          restart: form.restart,
        },
      });
      setMsg(form.restart ? "Сохранено и перезапущено." : "Сохранено. Изменения применятся после рестарта.");
      onSaved?.();
    } catch (e) {
      setMsg(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack">
      <div className="create-grid">
        <div className="form-col">
          <label>Название<input value={form.name} onChange={(e) => set("name", e.target.value)} /></label>
          <label>Команда<input value={form.command} onChange={(e) => set("command", e.target.value)} className="mono" /></label>
          <label>Docker образ<input value={form.image} onChange={(e) => set("image", e.target.value)} className="mono" /></label>
          <label>Порты<input value={form.ports} onChange={(e) => set("ports", e.target.value)} /></label>
        </div>
        <div className="form-col">
          <label>CPU (ядра)<input type="number" step="0.5" min="0.5" value={form.cpu_limit} onChange={(e) => set("cpu_limit", e.target.value)} /></label>
          <label>RAM (MB)<input type="number" step="128" min="128" value={form.ram_limit_mb} onChange={(e) => set("ram_limit_mb", e.target.value)} /></label>
          <label>Disk (MB)<input type="number" step="512" min="512" value={form.disk_limit_mb} onChange={(e) => set("disk_limit_mb", e.target.value)} /></label>
          <label className="check-inline"><input type="checkbox" checked={form.restart} onChange={(e) => set("restart", e.target.checked)} /> Перезапустить после сохранения</label>
        </div>
      </div>
      <label>Переменные окружения (KEY=VALUE)
        <textarea className="env-input" rows="4" value={form.env} onChange={(e) => set("env", e.target.value)} />
      </label>
      {msg && <div className="notice" onClick={() => setMsg(null)}>{msg}</div>}
      <div className="actions"><button className="btn-primary" onClick={save} disabled={busy}>{busy ? "Сохраняем…" : "Сохранить"}</button></div>
    </div>
  );
}

function ServerDetail({ appId, onClose, onChanged }) {
  const { data: app, reload } = usePolling(() => api(`/api/v1/apps/${appId}`), 3000);
  const { data: presets } = usePolling(() => api("/api/v1/presets"), 0);
  const { data: blocks } = usePolling(() => api("/api/v1/blocks"), 8000);
  const [tab, setTab] = useState("overview");
  const preset = presetOf(presets, app?.spec?.preset);
  const blockName = (blocks || []).find((b) => b.id === app?.block_id)?.name || app?.block_id || "—";

  async function act(a) {
    try {
      await api(`/api/v1/apps/${appId}/${a}`, { method: "POST" });
      reload();
      onChanged?.();
    } catch (e) {
      alert(e.message);
    }
  }
  async function del() {
    if (!confirm("Удалить сервер?")) return;
    try {
      await api(`/api/v1/apps/${appId}`, { method: "DELETE" });
      onClose();
      onChanged?.();
    } catch (e) {
      alert(e.message);
    }
  }

  return (
    <Modal title={app?.name || "Сервер"} subtitle={app ? `${preset.name} · ${blockName} · ${app.status}` : "Загрузка…"} onClose={onClose} wide>
      <div className="tabs">
        {[["overview", "Обзор"], ["files", "Файлы"], ["console", "Консоль"], ["settings", "Настройки"]].map(([k, label]) => (
          <button key={k} className={cx("tab", tab === k && "active")} onClick={() => setTab(k)}>{label}</button>
        ))}
      </div>
      {!app && <div className="skeleton" />}
      {app && tab === "overview" && (
        <div className="stack">
          <div className="row between">
            <div className="row gap">
              <span className="server-badge" style={{ background: `${preset.color}22`, color: preset.color }}>{preset.name.slice(0, 2).toUpperCase()}</span>
              <div><strong>{app.name}</strong><div className="muted small">{preset.name} · {app.kind}</div></div>
            </div>
            <span className={cx("pill", `pill-${app.status}`)}>{app.status}</span>
          </div>
          <div className="bars-2">
            <Bar label="CPU" value={(app.cpu_percent || 0) / 100} max={app.spec?.cpu_limit || 0} color={preset.color} format={(v) => `${v.toFixed(2)} / ${app.spec?.cpu_limit || 0} яд`} />
            <Bar label="RAM" value={app.ram_mb || 0} max={app.spec?.ram_limit_mb || 0} format={(v) => `${Math.round(v)} / ${Math.round(app.spec?.ram_limit_mb || 0)} MB`} />
          </div>
          <div className="kv"><span className="muted">Блок</span><strong>{blockName}</strong></div>
          <div className="kv"><span className="muted">PID</span><strong>{app.pid || "—"}</strong></div>
          <div className="kv"><span className="muted">Порты</span><strong>
            {(app.spec?.ports || []).length === 0 && "—"}
            {(app.spec?.ports || []).map((p, i) => (
              <span key={p}>{i > 0 ? ", " : ""}<a href={portUrl(p)} target="_blank" rel="noreferrer">{p}</a></span>
            ))}
          </strong></div>
          <div className="kv"><span className="muted">Команда</span><strong className="mono small">{app.spec?.command || app.spec?.image || "—"}</strong></div>
          {Object.keys(app.spec?.env || {}).length > 0 && (
            <div className="kv"><span className="muted">Env</span><strong className="mono small">{Object.keys(app.spec.env).join(", ")}</strong></div>
          )}
          <div className="card-actions">
            <button className="btn-ghost sm" onClick={() => act("start")} disabled={app.status === "RUNNING"}><Icon name="play" size={14} /> Старт</button>
            <button className="btn-ghost sm" onClick={() => act("stop")} disabled={app.status !== "RUNNING"}><Icon name="stop" size={14} /> Стоп</button>
            <button className="btn-ghost sm" onClick={() => act("restart")}><Icon name="restart" size={14} /> Рестарт</button>
            <button className="btn-ghost sm danger" onClick={del}><Icon name="trash" size={14} /> Удалить</button>
          </div>
        </div>
      )}
      {app && tab === "files" && <FileManager appId={appId} />}
      {app && tab === "console" && <Console appId={appId} />}
      {app && tab === "settings" && <ServerSettings app={app} onSaved={() => { reload(); onChanged?.(); }} />}
    </Modal>
  );
}

function Servers({ dockerOnly = false }) {
  const { data: apps, error, reload } = usePolling(() => api("/api/v1/apps"), 4000);
  const { data: blocks } = usePolling(() => api("/api/v1/blocks"), 8000);
  const { data: presets } = usePolling(() => api("/api/v1/presets"), 0);
  const [show, setShow] = useState(false);
  const [logs, setLogs] = useState(null);
  const [openId, setOpenId] = useState(null);
  const [notice, setNotice] = useState(null);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const list = (apps || []).filter((a) => (dockerOnly ? a.kind === "docker" : true));

  const act = async (id, a) => { try { await api(`/api/v1/apps/${id}/${a}`, { method: "POST" }); reload(); } catch (e) { setNotice(e.message); } };
  const del = async (id) => { if (!confirm("Удалить сервер?")) return; try { await api(`/api/v1/apps/${id}`, { method: "DELETE" }); reload(); } catch (e) { setNotice(e.message); } };
  const openLogs = async (app) => {
    setLogs({ app, text: "Загрузка…" });
    try {
      const r = await api(`/api/v1/apps/${app.id}/logs`);
      setLogs({ app, text: r.logs || "(пусто)" });
    } catch (e) {
      setLogs({ app, text: `Ошибка: ${e.message}` });
    }
  };
  const refreshLogs = useCallback(async () => {
    if (!logs) return;
    try {
      const r = await api(`/api/v1/apps/${logs.app.id}/logs`);
      setLogs((cur) => (cur ? { ...cur, text: r.logs || "(пусто)" } : cur));
    } catch (e) {
      setLogs((cur) => (cur ? { ...cur, text: `Ошибка: ${e.message}` } : cur));
    }
  }, [logs?.app?.id]);

  useEffect(() => {
    if (!logs) return;
    const t = setInterval(refreshLogs, 2500);
    return () => clearInterval(t);
  }, [logs?.app?.id, refreshLogs]);

  const visible = list.filter((a) => {
    if (statusFilter !== "all" && a.status !== statusFilter) return false;
    const q = query.trim().toLowerCase();
    if (!q) return true;
    const hay = `${a.name} ${a.spec?.preset || ""} ${a.kind}`.toLowerCase();
    return hay.includes(q);
  });
  const online = list.filter((a) => a.status === "RUNNING").length;

  return (
    <div className="stack">
      <div className="row between">
        <div><h2>{dockerOnly ? "Контейнеры" : "Серверы"}</h2><p className="muted small">{dockerOnly ? "Docker-сервисы." : "Приложения и сервисы, размещённые на блоках."}</p></div>
        <button className="btn-primary" onClick={() => setShow(true)}><Icon name="plus" /> Создать сервер</button>
      </div>
      {notice && <div className="notice" onClick={() => setNotice(null)}>{notice}</div>}
      {error && <div className="error">{error}</div>}
      <div className="toolrow">
        <input className="search" placeholder="Поиск по имени, пресету…" value={query} onChange={(e) => setQuery(e.target.value)} />
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="all">Все статусы</option>
          <option value="RUNNING">Только запущенные</option>
          <option value="STOPPED">Остановленные</option>
          <option value="ERROR">С ошибкой</option>
        </select>
        <span className="muted small">{online}/{list.length} запущено</span>
      </div>
      <div className="server-grid">
        {visible.map((a) => <ServerCard key={a.id} app={a} presets={presets} blocks={blocks} onAction={act} onLogs={openLogs} onDelete={del} onOpen={setOpenId} />)}
        {visible.length === 0 && <div className="empty">{list.length === 0 ? (blocks && blocks.length === 0 ? "Нет подключённых блоков — создай сервер после подключения блока." : "Серверов пока нет. Нажми «Создать сервер».") : "Ничего не найдено."}</div>}
      </div>
      {show && <CreateServer presets={presets} blocks={blocks} onClose={() => setShow(false)} onCreated={reload} />}
      {openId && <ServerDetail appId={openId} onClose={() => setOpenId(null)} onChanged={reload} />}
      {logs && (
        <Modal title={`Логи — ${logs.app.name}`} subtitle="Обновляются автоматически" onClose={() => setLogs(null)} wide>
          <div className="console"><pre>{logs.text}</pre></div>
          <div className="actions"><button className="btn-ghost" onClick={refreshLogs}>Обновить</button></div>
        </Modal>
      )}
    </div>
  );
}

/* -------------------------------- inference ------------------------------ */

function Inference() {
  const { data: presets } = usePolling(() => api("/api/v1/inference/presets"), 0);
  const [preset, setPreset] = useState("llama-3-8b");
  const [plan, setPlan] = useState(null);
  const [error, setError] = useState(null);
  async function run() {
    setError(null);
    try { setPlan(await api("/api/v1/inference/plan", { method: "POST", body: { preset } })); } catch (e) { setError(e.message); }
  }
  return (
    <div className="stack">
      <div><h2>AI Infrastructure</h2><p className="muted small">Планировщик разбиения одной модели по блокам (pipeline parallelism). Честно учитывает VRAM и сеть.</p></div>
      <div className="row">
        <select value={preset} onChange={(e) => setPreset(e.target.value)}>
          {Object.keys(presets || { "llama-3-8b": {} }).map((k) => <option key={k} value={k}>{k}</option>)}
        </select>
        <button className="btn-primary" onClick={run}>Построить план</button>
      </div>
      {error && <div className="error">{error}</div>}
      {plan && (
        <div className="panel">
          <div className="row between"><strong>{plan.model}</strong><span className={cx("pill", plan.feasible ? "pill-ONLINE" : "pill-ERROR")}>{plan.feasible ? "FEASIBLE" : "NOT FEASIBLE"}</span></div>
          <p className="muted small">Нужно VRAM: {plan.required_vram_gb} GB · Доступно: {plan.available_vram_gb} GB · {plan.strategy}</p>
          {plan.stages.length > 0 && (
            <div className="stage-list">
              {plan.stages.map((s) => <div className="stage" key={s.block_id}><strong>{s.block_name}</strong><span className="muted">слои {s.layer_start}–{s.layer_end} ({s.layers})</span><span>{s.vram_needed_mb} MB</span></div>)}
            </div>
          )}
          {plan.reasons.map((r, i) => <div className="bad" key={i}>• {r}</div>)}
          {plan.warnings.map((r, i) => <div className="warn" key={i}>• {r}</div>)}
          <p className="muted small">{plan.notes}</p>
        </div>
      )}
    </div>
  );
}

/* ------------------------------- monitoring ------------------------------ */

function Monitoring() {
  const { data: blocks } = usePolling(() => api("/api/v1/blocks"), 5000);
  const [blockId, setBlockId] = useState("");
  const { data: metrics } = usePolling(() => (blockId ? api(`/api/v1/blocks/${blockId}/metrics`) : Promise.resolve([])), 4000, [blockId]);
  const cpu = (metrics || []).map((m) => m.data.cpu_usage_percent || 0);
  const ram = (metrics || []).map((m) => m.data.ram_used_mb || 0);
  const last = metrics && metrics.length ? metrics[metrics.length - 1].data : null;
  return (
    <div className="stack">
      <div><h2>Мониторинг</h2><p className="muted small">История heartbeat по блокам.</p></div>
      <select value={blockId} onChange={(e) => setBlockId(e.target.value)}>
        <option value="">Выбери блок</option>
        {(blocks || []).map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
      </select>
      {blockId ? (
        <>
          <div className="kpi-grid">
            <div className="kpi"><div className="kpi-icon"><Icon name="monitor" /></div><div><div className="kpi-value">{last ? Math.round(last.cpu_usage_percent) : 0}%</div><div className="kpi-label">CPU сейчас</div></div></div>
            <div className="kpi"><div className="kpi-icon"><Icon name="servers" /></div><div><div className="kpi-value">{last ? (last.ram_used_mb / 1024).toFixed(1) : 0} GB</div><div className="kpi-label">RAM занято</div></div></div>
            <div className="kpi"><div className="kpi-icon"><Icon name="logs" /></div><div><div className="kpi-value">{last ? (last.disk_used_mb / 1024).toFixed(0) : 0} GB</div><div className="kpi-label">Disk занято</div></div></div>
            <div className="kpi"><div className="kpi-icon"><Icon name="ai" /></div><div><div className="kpi-value">{last ? (last.net_rx_kbps || 0).toFixed(0) : 0}</div><div className="kpi-label">Сеть (KB/s)</div></div></div>
          </div>
          <div className="panel"><div className="panel-title">CPU %</div><AreaChart points={cpu} color="#5b8cff" /></div>
          <div className="panel"><div className="panel-title">RAM (MB)</div><AreaChart points={ram} color="#22c55e" /></div>
        </>
      ) : <div className="empty">Выбери блок, чтобы увидеть графики.</div>}
    </div>
  );
}

/* ---------------------------------- logs --------------------------------- */

function Logs() {
  const { data, error } = usePolling(() => api("/api/v1/audit"), 4000);
  return (
    <div className="stack">
      <div><h2>Логи</h2><p className="muted small">Журнал действий администратора и системы.</p></div>
      {error && <div className="error">{error}</div>}
      <div className="console log-table">
        {(data || []).map((r, i) => (
          <div className="log-row" key={i}>
            <span className="muted">{new Date(r.ts * 1000).toLocaleString()}</span>
            <span className="pill">{r.actor}</span>
            <span>{r.action}</span>
            <span className="muted">{r.detail}</span>
          </div>
        ))}
        {(!data || data.length === 0) && <div className="muted">Пока пусто.</div>}
      </div>
    </div>
  );
}

/* -------------------------------- security ------------------------------- */

function Security() {
  const { data, reload } = usePolling(() => api("/api/v1/security/tokens"), 0);
  const { data: cfg } = usePolling(() => api("/api/v1/settings"), 0);
  const [note, setNote] = useState("");
  const [created, setCreated] = useState(null);
  const masterUrl = cfg?.public_url || "https://<этот-master>";
  async function create() {
    const r = await api("/api/v1/security/tokens", { method: "POST", body: { note } });
    setCreated(r.pairing_token);
    setNote("");
    reload();
  }
  return (
    <div className="stack">
      <div><h2>Безопасность</h2><p className="muted small">Одноразовые токены сопряжения. Каждый блок получает свой секрет.</p></div>
      <div className="row">
        <input placeholder="Комментарий к токену" value={note} onChange={(e) => setNote(e.target.value)} />
        <button className="btn-primary" onClick={create}>Создать токен</button>
      </div>
      {created && <pre className="code">nexus up block --master {masterUrl} --token {created}</pre>}
      <div className="panel">
        <table className="table">
          <thead><tr><th>#</th><th>Комментарий</th><th>Создан</th><th>Использован</th></tr></thead>
          <tbody>
            {(data || []).map((t) => (
              <tr key={t.id}><td>{t.id}</td><td>{t.note || "—"}</td><td>{new Date(t.created_at * 1000).toLocaleString()}</td><td>{t.used ? "да" : "нет"}</td></tr>
            ))}
            {(!data || data.length === 0) && <tr><td colSpan="4" className="muted">Нет токенов.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* -------------------------------- settings ------------------------------- */

function Settings() {
  const { data: cfg, reload } = usePolling(() => api("/api/v1/settings"), 0);
  const [clusterName, setClusterName] = useState("");
  const [publicUrl, setPublicUrl] = useState("");
  const [password, setPassword] = useState("");
  const [msg, setMsg] = useState(null);
  const [accent, setAccent] = useLocalStorage("nexus_accent", "blue");
  const [refresh, setRefresh] = useLocalStorage("nexus_refresh", 5);

  useEffect(() => {
    if (cfg) {
      setClusterName(cfg.cluster_name || "");
      setPublicUrl(cfg.public_url || "");
    }
  }, [cfg]);

  useEffect(() => { applyAccent(accent); }, [accent]);

  async function saveCluster() {
    setMsg(null);
    try {
      await api("/api/v1/settings", { method: "PUT", body: { cluster_name: clusterName, public_url: publicUrl } });
      setMsg("Настройки кластера сохранены.");
      reload();
    } catch (e) {
      setMsg(e.message);
    }
  }
  async function savePassword() {
    setMsg(null);
    try {
      await api("/api/v1/security/password", { method: "POST", body: { password } });
      setMsg("Пароль обновлён.");
      setPassword("");
    } catch (e) {
      setMsg(e.message);
    }
  }
  function saveInterface(nextAccent, nextRefresh) {
    setAccent(nextAccent);
    setRefresh(nextRefresh);
    applyAccent(nextAccent);
    setTimeout(() => window.location.reload(), 150);
  }
  return (
    <div className="stack">
      <div><h2>Настройки</h2><p className="muted small">Параметры кластера, интерфейса и безопасности.</p></div>
      {msg && <div className="notice" onClick={() => setMsg(null)}>{msg}</div>}

      <div className="settings-grid">
        <div className="panel">
          <div className="panel-title">Кластер</div>
          <label>Название кластера<input value={clusterName} onChange={(e) => setClusterName(e.target.value)} placeholder="NEXUS Cloud" /></label>
          <label>Публичный адрес MASTER
            <input value={publicUrl} onChange={(e) => setPublicUrl(e.target.value)} placeholder="https://panel.example.com" />
          </label>
          <p className="muted small">Используется в команде подключения блоков и ссылках.</p>
          <div className="actions"><button className="btn-primary" onClick={saveCluster} disabled={!clusterName}>Сохранить</button></div>
        </div>

        <div className="panel">
          <div className="panel-title">Интерфейс</div>
          <label>Акцентный цвет</label>
          <div className="accent-row">
            {ACCENTS.map((a) => (
              <button key={a.id} className={cx("accent-swatch", accent === a.id && "active")} style={{ "--sw": a.color, "--sw2": a.color2 }} onClick={() => saveInterface(a.id, refresh)} title={a.label} />
            ))}
          </div>
          <label>Интервал автообновления
            <select value={refresh} onChange={(e) => saveInterface(accent, Number(e.target.value))}>
              <option value={3}>3 секунды</option>
              <option value={5}>5 секунд</option>
              <option value={10}>10 секунд</option>
              <option value={30}>30 секунд</option>
            </select>
          </label>
          <p className="muted small">Применяется сразу (страница перезагрузится).</p>
        </div>

        <div className="panel">
          <div className="panel-title">Безопасность</div>
          <label>Новый пароль администратора<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" /></label>
          <div className="actions"><button className="btn-primary" onClick={savePassword} disabled={!password}>Обновить пароль</button></div>
        </div>

        <div className="panel">
          <div className="panel-title">О системе</div>
          <div className="kv"><span className="muted">Роль</span><strong>{cfg?.role || "—"}</strong></div>
          <div className="kv"><span className="muted">Heartbeat</span><strong>{cfg ? `${cfg.heartbeat_interval}s` : "—"}</strong></div>
          <div className="kv"><span className="muted">Офлайн через</span><strong>{cfg ? `${cfg.offline_after}s` : "—"}</strong></div>
          <div className="kv"><span className="muted">Публичный URL</span><strong className="mono small">{cfg?.public_url || "не задан"}</strong></div>
        </div>
      </div>
    </div>
  );
}

/* --------------------------------- shell --------------------------------- */

const NAV = [
  ["overview", "Обзор", "overview"],
  ["blocks", "Блоки", "blocks"],
  ["codeserver", "Code Server", "terminal"],
  ["inference", "AI Infrastructure", "ai"],
  ["monitoring", "Мониторинг", "monitor"],
  ["logs", "Логи", "logs"],
  ["security", "Безопасность", "security"],
  ["settings", "Настройки", "settings"],
];

function Dashboard({ onLogout }) {
  const [view, setView] = useState("overview");
  const { data: overview } = usePolling(() => api("/api/v1/overview"), 5000);
  const [clock, setClock] = useState(() => new Date());
  useEffect(() => {
    const t = setInterval(() => setClock(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  const clusterName = overview?.cluster_name || "NEXUS Cloud";
  const content = {
    overview: <Overview />,
    blocks: <Blocks />,
    codeserver: <CodeServer />,
    inference: <Inference />,
    monitoring: <Monitoring />,
    logs: <Logs />,
    security: <Security />,
    settings: <Settings />,
  }[view];
  const title = NAV.find(([k]) => k === view)?.[1] || "";
  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark">N</span><span>NEXUS<span className="accent">CLOUD</span></span></div>
        <nav>
          {NAV.map(([key, label, icon]) => (
            <button key={key} className={cx(view === key && "active")} onClick={() => setView(key)}>
              <Icon name={icon} /><span>{label}</span>
            </button>
          ))}
        </nav>
        <div className="sidebar-foot">
          <div className="cluster-pill"><StatusDot status={overview?.blocks_online ? "ONLINE" : "OFFLINE"} /> {overview?.blocks_online || 0} блоков онлайн</div>
          <button className="btn-ghost sm" onClick={() => { setToken(null); onLogout(); }}>Выйти</button>
        </div>
      </aside>
      <main className="content">
        <header className="topbar">
          <div>
            <h1>{title}</h1>
            <p className="muted small">{clusterName}</p>
          </div>
          <div className="topbar-right">
            <span className="pill pill-ONLINE">{overview?.blocks_online || 0} блоков онлайн</span>
            <span className="clock mono">{clock.toLocaleTimeString()}</span>
          </div>
        </header>
        {content}
      </main>
    </div>
  );
}

export default function App() {
  const [authed, setAuthed] = useState(!!getToken());
  const [notice, setNotice] = useState(null);
  const [accent] = useLocalStorage("nexus_accent", "blue");

  useEffect(() => { applyAccent(accent); }, [accent]);

  useEffect(() => {
    const onUnauthorized = () => {
      setNotice("Сессия истекла — войди заново.");
      setAuthed(false);
    };
    window.addEventListener("nexus:unauthorized", onUnauthorized);
    return () => window.removeEventListener("nexus:unauthorized", onUnauthorized);
  }, []);

  if (!authed) return <Login onLogin={() => { setNotice(null); setAuthed(true); }} notice={notice} />;
  return <Dashboard onLogout={() => setAuthed(false)} />;
}
