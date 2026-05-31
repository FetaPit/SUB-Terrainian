#!/usr/bin/env python3
"""
chain/flask_app.py  —  SUB-Terrainian v0.1 alpha dashboard

Local Flask server. Mobile-first dark UI.
Open http://localhost:5000 in your Android browser or MetaMask Mobile.

Start: python sub_terrainian.py serve
"""

import hashlib
import json
import os
import secrets
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from threading import Lock

import requests
from flask import (Flask, Response, jsonify, redirect,
                   render_template_string, request, session, stream_with_context)
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY") or secrets.token_hex(32)

HEADERS  = {"User-Agent": "SubTerrainian/0.1 ( contact@ptliveddesign.example )"}
RPC_URL  = os.getenv("BASE_RPC_URL", "https://mainnet.base.org")
EDITION  = os.getenv("MUSIC_EDITION_ADDRESS", "")
PHYSICAL = os.getenv("PHYSICAL_CLAIM_ADDRESS", "")
DB_PATH  = os.getenv("MANIFEST_PATH", "sub_terrainian.db")
MUSIC_ROOT = os.getenv("MUSIC_ROOT", os.path.expanduser("~/storage/shared/Music"))

_run_lock = Lock()


# ── DB helpers ────────────────────────────────────────────────────────────────

def get_db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def db_counts() -> dict:
    try:
        con = get_db()
        releases = con.execute("SELECT COUNT(*) FROM release").fetchone()[0]
        artists  = con.execute("SELECT COUNT(*) FROM artist").fetchone()[0]
        tracks   = con.execute("SELECT COUNT(*) FROM track").fetchone()[0]
        art_done = con.execute(
            "SELECT COUNT(*) FROM release WHERE artwork_fetched_at IS NOT NULL"
        ).fetchone()[0]
        lyr_done = con.execute(
            "SELECT COUNT(*) FROM track WHERE lyrics_fetched_at IS NOT NULL"
        ).fetchone()[0]
        port_done = con.execute(
            "SELECT COUNT(*) FROM artist WHERE portrait_fetched_at IS NOT NULL"
        ).fetchone()[0]
        con.close()
        return dict(releases=releases, artists=artists, tracks=tracks,
                    art_done=art_done, lyr_done=lyr_done, port_done=port_done)
    except Exception:
        return dict(releases=0, artists=0, tracks=0,
                    art_done=0, lyr_done=0, port_done=0)


# ── Ownership checks (raw JSON-RPC) ──────────────────────────────────────────

def _rpc(to: str, data: str) -> str:
    try:
        r = requests.post(RPC_URL, json={
            "jsonrpc": "2.0", "method": "eth_call",
            "params": [{"to": to, "data": data}, "latest"], "id": 1,
        }, headers=HEADERS, timeout=8)
        return r.json().get("result", "0x")
    except Exception:
        return "0x"


def mbid_to_token_id(mbid: str) -> int:
    return int(hashlib.sha256(mbid.encode()).hexdigest(), 16) % (2 ** 256)


def is_owner(wallet: str, mbid: str) -> bool:
    if not wallet or not mbid:
        return False
    try:
        addr = wallet.lower().replace("0x", "").zfill(64)
        tid  = hex(mbid_to_token_id(mbid))[2:].zfill(64)
        raw  = _rpc(EDITION, "0x00fdd58e" + addr + tid) if EDITION else "0x"
        if raw and raw != "0x" and int(raw, 16) > 0:
            return True
        b32 = hashlib.sha256(mbid.encode()).hexdigest()
        raw = _rpc(PHYSICAL, "0x6e7a1e17" + addr + b32) if PHYSICAL else "0x"
        return raw != "0x" and int(raw, 16) != 0
    except Exception:
        return False


# ── Server-Sent Events phase runner ──────────────────────────────────────────

def _stream_subprocess(cmd: list[str]):
    """Run a subprocess and stream its stdout line-by-line as SSE."""
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, cwd=str(Path(__file__).parent.parent),
        )
        for line in proc.stdout:
            yield f"data: {line.rstrip()}\n\n"
        proc.wait()
        status = "DONE" if proc.returncode == 0 else f"ERROR (exit {proc.returncode})"
        yield f"data: ✓ {status}\n\n"
        yield "data: __DONE__\n\n"
    except Exception as e:
        yield f"data: ERROR: {e}\n\n"
        yield "data: __DONE__\n\n"


