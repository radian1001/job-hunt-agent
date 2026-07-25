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
import urllib.parse
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


MAX_FILE_BYTES = 200_000  # a drafted resume/letter is a few KB; this is a sane ceiling


def read_application(fingerprint):
    """Return the drafted files for a job, read from its recorded folder.

    The folder comes from the database, but it is still resolved and checked to
    sit inside applications/ before anything is read, so a bad value can never
    be used to read arbitrary files off the disk.
    """
    con = db.connect()
    try:
        job = db.get_job(con, fingerprint)
        row = con.execute(
            "SELECT a.folder, a.status FROM Applications a JOIN Jobs j ON j.id = a.job_id"
            " WHERE j.fingerprint = ?", (fingerprint,)).fetchone()
    finally:
        con.close()
    if not job:
        return {"error": "unknown job"}
    if not row or not row["folder"]:
        return {"error": "no draft yet for this job"}

    base = os.path.realpath(project_path("applications"))
    folder = os.path.realpath(project_path(row["folder"]))
    if folder != base and not folder.startswith(base + os.sep):
        return {"error": "draft folder is outside applications/"}
    if not os.path.isdir(folder):
        return {"error": f"folder missing on disk: {row['folder']}"}

    files, pdfs = {}, []
    for name in sorted(os.listdir(folder)):
        path = os.path.join(folder, name)
        if not os.path.isfile(path):
            continue
        ext = os.path.splitext(name)[1].lower()
        if ext == ".pdf":
            pdfs.append(name)
        elif ext in (".md", ".txt", ".tex") and os.path.getsize(path) <= MAX_FILE_BYTES:
            with open(path, encoding="utf-8", errors="replace") as f:
                files[name] = f.read()
    return {"folder": row["folder"], "status": row["status"], "company": job["company"],
            "title": job["title"], "files": files, "pdfs": pdfs}


def resolve_in_applications(rel_path):
    """Resolve a path and confirm it stays inside applications/. None if it escapes."""
    base = os.path.realpath(project_path("applications"))
    target = os.path.realpath(project_path(rel_path))
    if target != base and not target.startswith(base + os.sep):
        return None
    return target


