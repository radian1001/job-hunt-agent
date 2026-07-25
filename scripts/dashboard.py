#!/usr/bin/env python3
"""Local web dashboard for job-hunt-agent. Python stdlib only.

Serves a single page at http://127.0.0.1:8765 with the scored job list, a
Scan Now button, per-job Draft buttons, and status dropdowns. Everything reads
from state/jobhunt.db (the source of truth); actions shell out to the same
wrappers and skills the scheduler uses, so the UI and the cron path stay
identical in behaviour.

Bound to 127.0.0.1 on purpose: this exposes job data and can launch local
processes, so it must never listen on a public interface.
"""
import json
import os
import re
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOST, PORT = "127.0.0.1", 8765
FINGERPRINT_RE = re.compile(r"^[0-9a-f]{16}$")

# Tracks background scan/draft launches so the UI can show progress.
JOBS_LOCK = threading.Lock()
RUNNING = {}  # key -> {"kind", "label", "state", "detail"}


def project_path(*parts):
    return os.path.join(ROOT, *parts)


def log_tail(name, lines=40):
    path = project_path("logs", name)
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8", errors="replace") as f:
        return "".join(f.readlines()[-lines:])


def launch(key, kind, label, argv):
    """Run a wrapper/CLI detached, tracking completion for the status endpoint."""
    with JOBS_LOCK:
        if RUNNING.get(key, {}).get("state") == "running":
            return False
        RUNNING[key] = {"kind": kind, "label": label, "state": "running", "detail": ""}

    def run():
        try:
            proc = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True,
                                  shell=False)
            ok = proc.returncode == 0
            detail = (proc.stdout or "")[-4000:] or (proc.stderr or "")[-4000:]
            state = "done" if ok else "failed"
        except Exception as exc:  # launching itself failed
            state, detail = "failed", str(exc)
        with JOBS_LOCK:
            RUNNING[key] = {"kind": kind, "label": label, "state": state,
                            "detail": detail.strip()}

    threading.Thread(target=run, daemon=True).start()
    return True