@app.get("/run/<phase>")
def run_phase(phase: str):
    """SSE endpoint — streams pipeline output to the browser."""
    if not _run_lock.acquire(blocking=False):
        return Response("data: Another phase is already running.\n\ndata: __DONE__\n\n",
                        mimetype="text/event-stream")

    py   = sys.executable
    root = str(Path(__file__).parent.parent)
    force = request.args.get("force", "") == "1"

    cmds = {
        "scan":      [py, "sub_terrainian.py", "scan", MUSIC_ROOT],
        "artwork":   [py, "sub_terrainian.py", "art"],
        "portraits": [py, "sub_terrainian.py", "port"],
        "lyrics":    [py, "sub_terrainian.py", "lyr"],
        "emit":      [py, "sub_terrainian.py", "emit", "--plain"],
        "sync":      [py, "sub_terrainian.py", "sync"],
        "all":       [py, "sub_terrainian.py", "run", MUSIC_ROOT],
    }
    if force:
        for k in cmds:
            if k not in ("sync",):
                cmds[k].append("--force")

    if phase not in cmds:
        _run_lock.release()
        return Response("data: Unknown phase\n\ndata: __DONE__\n\n",
                        mimetype="text/event-stream")

    def generate():
        try:
            yield from _stream_subprocess(cmds[phase])
        finally:
            _run_lock.release()

    return Response(stream_with_context(generate()),
                    mimetype="text/event-stream",
                    headers={"X-Accel-Buffering": "no",
                             "Cache-Control": "no-cache"})


# ── Auth ──────────────────────────────────────────────────────────────────────

@app.post("/connect")
def connect_post():
    data   = request.json or {}
    wallet = data.get("address", "").lower()
    if not wallet.startswith("0x") or len(wallet) != 42:
        return jsonify({"error": "invalid address"}), 400
    session["wallet"] = wallet
    return jsonify({"address": wallet, "connected": True})


@app.post("/disconnect")
def disconnect():
    session.pop("wallet", None)
    return jsonify({"disconnected": True})


# ── API ───────────────────────────────────────────────────────────────────────

@app.get("/api/status")
def api_status():
    return jsonify({
        "wallet":   session.get("wallet"),
        "manifest": db_counts(),
        "contracts": {"edition": bool(EDITION), "physical": bool(PHYSICAL)},
        "chain":    "Base" if "base.org" in RPC_URL else RPC_URL,
        "music_root": MUSIC_ROOT,
    })


@app.get("/api/library")
def api_library():
    con  = get_db()
    page = int(request.args.get("page", 1))
    per  = int(request.args.get("per", 48))
    q    = request.args.get("q", "").strip()
    offset = (page - 1) * per

    where = "WHERE (r.title LIKE ? OR a.name LIKE ?)" if q else ""
    params = [f"%{q}%", f"%{q}%", per, offset] if q else [per, offset]

    rows = con.execute(
        f"""
        SELECT r.id, r.mbid, r.title, r.year, r.artwork_path,
               r.artwork_fetched_at, r.resolved_at,
               r.nft_token_id,
               a.name as artist_name, a.portrait_path,
               (SELECT COUNT(*) FROM track t WHERE t.release_id = r.id) as track_count,
               (SELECT COUNT(*) FROM track t WHERE t.release_id = r.id
                AND t.lyrics_fetched_at IS NOT NULL) as lyrics_done
        FROM release r
        LEFT JOIN artist a ON a.id = r.artist_id
        {where}
        ORDER BY a.sort_name, r.date
        LIMIT ? OFFSET ?
        """,
        params,
    ).fetchall()
    total = con.execute(
        f"SELECT COUNT(*) FROM release r LEFT JOIN artist a ON a.id = r.artist_id {where}",
        [f"%{q}%", f"%{q}%"] if q else [],
    ).fetchone()[0]
    con.close()

    wallet = session.get("wallet")
    items = []
    for r in rows:
        owned = is_owner(wallet, r["mbid"]) if wallet and r["mbid"] else False
        items.append({
            "id":            r["id"],
            "mbid":          r["mbid"],
            "title":         r["title"],
            "year":          r["year"],
            "artist":        r["artist_name"],
            "artwork_path":  r["artwork_path"],
            "has_artwork":   bool(r["artwork_fetched_at"]),
            "has_lyrics":    r["lyrics_done"] > 0,
            "all_lyrics":    r["lyrics_done"] == r["track_count"] and r["track_count"] > 0,
            "resolved":      bool(r["resolved_at"]),
            "portrait_path": r["portrait_path"],
            "nft":           bool(r["nft_token_id"]),
            "owned":         owned,
            "track_count":   r["track_count"],
            "lyrics_done":   r["lyrics_done"],
        })
    return jsonify({"items": items, "total": total, "page": page, "per": per})