def draft_folder(fingerprint):
    con = db.connect()
    try:
        row = con.execute(
            "SELECT a.folder FROM Applications a JOIN Jobs j ON j.id = a.job_id"
            " WHERE j.fingerprint = ?", (fingerprint,)).fetchone()
    finally:
        con.close()
    return row["folder"] if row and row["folder"] else None


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
                gaps = db.keyword_gaps(con, 45, 15)
            finally:
                con.close()
            with JOBS_LOCK:
                running = dict(RUNNING)
            return self.send_json({"jobs": jobs, "stats": stats, "gaps": gaps,
                                   "running": running,
                                   "scan_log": log_tail("scan.log", 25)})

        if self.path.startswith("/api/application"):
            query = urllib.parse.urlparse(self.path).query
            fp = urllib.parse.parse_qs(query).get("fingerprint", [""])[0]
            if not FINGERPRINT_RE.match(fp):
                return self.send_json({"error": "bad fingerprint"}, 400)
            return self.send_json(read_application(fp))

        if self.path.startswith("/download"):
            params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            fp = params.get("fingerprint", [""])[0]
            name = params.get("name", [""])[0]
            if not FINGERPRINT_RE.match(fp):
                return self.send_json({"error": "bad fingerprint"}, 400)
            # Only a bare filename is accepted, so "name" can never walk the tree.
            if not name or name != os.path.basename(name):
                return self.send_json({"error": "bad filename"}, 400)
            folder = draft_folder(fp)
            if not folder:
                return self.send_json({"error": "no draft for this job"}, 404)
            target = resolve_in_applications(os.path.join(folder, name))
            if not target or not os.path.isfile(target):
                return self.send_json({"error": "file not found"}, 404)
            ctype = {".pdf": "application/pdf", ".tex": "application/x-tex",
                     ".md": "text/markdown; charset=utf-8",
                     ".txt": "text/plain; charset=utf-8"}.get(
                         os.path.splitext(target)[1].lower(), "application/octet-stream")
            with open(target, "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Disposition",
                             f'attachment; filename="{os.path.basename(target)}"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            return self.wfile.write(body)

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

        if self.path == "/api/build-pdf":
            fp = str(payload.get("fingerprint", ""))
            if not FINGERPRINT_RE.match(fp):
                return self.send_json({"error": "bad fingerprint"}, 400)
            folder = draft_folder(fp)
            if not folder or not resolve_in_applications(folder):
                return self.send_json({"error": "no draft folder for this job"}, 404)
            started = launch(f"pdf:{fp}", "pdf", f"PDF {fp[:8]}",
                             [sys.executable, project_path("scripts", "build-pdf.py"),
                              folder])
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
  .gaps { background:var(--panel); border:1px solid var(--line); border-radius:10px;
    padding:16px; margin-bottom:20px; }
  .gaps h2 { font-size:14px; margin:0 0 4px; font-weight:600; }
  .gaps p { margin:0 0 12px; color:var(--muted); font-size:13px; }
  .gaplist { display:flex; gap:8px; flex-wrap:wrap; }
  .gap { background:var(--panel2); border:1px solid var(--line); border-radius:8px;
    padding:7px 11px; font-size:13px; }
  .gap b { color:var(--warn); }
  .gap i { color:var(--muted); font-style:normal; font-size:12px; }
  .modal { position:fixed; inset:0; background:rgba(0,0,0,.6); display:none;
    align-items:center; justify-content:center; padding:24px; z-index:20; }
  .modal.open { display:flex; }
  .sheet { background:var(--panel); border:1px solid var(--line); border-radius:12px;
    width:100%; max-width:900px; max-height:88vh; display:flex; flex-direction:column; }
  .sheethead { padding:16px 20px; border-bottom:1px solid var(--line); display:flex;
    gap:12px; align-items:center; flex-wrap:wrap; }
  .dl { padding:14px 20px 0; display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
  .dl a { background:var(--accent); color:#fff; text-decoration:none; font-size:13px;
    font-weight:600; padding:8px 14px; border-radius:8px; }
  .dl a.alt { background:var(--panel2); color:var(--text); border:1px solid var(--line);
    font-weight:400; }
  .dl span.hint { color:var(--muted); font-size:12px; }
  .tabs { display:flex; gap:6px; padding:12px 20px 0; flex-wrap:wrap; }
  .tabs button.active { border-color:var(--accent); color:var(--accent); }
  .sheetbody { padding:16px 20px 20px; overflow:auto; }
  .sheetbody pre { margin:0; white-space:pre-wrap; word-break:break-word;
    font:13px/1.6 ui-monospace,Consolas,monospace; color:var(--text); }
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
  <div class="gaps" id="gaps"></div>
  <div class="filters">
    <input id="q" placeholder="Filter by company, title, location, or skill...">
    <button data-f="all" class="fbtn">All</button>
    <button data-f="strong" class="fbtn">Score 70+</button>
    <button data-f="new" class="fbtn">Not yet drafted</button>
    <button data-f="pipeline" class="fbtn">In pipeline</button>
  </div>
  <div id="list"></div>
</main>

<div class="modal" id="modal">
  <div class="sheet">
    <div class="sheethead">
      <strong id="mTitle"></strong>
      <span class="pill" id="mFolder"></span>
      <div class="grow"></div>
      <button id="mCopy">Copy this file</button>
      <button id="mClose">Close</button>
    </div>
    <div class="dl" id="mDownloads"></div>
    <div class="tabs" id="mTabs"></div>
    <div class="sheetbody"><pre id="mBody"></pre></div>
  </div>
</div>

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

  const g = DATA.gaps || {gaps:[]};
  const gapEl = document.getElementById('gaps');
  if (g.gaps && g.gaps.length) {
    gapEl.style.display = 'block';
    gapEl.innerHTML = `<h2>Keywords to add to your resume</h2>
      <p>Skills the roles you'd actually want keep asking for and your resume doesn't
      show, across ${esc(g.jobs_considered)} jobs scoring ${esc(g.min_score)}+.
      Learning or surfacing the top ones lifts every future score.</p>
      <div class="gaplist">${g.gaps.map(x => `<div class="gap">
        <b>${esc(x.keyword)}</b> <i>&times;${esc(x.missing_in_jobs)}</i><br>
        <i>${esc(x.wanted_by.slice(0,3).join(', '))}</i></div>`).join('')}</div>`;
  } else { gapEl.style.display = 'none'; }

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
        ${j.folder ? `<button data-view="${esc(j.fingerprint)}">View draft</button>` : ''}
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
// ---- drafted-application viewer ----
let VIEW = {files:{}, current:null, fp:null};
const modal = document.getElementById('modal');

function paintView() {
  const names = Object.keys(VIEW.files);
  document.getElementById('mTabs').innerHTML = names.map(n =>
    `<button data-tab="${esc(n)}" class="${n === VIEW.current ? 'active' : ''}">${esc(n)}</button>`
  ).join('');
  document.getElementById('mBody').textContent = VIEW.files[VIEW.current] || '';
}

function paintDownloads(d) {
  const dl = (name, alt) => `<a class="${alt ? 'alt' : ''}" href="/download?fingerprint=${
    encodeURIComponent(VIEW.fp)}&name=${encodeURIComponent(name)}">${esc(name)}</a>`;
  const pdfs = d.pdfs || [];
  const texs = Object.keys(d.files || {}).filter(n => n.endsWith('.tex'));
  let html = '';
  if (pdfs.length) {
    html += '<span class="hint">Upload to the portal:</span>' +
      pdfs.map(n => dl(n)).join('');
  } else {
    html += `<button data-buildpdf="1">Build PDFs</button>
      <span class="hint">Compiles the .tex resume and the cover letter into
      submission-ready PDFs (needs pdflatex).</span>`;
  }
  if (texs.length) html += texs.map(n => dl(n, true)).join('');
  document.getElementById('mDownloads').innerHTML = html;
}

async function openView(fp) {
  const r = await fetch('/api/application?fingerprint=' + encodeURIComponent(fp));
  const d = await r.json();
  if (d.error) { alert(d.error); return; }
  VIEW.fp = fp;
  VIEW.files = d.files || {};
  // Show the cover letter first if present; it's what needs the closest read.
  const names = Object.keys(VIEW.files);
  VIEW.current = names.find(n => n.startsWith('cover_letter')) || names[0] || null;
  document.getElementById('mTitle').textContent = d.company + ' — ' + d.title;
  document.getElementById('mFolder').textContent = d.folder;
  paintDownloads(d);
  paintView();
  modal.classList.add('open');
}

document.getElementById('mClose').onclick = () => modal.classList.remove('open');
modal.onclick = e => { if (e.target === modal) modal.classList.remove('open'); };
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') modal.classList.remove('open');
});
document.getElementById('mCopy').onclick = async () => {
  try {
    await navigator.clipboard.writeText(VIEW.files[VIEW.current] || '');
    document.getElementById('mCopy').textContent = 'Copied';
    setTimeout(() => document.getElementById('mCopy').textContent = 'Copy this file', 1500);
  } catch (err) { alert('Copy failed: ' + err); }
};

document.addEventListener('click', async e => {
  const ds = e.target.dataset || {};
  if (ds.tab) { VIEW.current = ds.tab; paintView(); return; }
  if (ds.view) { openView(ds.view); return; }
  if (ds.buildpdf) {
    e.target.disabled = true; e.target.textContent = 'Building...';
    await fetch('/api/build-pdf', {method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({fingerprint: VIEW.fp})});
    // pdflatex runs twice per file; re-open when the PDFs have landed.
    setTimeout(() => openView(VIEW.fp), 9000);
    return;
  }
  if (ds.draft) {
    await fetch('/api/draft', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({fingerprint: ds.draft})});
    load();
  }
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