def claude_argv(prompt, extra_tools=()):
    """Headless claude call with the same scoped allowlist the wrappers use."""
    tools = ["mcp__tinyfish__search", "mcp__tinyfish__fetch_content",
             "Bash(python:*)", "Bash(powershell:*)", "Read", "Write", "Edit"]
    tools.extend(extra_tools)
    argv = ["cmd", "/c", "claude", "-p", prompt,
            "--permission-mode", "acceptEdits", "--allowedTools"]
    argv.extend(tools)
    return argv


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # keep the console quiet
        pass

    # ---------- helpers ----------
    def send_json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, html):
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except ValueError:
            return {}

    # ---------- routes ----------
    def do_GET(self):
        if self.path == "/":
            return self.send_html(PAGE)
        if self.path == "/api/data":
            con = db.connect()
            try:
                jobs = db.list_jobs(con, 300)
                stats = db.stats(con, 7)
            finally:
                con.close()
            with JOBS_LOCK:
                running = dict(RUNNING)
            return self.send_json({"jobs": jobs, "stats": stats, "running": running,
                                   "scan_log": log_tail("scan.log", 25)})
        self.send_json({"error": "not found"}, 404)

    def do_POST(self):
        payload = self.read_json()

        if self.path == "/api/scan":
            started = launch("scan", "scan", "Job scan",
                             ["cmd", "/c", project_path("scripts", "run-scan.cmd")])
            return self.send_json({"started": started})

        if self.path == "/api/draft":
            fp = str(payload.get("fingerprint", ""))
            if not FINGERPRINT_RE.match(fp):
                return self.send_json({"error": "bad fingerprint"}, 400)
            started = launch(f"draft:{fp}", "draft", f"Draft {fp[:8]}",
                             claude_argv(f"/draft-application {fp}"))
            return self.send_json({"started": started})

        if self.path == "/api/status":
            fp = str(payload.get("fingerprint", ""))
            status = str(payload.get("status", ""))
            if not FINGERPRINT_RE.match(fp):
                return self.send_json({"error": "bad fingerprint"}, 400)
            if status not in db.STATUSES:
                return self.send_json({"error": "bad status"}, 400)
            con = db.connect()
            try:
                db.track(con, fp, status)
            except KeyError as exc:
                return self.send_json({"error": str(exc)}, 404)
            finally:
                con.close()
            return self.send_json({"ok": True})

        self.send_json({"error": "not found"}, 404)


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Job Hunt Dashboard</title>
<style>
  :root {
    --bg:#0f1115; --panel:#171a21; --panel2:#1e222b; --line:#2a2f3a;
    --text:#e6e8ec; --muted:#9aa2b1; --accent:#4f8cff; --good:#3fb950;
    --warn:#d29922; --bad:#f85149;
  }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--text);
    font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif; }
  header { padding:20px 24px; border-bottom:1px solid var(--line);
    display:flex; align-items:center; gap:16px; flex-wrap:wrap; }
  h1 { font-size:19px; margin:0; font-weight:600; }
  .grow { flex:1; }
  button { font:inherit; cursor:pointer; border-radius:8px; border:1px solid var(--line);
    background:var(--panel2); color:var(--text); padding:8px 14px; }
  button:hover:not(:disabled) { border-color:var(--accent); }
  button:disabled { opacity:.5; cursor:default; }
  #scanBtn { background:var(--accent); border-color:var(--accent); color:#fff;
    font-weight:600; padding:10px 20px; }
  main { padding:24px; max-width:1100px; margin:0 auto; }
  .stats { display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr));
    gap:12px; margin-bottom:20px; }
  .stat { background:var(--panel); border:1px solid var(--line); border-radius:10px;
    padding:14px 16px; }
  .stat b { display:block; font-size:24px; font-weight:600; }
  .stat span { color:var(--muted); font-size:12px; text-transform:uppercase;
    letter-spacing:.5px; }
  .bar { background:var(--panel); border:1px solid var(--line); border-radius:10px;
    padding:12px 16px; margin-bottom:18px; color:var(--muted); font-size:13px;
    white-space:pre-wrap; font-family:ui-monospace,Consolas,monospace; display:none; }
  .filters { display:flex; gap:8px; margin-bottom:16px; flex-wrap:wrap; }
  .filters input { flex:1; min-width:200px; background:var(--panel); color:var(--text);
    border:1px solid var(--line); border-radius:8px; padding:9px 12px; font:inherit; }
  .job { background:var(--panel); border:1px solid var(--line); border-radius:10px;
    padding:16px; margin-bottom:12px; }
  .jobhead { display:flex; gap:14px; align-items:flex-start; }
  .score { font-size:22px; font-weight:700; min-width:52px; text-align:center; }
  .s-hi { color:var(--good); } .s-mid { color:var(--warn); } .s-lo { color:var(--muted); }
  .title { font-weight:600; }
  .meta { color:var(--muted); font-size:13px; margin-top:2px; }
  .kw { margin-top:10px; font-size:13px; display:flex; gap:6px; flex-wrap:wrap; }
  .kw span { padding:2px 8px; border-radius:20px; background:var(--panel2); }
  .kw .yes { color:var(--good); } .kw .no { color:var(--muted); }
  .actions { display:flex; gap:8px; margin-top:12px; align-items:center;
    flex-wrap:wrap; }
  .actions a { color:var(--accent); text-decoration:none; font-size:14px; }
  select { font:inherit; background:var(--panel2); color:var(--text);
    border:1px solid var(--line); border-radius:8px; padding:7px 10px; }
  .pill { font-size:11px; padding:3px 9px; border-radius:20px; background:var(--panel2);
    color:var(--muted); text-transform:uppercase; letter-spacing:.4px; }
  /* Pipeline state reads off the status pill itself rather than a card border. */
  .pill.st-Drafted  { color:var(--warn); box-shadow:inset 0 0 0 1px rgba(210,153,34,.35); }
  .pill.st-Applied,
  .pill.st-Offer,
  .pill.st-Accepted { color:var(--good); box-shadow:inset 0 0 0 1px rgba(63,185,80,.35); }
  .pill.st-Interview { color:var(--accent); box-shadow:inset 0 0 0 1px rgba(79,140,255,.4); }
  .pill.st-Rejected { color:var(--muted); }
  .empty { color:var(--muted); text-align:center; padding:40px; }
</style></head><body>
<header>
  <h1>Job Hunt Dashboard</h1>
  <span id="tag" class="pill">loading</span>
  <div class="grow"></div>
  <button id="scanBtn">Scan for jobs now</button>
  <button id="refreshBtn">Refresh</button>
</header>
<main>
  <div class="stats" id="stats"></div>
  <div class="bar" id="bar"></div>
  <div class="filters">
    <input id="q" placeholder="Filter by company, title, location, or skill...">
    <button data-f="all" class="fbtn">All</button>
    <button data-f="strong" class="fbtn">Score 70+</button>
    <button data-f="new" class="fbtn">Not yet drafted</button>
    <button data-f="pipeline" class="fbtn">In pipeline</button>
  </div>
  <div id="list"></div>
</main>
<script>
const STATUSES = ["Drafted","Applied","Interview","Rejected","Offer","Accepted"];
let DATA = {jobs:[], stats:{}, running:{}}, FILTER = "all";