@app.get("/api/release/<mbid>")
def api_release(mbid: str):
    con = get_db()
    r = con.execute(
        "SELECT r.*, a.name as artist_name, a.mbid as artist_mbid, "
        "a.portrait_path, a.portrait_url "
        "FROM release r LEFT JOIN artist a ON a.id = r.artist_id "
        "WHERE r.mbid = ?", (mbid,)
    ).fetchone()
    if not r:
        con.close()
        return jsonify({"error": "not found"}), 404
    tracks = con.execute(
        "SELECT id, title, track_number, disc_number, duration_ms, "
        "lyrics_source, lyrics_synced IS NOT NULL as has_lrc, "
        "lyrics_plain IS NOT NULL as has_plain, file_path "
        "FROM track WHERE release_id = ? ORDER BY disc_number, track_number",
        (r["id"],)
    ).fetchall()
    con.close()

    wallet = session.get("wallet")
    owned  = is_owner(wallet, mbid) if wallet else False

    release_data = dict(r)
    release_data["owned"]  = owned
    release_data["tracks"] = [dict(t) for t in tracks]
    return jsonify(release_data)


@app.get("/api/artwork/<int:release_id>")
def serve_artwork(release_id: int):
    """Serve folder.jpg from the filesystem."""
    con = get_db()
    row = con.execute(
        "SELECT artwork_path FROM release WHERE id = ?", (release_id,)
    ).fetchone()
    con.close()
    if not row or not row["artwork_path"]:
        return "", 404
    path = Path(row["artwork_path"])
    if not path.exists():
        return "", 404
    from flask import send_file
    return send_file(str(path), mimetype="image/jpeg")


@app.get("/api/portrait/<int:artist_id>")
def serve_portrait(artist_id: int):
    """Serve artist portrait from the filesystem."""
    con = get_db()
    row = con.execute(
        "SELECT portrait_path FROM artist WHERE id = ?", (artist_id,)
    ).fetchone()
    con.close()
    if not row or not row["portrait_path"]:
        return "", 404
    path = Path(row["portrait_path"])
    if not path.exists():
        return "", 404
    from flask import send_file
    return send_file(str(path), mimetype="image/jpeg")


# ── HTML pages ────────────────────────────────────────────────────────────────

@app.get("/")
def index():
    return render_template_string(DASHBOARD_HTML)


@app.get("/album/<mbid>")
def album_page(mbid: str):
    return render_template_string(ALBUM_HTML, mbid=mbid)


@app.get("/connect")
def connect_page():
    nonce = secrets.token_hex(16)
    session["nonce"] = nonce
    return render_template_string(CONNECT_HTML, nonce=nonce)


# ══════════════════════════════════════════════════════════════════════════════
# HTML Templates — mobile-first, dark, no external CDN
# ══════════════════════════════════════════════════════════════════════════════

_BASE_CSS = """
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --bg:    #0a0a0a;
  --bg2:   #111;
  --bg3:   #1a1a1a;
  --line:  #2a2a2a;
  --muted: #555;
  --text:  #ddd;
  --hi:    #fff;
  --blue:  #3b82f6;
  --green: #22c55e;
  --amber: #f59e0b;
  --red:   #ef4444;
}
html, body { background: var(--bg); color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  font-size: 15px; min-height: 100vh; }
a { color: var(--blue); text-decoration: none; }
a:hover { text-decoration: underline; }
button, .btn {
  display: inline-flex; align-items: center; justify-content: center;
  gap: 6px; padding: 10px 18px; border-radius: 8px; border: none;
  font-size: 14px; font-weight: 600; cursor: pointer;
  transition: opacity .15s; -webkit-tap-highlight-color: transparent;
}
button:active, .btn:active { opacity: .7; }
.btn-primary   { background: var(--blue);  color: #fff; }
.btn-secondary { background: var(--bg3);   color: var(--text); border: 1px solid var(--line); }
.btn-green     { background: var(--green); color: #000; }
.btn-amber     { background: var(--amber); color: #000; }
.btn-danger    { background: var(--red);   color: #fff; }
.btn-full      { width: 100%; }
.card { background: var(--bg2); border: 1px solid var(--line); border-radius: 12px; overflow: hidden; }
.header { display: flex; align-items: center; justify-content: space-between;
  padding: 14px 16px; background: var(--bg2); border-bottom: 1px solid var(--line);
  position: sticky; top: 0; z-index: 100; }
.header h1 { font-size: 17px; font-weight: 700; letter-spacing: -.3px; color: var(--hi); }
.pill { display: inline-flex; align-items: center; gap: 4px;
  padding: 4px 10px; border-radius: 20px; font-size: 12px; font-weight: 600;
  background: var(--bg3); border: 1px solid var(--line); }
.dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.dot-green  { background: var(--green); }
.dot-amber  { background: var(--amber); }
.dot-red    { background: var(--red); }
.dot-blue   { background: var(--blue); }
.dot-grey   { background: var(--muted); }
.tag { display: inline-block; padding: 2px 8px; border-radius: 4px;
  font-size: 11px; font-weight: 600; text-transform: uppercase; }
.tag-green  { background: #14532d; color: #86efac; }
.tag-blue   { background: #1e3a5f; color: #93c5fd; }
.tag-amber  { background: #451a03; color: #fcd34d; }
.tag-grey   { background: var(--bg3); color: var(--muted); }
.muted { color: var(--muted); }
.page { padding: 16px; max-width: 900px; margin: 0 auto; }
.gap-8  { display: flex; flex-direction: column; gap: 8px; }
.gap-12 { display: flex; flex-direction: column; gap: 12px; }
.gap-16 { display: flex; flex-direction: column; gap: 16px; }
.row    { display: flex; align-items: center; gap: 10px; }
.row-sb { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.log-box { background: #000; border: 1px solid var(--line); border-radius: 8px;
  padding: 12px; font-family: monospace; font-size: 12px; line-height: 1.6;
  max-height: 280px; overflow-y: auto; color: #9f9; white-space: pre-wrap;
  word-break: break-all; }
.search-box { width: 100%; background: var(--bg3); border: 1px solid var(--line);
  border-radius: 8px; padding: 10px 14px; color: var(--text); font-size: 15px; }
.search-box:focus { outline: 2px solid var(--blue); }
"""

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<title>SUB-Terrainian</title>
<style>
""" + _BASE_CSS + """
.stats-bar { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 16px; }
.stat-card { background: var(--bg2); border: 1px solid var(--line); border-radius: 10px;
  padding: 12px; text-align: center; }
.stat-num  { font-size: 26px; font-weight: 700; color: var(--hi); line-height: 1; }
.stat-lbl  { font-size: 11px; color: var(--muted); margin-top: 3px; text-transform: uppercase; }
.album-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; }
@media(min-width: 500px) { .album-grid { grid-template-columns: repeat(4, 1fr); gap: 8px; } }
@media(min-width: 700px) { .album-grid { grid-template-columns: repeat(5, 1fr); gap: 10px; } }
.album-card { border-radius: 8px; overflow: hidden; background: var(--bg3);
  cursor: pointer; transition: transform .15s; position: relative; }
.album-card:active { transform: scale(.97); }
.album-art  { width: 100%; aspect-ratio: 1; object-fit: cover; background: var(--bg3); display: block; }
.album-art-placeholder { width: 100%; aspect-ratio: 1; background: var(--bg3);
  display: flex; align-items: center; justify-content: center; color: var(--muted);
  font-size: 28px; }