const esc = s => String(s ?? "").replace(/[&<>"']/g, c =>
  ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

async function load() {
  const r = await fetch('/api/data');
  DATA = await r.json();
  render();
}

function render() {
  const s = DATA.stats || {};
  const apps = s.applications || {};
  const inPipe = ["Applied","Interview","Offer","Accepted"]
    .reduce((n,k) => n + (apps[k]||0), 0);
  document.getElementById('stats').innerHTML = [
    ['Jobs tracked', DATA.jobs.length],
    ['New this week', s.new_jobs ?? 0],
    ['Drafted', apps.Drafted ?? 0],
    ['In pipeline', inPipe],
    ['Interview rate', Math.round((s.interview_rate ?? 0)*100) + '%'],
    ['New companies', (s.new_companies||[]).length],
  ].map(([k,v]) => `<div class="stat"><b>${esc(v)}</b><span>${esc(k)}</span></div>`).join('');

  const scan = (DATA.running || {}).scan;
  const bar = document.getElementById('bar');
  const btn = document.getElementById('scanBtn');
  if (scan && scan.state === 'running') {
    btn.disabled = true; btn.textContent = 'Scanning...';
    bar.style.display = 'block';
    bar.textContent = 'Scan running (usually 10-20 min). Latest log:\n' +
      (DATA.scan_log || '').slice(-1200);
  } else {
    btn.disabled = false; btn.textContent = 'Scan for jobs now';
    if (scan && scan.state === 'failed') {
      bar.style.display = 'block';
      bar.textContent = 'Last scan FAILED:\n' + (scan.detail || '').slice(-1200);
    } else if (scan && scan.state === 'done') {
      bar.style.display = 'block';
      bar.textContent = 'Last scan finished.\n' + (DATA.scan_log || '').slice(-800);
    } else { bar.style.display = 'none'; }
  }
  document.getElementById('tag').textContent =
    (scan && scan.state === 'running') ? 'scanning' : 'idle';

  const q = document.getElementById('q').value.toLowerCase();
  let jobs = DATA.jobs.filter(j => {
    if (FILTER === 'strong' && !(j.total >= 70)) return false;
    if (FILTER === 'new' && j.status) return false;
    if (FILTER === 'pipeline' && !j.status) return false;
    if (!q) return true;
    return [j.company, j.title, j.location, (j.stack||[]).join(' ')]
      .join(' ').toLowerCase().includes(q);
  });

  document.getElementById('list').innerHTML = jobs.length ? jobs.map(j => {
    const sc = j.total == null ? '--' : j.total;
    const cls = j.total >= 70 ? 's-hi' : j.total >= 50 ? 's-mid' : 's-lo';
    const drafting = (DATA.running||{})['draft:'+j.fingerprint];
    const busy = drafting && drafting.state === 'running';
    const yes = (j.matched_keywords||[]).slice(0,8)
      .map(k => `<span class="yes">+ ${esc(k)}</span>`).join('');
    const no = (j.missing_keywords||[]).slice(0,6)
      .map(k => `<span class="no">- ${esc(k)}</span>`).join('');
    return `<div class="job">
      <div class="jobhead">
        <div class="score ${cls}">${esc(sc)}</div>
        <div style="flex:1">
          <div class="title">${esc(j.company)} — ${esc(j.title)}</div>
          <div class="meta">${esc(j.location || 'location n/a')}
            ${j.recommendation ? ' · ' + esc(j.recommendation) : ''}
            · via ${esc(j.source)}${j.has_jd ? ' · JD cached' : ''}</div>
        </div>
        ${j.status ? `<span class="pill st-${esc(j.status)}">${esc(j.status)}</span>` : ''}
      </div>
      <div class="kw">${yes}${no}</div>
      <div class="actions">
        <button data-draft="${esc(j.fingerprint)}" ${busy ? 'disabled' : ''}>
          ${busy ? 'Drafting...' : (j.status ? 'Re-draft' : 'Draft application')}</button>
        <select data-status="${esc(j.fingerprint)}">
          <option value="">Set status...</option>
          ${STATUSES.map(s2 => `<option ${j.status === s2 ? 'selected' : ''}
            value="${s2}">${s2}</option>`).join('')}
        </select>
        ${j.url ? `<a href="${esc(j.url)}" target="_blank" rel="noreferrer">Open posting</a>` : ''}
        ${j.folder ? `<span class="meta">${esc(j.folder)}</span>` : ''}
      </div>
      ${drafting && drafting.state === 'failed'
        ? `<div class="meta" style="color:var(--bad);margin-top:8px">Draft failed: ${
            esc((drafting.detail||'').slice(-300))}</div>` : ''}
    </div>`;
  }).join('') : '<div class="empty">No jobs match. Hit "Scan for jobs now" to fetch fresh postings.</div>';
}

document.getElementById('scanBtn').onclick = async () => {
  await fetch('/api/scan', {method:'POST'});
  load();
};
document.getElementById('refreshBtn').onclick = load;
document.getElementById('q').oninput = render;
document.querySelectorAll('.fbtn').forEach(b => b.onclick = () => {
  FILTER = b.dataset.f; render();
});
document.addEventListener('click', async e => {
  const fp = e.target.dataset && e.target.dataset.draft;
  if (!fp) return;
  await fetch('/api/draft', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({fingerprint: fp})});
  load();
});
document.addEventListener('change', async e => {
  const fp = e.target.dataset && e.target.dataset.status;
  if (!fp || !e.target.value) return;
  await fetch('/api/status', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({fingerprint: fp, status: e.target.value})});
  load();
});
load();
setInterval(load, 15000);  // keeps scan progress and draft results current
</script></body></html>
"""


def main():
    con = db.connect()  # creates the DB/tables if this is a fresh clone
    con.close()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    url = f"http://{HOST}:{PORT}"
    print(f"Job Hunt Dashboard running at {url}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