.album-meta { padding: 6px 7px 7px; }
.album-title { font-size: 11px; font-weight: 600; color: var(--hi);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.album-artist { font-size: 10px; color: var(--muted);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.phase-dots { position: absolute; top: 4px; right: 4px;
  display: flex; gap: 3px; background: rgba(0,0,0,.6);
  padding: 3px 5px; border-radius: 6px; }
.owned-badge { position: absolute; top: 4px; left: 4px;
  background: var(--green); color: #000; font-size: 9px; font-weight: 700;
  padding: 2px 5px; border-radius: 4px; }
.section-title { font-size: 13px; font-weight: 700; color: var(--muted);
  text-transform: uppercase; letter-spacing: .5px; margin-bottom: 8px; }
.actions-panel { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.phase-btn { flex-direction: column; padding: 14px 10px; gap: 4px; border-radius: 10px; }
.phase-btn .phase-label { font-size: 12px; font-weight: 700; }
.phase-btn .phase-sub   { font-size: 10px; font-weight: 400; opacity: .7; }
#loadMore { margin-top: 12px; }
#loadingSpinner { text-align: center; padding: 24px; color: var(--muted); }
</style>
</head>
<body>

<div class="header">
  <h1>SUB-Terrainian</h1>
  <div id="walletPill" class="pill" onclick="location.href='/connect'" style="cursor:pointer">
    <span class="dot dot-grey"></span> connect
  </div>
</div>

<div class="page gap-16">

  <!-- Stats -->
  <div class="stats-bar">
    <div class="stat-card">
      <div class="stat-num" id="statReleases">—</div>
      <div class="stat-lbl">Albums</div>
    </div>
    <div class="stat-card">
      <div class="stat-num" id="statArtwork">—</div>
      <div class="stat-lbl">Artwork</div>
    </div>
    <div class="stat-card">
      <div class="stat-num" id="statLyrics">—</div>
      <div class="stat-lbl">w/ Lyrics</div>
    </div>
  </div>

  <!-- Search -->
  <input class="search-box" id="searchBox" type="search"
    placeholder="Search albums, artists…" autocomplete="off">

  <!-- Actions panel -->
  <div>
    <div class="section-title">Pipeline</div>
    <div class="actions-panel" id="actionsPanel">
      <button class="btn btn-secondary phase-btn" onclick="runPhase('scan')">
        <span class="phase-label">① Scan</span>
        <span class="phase-sub">Resolve MBIDs</span>
      </button>
      <button class="btn btn-secondary phase-btn" onclick="runPhase('artwork')">
        <span class="phase-label">② Artwork</span>
        <span class="phase-sub">CAA → iTunes → Deezer</span>
      </button>
      <button class="btn btn-secondary phase-btn" onclick="runPhase('portraits')">
        <span class="phase-label">③ Portraits</span>
        <span class="phase-sub">Wikidata → Commons</span>
      </button>
      <button class="btn btn-secondary phase-btn" onclick="runPhase('lyrics')">
        <span class="phase-label">④ Lyrics</span>
        <span class="phase-sub">LRCLIB</span>
      </button>
      <button class="btn btn-secondary phase-btn" onclick="runPhase('emit')">
        <span class="phase-label">⑤ Emit .lrc</span>
        <span class="phase-sub">Write sidecars</span>
      </button>
      <button class="btn btn-green phase-btn" onclick="runPhase('sync')">
        <span class="phase-label">↺ Sync</span>
        <span class="phase-sub">Samsung Music</span>
      </button>
    </div>
    <button class="btn btn-primary btn-full" style="margin-top:8px" onclick="runPhase('all')">
      ▶ Run full pipeline
    </button>
  </div>

  <!-- Log output -->
  <div id="logWrap" style="display:none">
    <div class="section-title row-sb">
      <span id="logTitle">Running…</span>
      <button class="btn btn-secondary" style="padding:4px 10px;font-size:12px"
              onclick="document.getElementById('logWrap').style.display='none'">✕</button>
    </div>
    <div class="log-box" id="logBox"></div>
  </div>

  <!-- Library grid -->
  <div>
    <div class="section-title row-sb">
      <span>Library</span>
      <span id="totalCount" class="muted" style="font-size:12px"></span>
    </div>
    <div class="album-grid" id="albumGrid"></div>
    <div id="loadingSpinner">Loading library…</div>
    <button class="btn btn-secondary btn-full" id="loadMore" style="display:none"
            onclick="loadMore()">Load more</button>
  </div>

</div>

<script>
let page = 1, totalItems = 0, loadedItems = 0, currentQuery = '';
let activeSSE = null;

// ── Status ──────────────────────────────────────────────────────
async function loadStatus() {
  const data = await fetch('/api/status').then(r=>r.json()).catch(()=>({}));
  const m = data.manifest || {};
  document.getElementById('statReleases').textContent = m.releases ?? '—';
  document.getElementById('statArtwork').textContent  =
    m.releases ? Math.round(m.art_done/m.releases*100)+'%' : '—';
  document.getElementById('statLyrics').textContent  =
    m.tracks ? Math.round(m.lyr_done/m.tracks*100)+'%' : '—';
  const w = data.wallet;
  const pill = document.getElementById('walletPill');
  if (w) {
    pill.innerHTML = '<span class="dot dot-green"></span> ' + w.slice(0,6)+'…'+w.slice(-4);
  }
}

// ── Library ─────────────────────────────────────────────────────
function phaseDotsHTML(item) {
  const d = (ok, title) =>
    `<span class="dot ${ok ? 'dot-green' : 'dot-grey'}" title="${title}"></span>`;
  return d(item.resolved,'Resolved') + d(item.has_artwork,'Artwork') +
         d(item.has_lyrics,'Lyrics') + (item.nft ? d(true,'NFT') : '');
}

function albumCardHTML(item) {
  const art = item.artwork_path
    ? `<img class="album-art" src="/api/artwork/${item.id}"
           loading="lazy" onerror="this.style.display='none'">`
    : `<div class="album-art-placeholder">♫</div>`;
  const owned = item.owned
    ? `<div class="owned-badge">OWNED</div>` : '';
  return `
<div class="album-card" onclick="location.href='/album/${item.mbid || item.id}'">
  <div style="position:relative">
    ${art}
    <div class="phase-dots">${phaseDotsHTML(item)}</div>
    ${owned}
  </div>
  <div class="album-meta">
    <div class="album-title">${escHtml(item.title)}</div>
    <div class="album-artist">${escHtml(item.artist||'')}${item.year?' · '+item.year:''}</div>
  </div>
</div>`;
}

async function loadLibrary(reset=false) {
  if (reset) { page=1; loadedItems=0; document.getElementById('albumGrid').innerHTML=''; }
  document.getElementById('loadingSpinner').style.display='block';
  const q = currentQuery ? '&q='+encodeURIComponent(currentQuery) : '';
  const data = await fetch(`/api/library?page=${page}&per=48${q}`).then(r=>r.json()).catch(()=>({items:[],total:0}));
  totalItems = data.total;
  document.getElementById('totalCount').textContent = totalItems + ' albums';
  const grid = document.getElementById('albumGrid');
  data.items.forEach(item => grid.insertAdjacentHTML('beforeend', albumCardHTML(item)));
  loadedItems += data.items.length;
  document.getElementById('loadingSpinner').style.display='none';
  document.getElementById('loadMore').style.display =
    loadedItems < totalItems ? 'flex' : 'none';
}

function loadMore() { page++; loadLibrary(); }

let searchTimer;
document.getElementById('searchBox').addEventListener('input', e => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    currentQuery = e.target.value.trim();
    loadLibrary(true);
  }, 300);
});

// ── Phase runner ─────────────────────────────────────────────────
function runPhase(phase) {
  if (activeSSE) { activeSSE.close(); activeSSE=null; }
  const logWrap = document.getElementById('logWrap');
  const logBox  = document.getElementById('logBox');
  const logTitle= document.getElementById('logTitle');
  logBox.textContent = '';
  logWrap.style.display = 'block';
  logTitle.textContent  = phase.toUpperCase() + ' — running…';
  logWrap.scrollIntoView({behavior:'smooth', block:'nearest'});

  activeSSE = new EventSource('/run/'+phase);
  activeSSE.onmessage = e => {
    if (e.data === '__DONE__') {
      activeSSE.close(); activeSSE=null;
      logTitle.textContent = phase.toUpperCase() + ' — complete';
      loadStatus(); loadLibrary(true);
      return;
    }
    logBox.textContent += e.data + '\\n';
    logBox.scrollTop = logBox.scrollHeight;
  };
  activeSSE.onerror = () => {
    logTitle.textContent = phase.toUpperCase() + ' — disconnected';
    activeSSE.close(); activeSSE=null;
  };
}

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── Boot ──────────────────────────────────────────────────────────
loadStatus();
loadLibrary(true);
</script>
</body>
</html>"""

# ── Album detail page ─────────────────────────────────────────────────────────

ALBUM_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SUB-Terrainian — Album</title>
<style>
""" + _BASE_CSS + """
.art-hero { width: 100%; max-width: 280px; border-radius: 12px;
  display: block; margin: 0 auto; aspect-ratio:1; object-fit:cover; }
.art-placeholder { width:100%; max-width:280px; aspect-ratio:1;
  background:var(--bg3); border-radius:12px; margin:0 auto;
  display:flex; align-items:center; justify-content:center;
  font-size:60px; color:var(--muted); }
.meta-block { padding: 8px 0; }
.meta-row { display:flex; justify-content:space-between; padding: 8px 0;
  border-bottom: 1px solid var(--line); font-size:14px; }
.meta-row:last-child { border-bottom:none; }
.meta-key { color: var(--muted); }
.track-row { display:flex; align-items:center; gap:10px;
  padding: 10px 0; border-bottom:1px solid var(--line); }
.track-row:last-child { border-bottom:none; }
.track-num { color:var(--muted); font-size:12px; min-width:22px; text-align:right; }
.track-title { flex:1; font-size:14px; }
.track-dur { color:var(--muted); font-size:12px; }
</style>
</head>
<body>
<div class="header">
  <a href="/" style="color:var(--text);font-size:20px">←</a>
  <h1 id="pageTitle">Album</h1>
  <div id="walletPill" class="pill"></div>
</div>
<div class="page gap-16" id="content">
  <div style="text-align:center;padding:40px;color:var(--muted)">Loading…</div>
</div>
<script>
const MBID = "{{ mbid }}";

function fmtDur(ms) {
  if (!ms) return '';
  const s=Math.round(ms/1000), m=Math.floor(s/60);
  return m+':'+(s%60).toString().padStart(2,'0');
}
function escHtml(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}

async function load() {
  const data = await fetch('/api/release/'+MBID).then(r=>r.json()).catch(()=>null);
  if (!data || data.error) {
    document.getElementById('content').innerHTML=
      '<p style="color:var(--red);padding:20px">Album not found.</p>';
    return;
  }
  document.getElementById('pageTitle').textContent = data.title||'Album';
  document.title = 'SUB-Terrainian — '+(data.title||'');

  const phases = [
    {ok: !!data.resolved_at,         label:'Metadata resolved'},
    {ok: !!data.artwork_fetched_at,  label:'Artwork fetched'},
    {ok: !!data.nft_token_id,        label:'NFT minted'},
  ];
  const phaseHTML = phases.map(p=>
    `<span class="tag ${p.ok?'tag-green':'tag-grey'}">${p.ok?'✓ ':'○ '}${p.label}</span>`
  ).join(' ');

  const artHTML = data.artwork_path
    ? `<img class="art-hero" src="/api/artwork/${data.id}" alt="Album art">`
    : `<div class="art-placeholder">♫</div>`;

  const tracks = (data.tracks||[]).map(t=>`
    <div class="track-row">
      <span class="track-num">${t.track_number}</span>
      <span class="track-title">${escHtml(t.title)}</span>
      ${t.has_lrc?'<span class="tag tag-green" style="font-size:10px">LRC</span>':
        t.has_plain?'<span class="tag tag-blue" style="font-size:10px">TXT</span>':''}
      <span class="track-dur">${fmtDur(t.duration_ms)}</span>
    </div>`).join('');

  const ownedBanner = data.owned
    ? `<div class="card" style="background:#14532d;border-color:#16a34a;padding:14px">
         <div style="font-weight:700;color:#86efac">✓ You own this release</div>
         ${data.nft_token_id?'<div style="font-size:12px;color:#4ade80;margin-top:4px">Token #'+data.nft_token_id.slice(0,12)+'…</div>':''}
       </div>` : '';

  document.getElementById('content').innerHTML = `
    ${ownedBanner}
    ${artHTML}
    <div style="text-align:center;margin-top:-8px">
      <div style="font-size:18px;font-weight:700;color:var(--hi)">${escHtml(data.title)}</div>
      <div style="color:var(--muted);margin-top:4px">${escHtml(data.artist_name||'')}
        ${data.year?' · '+data.year:''}</div>
      <div style="margin-top:8px;display:flex;flex-wrap:wrap;gap:6px;justify-content:center">
        ${phaseHTML}
      </div>
    </div>
    <div class="card">
      <div style="padding:14px 14px 0">
        <div class="section-title" style="margin-bottom:0">Details</div>
      </div>
      <div class="meta-block" style="padding:0 14px 8px">
        ${data.label?`<div class="meta-row"><span class="meta-key">Label</span><span>${escHtml(data.label)}</span></div>`:''}
        ${data.catalog_number?`<div class="meta-row"><span class="meta-key">Cat. No.</span><span>${escHtml(data.catalog_number)}</span></div>`:''}
        <div class="meta-row"><span class="meta-key">MBID</span>
          <span style="font-family:monospace;font-size:11px">${data.mbid||'—'}</span></div>
      </div>
    </div>
    <div class="card">
      <div style="padding:14px 14px 2px">
        <div class="section-title" style="margin-bottom:0">
          Tracks (${(data.tracks||[]).length})
        </div>
      </div>
      <div style="padding:0 14px 8px">${tracks||'<p class="muted" style="padding:12px 0">No tracks in manifest.</p>'}</div>
    </div>
  `;
}

load();
</script>
</body>
</html>"""

CONNECT_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Connect Wallet — SUB-Terrainian</title>
<style>
""" + _BASE_CSS + """
.connect-card { max-width: 420px; margin: 60px auto; padding: 0 16px; }
.wallet-icon { font-size: 48px; text-align:center; margin-bottom:16px; }
</style>
</head>
<body>
<div class="connect-card gap-16">
  <div class="wallet-icon">🔑</div>
  <div style="text-align:center">
    <h2 style="color:var(--hi);margin-bottom:6px">Connect Wallet</h2>
    <p class="muted">Verify ownership of music NFTs on Base.</p>
  </div>
  <button class="btn btn-primary btn-full" id="connectBtn" style="padding:16px">
    Connect with MetaMask
  </button>
  <p class="muted" style="text-align:center;font-size:13px">
    Open this page in the MetaMask Mobile browser,<br>or any wallet with an injected provider.
  </p>
  <div id="msg" class="card" style="display:none;padding:14px"></div>
  <a href="/" style="display:block;text-align:center;color:var(--muted);font-size:13px">
    ← Back to library
  </a>
</div>
<script>
const nonce = "{{ nonce }}";
const msg   = document.getElementById('msg');

document.getElementById('connectBtn').addEventListener('click', async () => {
  if (!window.ethereum) {
    msg.style.display='block';
    msg.innerHTML='<strong style="color:var(--amber)">No wallet detected.</strong><br>'
      +'Open this page inside the MetaMask Mobile browser app.';
    return;
  }
  try {
    const accounts = await ethereum.request({method:'eth_requestAccounts'});
    const address  = accounts[0];
    const message  = 'SUB-Terrainian verify ownership\\nNonce: '+nonce;
    await ethereum.request({method:'personal_sign', params:[message, address]});
    const res  = await fetch('/connect', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({address})
    });
    const data = await res.json();
    if (data.connected) {
      msg.style.display='block';
      msg.innerHTML='<span style="color:var(--green)">✓ Connected: '
        +address.slice(0,8)+'…'+address.slice(-4)+'</span><br>'
        +'<a href="/" style="font-size:13px">← Back to library</a>';
    }
  } catch(e) {
    msg.style.display='block';
    msg.innerHTML='<span style="color:var(--red)">'+e.message+'</span>';
  }
});
</script>
</body>
</html>"""


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    print(f"SUB-Terrainian → http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
