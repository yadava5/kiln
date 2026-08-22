"""kiln-sample — the samplers behind kiln-top, with their measured costs.

Split out so the cost of each source is stated next to it and can be re-measured
without reading the renderer.

MEASURED 2026-08-22 on this machine, mean of five calls:

    ctypes host_statistics       CPU ticks          0.0 ms
    ctypes host_statistics64     VM stats           0.0 ms
    ctypes host_processor_info   per-core ticks     0.0 ms
    fork   ps -A -o …,comm       process table     28.3 ms
    fork   ioreg -c IOAccelerator GPU              22.6 ms
    fork   netstat -ib           network           22.2 ms
    fork   pmset -g batt         battery           16.5 ms
    fork   vm_stat               memory             3.4 ms   (REPLACED by ctypes)

That table is why the dashboard can run at 100 ms. The two numbers a person
actually watches move — CPU and memory — cost nothing, so they are sampled every
frame. Everything that needs a fork is sampled on its own slower phase, and the
phases are deliberately co-prime-ish so they rarely land on the same frame.

`powermetrics` is not used: it refuses to run without sudo. GPU utilisation
comes from IOAccelerator's PerformanceStatistics, which needs no privileges.
"""
import ctypes
import ctypes.util
import os
import re
import subprocess
import time

_libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
_HOST_CPU_LOAD_INFO = 3
_HOST_VM_INFO64 = 4
_PROCESSOR_CPU_LOAD_INFO = 2

PAGE = os.sysconf("SC_PAGE_SIZE")
NCPU = os.cpu_count() or 1


def _memsize():
    """Total RAM, read ONCE. It cannot change while the process lives, and
    forking sysctl for it every frame was the entire 3.1 ms cost of an
    otherwise free memory sample."""
    try:
        return int(subprocess.run(["/usr/sbin/sysctl", "-n", "hw.memsize"],
                                  capture_output=True, text=True,
                                  timeout=2).stdout.strip())
    except Exception:
        return 0


class _CpuTicks(ctypes.Structure):
    _fields_ = [("t", ctypes.c_uint * 4)]          # user, system, idle, nice


class _VMStat64(ctypes.Structure):
    """vm_statistics64 from <mach/vm_statistics.h>.

    THE FIELD WIDTHS ARE NOT UNIFORM and getting them wrong is silent: a first
    attempt declared every field as uint32 and read compressor_page_count as 0
    while vm_stat reported real compression. natural_t is 32-bit; the counters
    in the middle are 64-bit.
    """
    _fields_ = [
        ("free_count", ctypes.c_uint), ("active_count", ctypes.c_uint),
        ("inactive_count", ctypes.c_uint), ("wire_count", ctypes.c_uint),
        ("zero_fill_count", ctypes.c_uint64), ("reactivations", ctypes.c_uint64),
        ("pageins", ctypes.c_uint64), ("pageouts", ctypes.c_uint64),
        ("faults", ctypes.c_uint64), ("cow_faults", ctypes.c_uint64),
        ("lookups", ctypes.c_uint64), ("hits", ctypes.c_uint64),
        ("purges", ctypes.c_uint64), ("purgeable_count", ctypes.c_uint),
        ("speculative_count", ctypes.c_uint),
        ("decompressions", ctypes.c_uint64), ("compressions", ctypes.c_uint64),
        ("swapins", ctypes.c_uint64), ("swapouts", ctypes.c_uint64),
        ("compressor_page_count", ctypes.c_uint), ("throttled_count", ctypes.c_uint),
        ("external_page_count", ctypes.c_uint), ("internal_page_count", ctypes.c_uint),
        ("total_uncompressed_pages_in_compressor", ctypes.c_uint64),
    ]


def cpu_ticks():
    c = ctypes.c_uint(4)
    i = _CpuTicks()
    if _libc.host_statistics(_libc.mach_host_self(), _HOST_CPU_LOAD_INFO,
                             ctypes.byref(i), ctypes.byref(c)) != 0:
        return None
    return list(i.t)


def per_core_ticks():
    """[(user, system, idle, nice)] per core. Free, same call top uses."""
    count = ctypes.c_uint(0)
    info = ctypes.POINTER(ctypes.c_uint)()
    n = ctypes.c_uint(0)
    if _libc.host_processor_info(_libc.mach_host_self(), _PROCESSOR_CPU_LOAD_INFO,
                                 ctypes.byref(n), ctypes.byref(info),
                                 ctypes.byref(count)) != 0:
        return []
    out = [tuple(info[i * 4 + j] for j in range(4)) for i in range(n.value)]
    _libc.vm_deallocate(_libc.mach_task_self(), info,
                        ctypes.c_size_t(count.value * 4))
    return out


def vm_stats():
    c = ctypes.c_uint(ctypes.sizeof(_VMStat64) // ctypes.sizeof(ctypes.c_uint))
    i = _VMStat64()
    if _libc.host_statistics64(_libc.mach_host_self(), _HOST_VM_INFO64,
                               ctypes.byref(i), ctypes.byref(c)) != 0:
        return None
    return i


def memory():
    """Bytes: used, total, wired, active, compressed, cached(inactive+spec)."""
    global _MEMTOTAL
    if _MEMTOTAL is None:
        _MEMTOTAL = _memsize()
    total = _MEMTOTAL
    v = vm_stats()
    if v is None:
        return 0, total, 0, 0, 0, 0
    wired = v.wire_count * PAGE
    active = v.active_count * PAGE
    comp = v.compressor_page_count * PAGE
    cached = (v.inactive_count + v.speculative_count) * PAGE
    # macOS counts wired + active + compressed as unavailable; inactive and
    # speculative are reclaimable, which is why they are shown separately
    # rather than folded into "used".
    return wired + active + comp, total, wired, active, comp, cached


_MEMTOTAL = None

_GPU_RE = re.compile(
    r'"(Device Utilization %|Renderer Utilization %|Tiler Utilization %|'
    r'In use system memory|Alloc system memory)"=(\d+)')


def gpu():
    """(util%, renderer%, tiler%, vram_in_use, vram_alloc) or None.

    IOAccelerator's PerformanceStatistics, which needs no privileges —
    powermetrics does and refuses without sudo. One fork, ~23 ms, so this runs
    on a slow phase rather than every frame.
    """
    try:
        out = subprocess.run(["/usr/sbin/ioreg", "-r", "-d", "1", "-w", "0",
                              "-c", "IOAccelerator"], capture_output=True,
                             text=True, timeout=3).stdout
    except Exception:
        return None
    d = {}
    for k, val in _GPU_RE.findall(out):
        d.setdefault(k, int(val))
    if "Device Utilization %" not in d:
        return None
    return (d.get("Device Utilization %", 0), d.get("Renderer Utilization %", 0),
            d.get("Tiler Utilization %", 0), d.get("In use system memory", 0),
            d.get("Alloc system memory", 0))


def processes():
    """[(pid, cpu%, rss, name)] — one fork, ~28 ms, for 'where it goes'."""
    try:
        out = subprocess.run(["/bin/ps", "-A", "-o", "pid=,%cpu=,rss=,comm="],
                             capture_output=True, text=True, timeout=4).stdout
    except Exception:
        return []
    rows = []
    for line in out.splitlines():
        f = line.split(None, 3)
        if len(f) < 4:
            continue
        try:
            rows.append((int(f[0]), float(f[1]), int(f[2]) * 1024,
                         os.path.basename(f[3].strip())))
        except ValueError:
            continue
    return rows


def net_bytes():
    try:
        out = subprocess.run(["/usr/sbin/netstat", "-ib"], capture_output=True,
                             text=True, timeout=3).stdout
    except Exception:
        return 0, 0
    rx = tx = 0
    seen = set()
    for line in out.splitlines()[1:]:
        f = line.split()
        if len(f) < 11 or f[0] in seen or f[0].startswith("lo"):
            continue
        try:
            rx += int(f[6]); tx += int(f[9]); seen.add(f[0])
        except (ValueError, IndexError):
            continue
    return rx, tx


def battery():
    try:
        out = subprocess.run(["/usr/bin/pmset", "-g", "batt"],
                             capture_output=True, text=True, timeout=3).stdout
    except Exception:
        return None, ""
    pct = None
    for tok in out.replace(";", " ").split():
        if tok.endswith("%") and tok[:-1].isdigit():
            pct = int(tok[:-1])
    low = out.lower()
    state = ("charging" if "; charging" in low
             else "AC" if "ac attached" in low else "battery")
    return pct, state


def swap_used():
    try:
        s = subprocess.run(["/usr/sbin/sysctl", "-n", "vm.swapusage"],
                           capture_output=True, text=True, timeout=2).stdout
        return float(s.split("used =")[1].split()[0].rstrip("M")) * 1024 * 1024
    except Exception:
        return 0


def disk_free(path="/"):
    try:
        st = os.statvfs(path)
        return st.f_bavail * st.f_frsize, st.f_blocks * st.f_frsize
    except Exception:
        return 0, 0


if __name__ == "__main__":
    print("re-measuring sampler costs on this machine\n")
    for label, fn in (("host_statistics CPU", cpu_ticks),
                      ("host_processor_info per-core", per_core_ticks),
                      ("host_statistics64 VM", vm_stats),
                      ("memory (incl. sysctl fork)", memory),
                      ("ioreg GPU", gpu),
                      ("ps process table", processes),
                      ("netstat", net_bytes),
                      ("pmset battery", battery)):
        fn()
        t = time.time()
        for _ in range(5):
            fn()
        print(f"  {label:32} {(time.time()-t)/5*1000:7.1f} ms")
    u, tot, w, a, c, ca = memory()
    print(f"\n  memory: used {u/2**30:.1f}G of {tot/2**30:.1f}G "
          f"(wired {w/2**30:.1f}G, active {a/2**30:.1f}G, "
          f"compressed {c/2**30:.2f}G, cached {ca/2**30:.1f}G)")
    print(f"  cores: {len(per_core_ticks())}   gpu: {gpu()}")


# ── tokens ──────────────────────────────────────────────────────────────────
# Output tokens are the only additive token figure in a transcript: each
# assistant record carries the tokens THAT record produced, so summing them
# inside a minute is a true tokens/minute. Input and cache counts are not
# additive — they restate the whole context every turn, so summing them would
# multiply-count the same tokens dozens of times.
_TOK_RE = re.compile(r'"timestamp":"([0-9T:\-]{19})[^"]*"')
_OUT_RE = re.compile(r'"output_tokens":(\d+)')
_tok_offset = {}      # path -> bytes already accounted for
_tok_buckets = {}     # epoch_minute -> output tokens


def token_minutes(window_s=1800, tail=262144):
    """{epoch_minute: output_tokens} across every transcript touched recently.

    INCREMENTAL. A full scan of every recent transcript measured 188 ms, which
    is not affordable even on a slow phase. Each file's byte offset is
    remembered, so a later call reads only what was APPENDED since the last one
    — steady state is a few kilobytes and effectively free. Buckets accumulate
    across calls and are aged out of the window rather than recomputed.
    """
    import glob
    now = time.time()
    home = os.path.expanduser("~/.claude/projects")
    cutoff = int((now - window_s) // 60)
    for k in [k for k in _tok_buckets if k < cutoff]:
        del _tok_buckets[k]
    for path in glob.glob(home + "/*/*.jsonl") + glob.glob(home + "/*/*/subagents/*.jsonl"):
        try:
            st = os.stat(path)
        except OSError:
            continue
        if now - st.st_mtime > window_s:
            continue
        prev = _tok_offset.get(path)
        if prev is not None and st.st_size <= prev:
            continue                      # nothing new
        try:
            with open(path, "rb") as f:
                if prev is None:
                    # first sight: read the tail only, and skip the partial line
                    if st.st_size > tail:
                        f.seek(-tail, os.SEEK_END)
                        f.readline()
                else:
                    f.seek(prev)
                base = f.tell()
                raw = f.read()
        except Exception:
            continue
        # Same partial-line rule as agent_index: a transcript being appended to
        # can be read mid-line, and advancing the offset past it would drop
        # that line's tokens for good.
        cut = raw.rfind(b"\n") + 1
        _tok_offset[path] = base + cut
        data = raw[:cut].decode("utf-8", "replace")
        buckets = _tok_buckets
        for line in data.splitlines():
            if '"output_tokens"' not in line:
                continue
            ts = _TOK_RE.search(line)
            ot = _OUT_RE.search(line)
            if not (ts and ot):
                continue
            try:
                t = time.mktime(time.strptime(ts.group(1), "%Y-%m-%dT%H:%M:%S"))
                t -= time.altzone if time.daylight else time.timezone
            except ValueError:
                continue
            if now - t > window_s:
                continue
            buckets[int(t // 60)] = buckets.get(int(t // 60), 0) + int(ot.group(1))
    return _tok_buckets


# ── the agent index ──────────────────────────────────────────────────────────
# Every subagent Claude Code has ever run leaves a transcript at
#   ~/.claude/projects/<encoded-cwd>/<session>/subagents/agent-<id>.jsonl
# and each one carries what the dashboard wants: `attributionAgent` is the
# agent TYPE (labrat, picasso, stig…), `cwd` and `gitBranch` say which checkout
# it worked in, the first and last `timestamp` bound its run, and every
# assistant line carries `message.usage`.
#
# COST, measured 2026-08-22: 1,345 transcripts, 2.9 GB, 11.3 s to read them
# all. That is a background thread and a cached index, never a frame. After
# the first build each refresh reads only bytes APPENDED since last time — the
# same offset trick token_minutes uses — so steady state is a few kilobytes.
#
# OUTPUT TOKENS ARE COUNTED FROM `message.usage`, NEVER BY REGEX. A regex for
# `"output_tokens":(\d+)` over the raw bytes reports 169.9M against the true
# 80.9M, because a tool result that quotes another transcript carries the
# string too: 80 lines of a single 267-line agent log hold more than one
# occurrence. Cheap and wrong.
#
# Input tokens are NOT summed. Each request re-sends the conversation, so a sum
# counts the same cached prefix once per turn; the last value is the context
# the agent actually reached, which is the meaningful figure.

_AI_PATH = os.path.expanduser("~/.claude/cache/kiln-agentindex.json")
_AI_GLOB = (os.path.expanduser("~/.claude/projects/*/*/subagents/agent-*.jsonl"),
            os.path.expanduser("~/.claude/projects/*/*.jsonl"))
_ai = {"recs": {}, "loaded": False, "worker": None, "done": 0, "total": 0,
       "dirty": False, "saved": 0.0}


def _ai_parse(data, r):
    """Fold newly appended bytes of one transcript into its record."""
    import json
    for line in data.splitlines():
        if b'"timestamp"' not in line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        ts = d.get("timestamp") or ""
        if ts:
            if not r.get("t0"):
                r["t0"] = ts
            r["t1"] = ts
        if not r.get("cwd"):
            r["cwd"] = d.get("cwd") or ""
            r["branch"] = d.get("gitBranch") or ""
            r["slug"] = d.get("slug") or ""
        if d.get("attributionAgent"):
            r["type"] = d["attributionAgent"]
        if d.get("effort"):
            r["effort"] = d["effort"]
        m = d.get("message")
        if not isinstance(m, dict):
            continue
        if m.get("model") and not m["model"].startswith("<"):
            # `<synthetic>` marks a message Claude Code generated locally, with
            # no model behind it. Letting it win makes an agent look like it
            # ran on a model that does not exist.
            r["model"] = m["model"]
        u = m.get("usage")
        if isinstance(u, dict):
            r["out"] = r.get("out", 0) + u.get("output_tokens", 0)
            r["turns"] = r.get("turns", 0) + 1
            r["ctx"] = (u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0)
                        + u.get("cache_creation_input_tokens", 0))
    return r


def _ai_refresh():
    """Bring the index up to date. Runs on a worker thread, never a frame."""
    import glob
    import json
    paths = [q for g in _AI_GLOB for q in glob.glob(g)]
    recs = _ai["recs"]
    _ai["total"] = len(paths)
    _ai["done"] = 0
    changed = 0
    for p in paths:
        _ai["done"] += 1
        try:
            st = os.stat(p)
        except OSError:
            continue
        r = recs.get(p)
        if r is not None and st.st_size == r.get("off") and st.st_mtime == r.get("mt"):
            continue
        if r is None or st.st_size < r.get("off", 0):
            r = {"off": 0}                       # new, or truncated and rewritten
        try:
            with open(p, "rb") as f:
                f.seek(r["off"])
                data = f.read()
        except OSError:
            continue
        # A transcript being appended to can be read mid-line. Stop the offset
        # at the last COMPLETE line so the partial one is re-read next time;
        # advancing past it drops that usage block for good, and the loss is
        # silent — the only symptom is a total that is quietly too low.
        cut = data.rfind(b"\n") + 1
        r["off"] += cut
        data = data[:cut]
        r["mt"] = st.st_mtime
        # Identity comes from the PATH, which is the only place it is stated:
        #   .../projects/<enc-cwd>/<session>.jsonl                  a session
        #   .../projects/<enc-cwd>/<session>/subagents/agent-*.jsonl  one agent
        parts = p.split(os.sep)
        if parts[-2] == "subagents":
            r["kind"] = "agent"
            r["sid"] = parts[-3]
        else:
            r["kind"] = "session"
            r["sid"] = parts[-1][:-6]
        _ai_parse(data, r)
        recs[p] = r
        changed += 1
    for p in [p for p in recs if p not in set(paths)]:
        del recs[p]
    _ai["loaded"] = True
    if changed:
        _ai["dirty"] = True
    now = time.time()
    if _ai["dirty"] and now - _ai["saved"] > 30:
        try:
            tmp = _AI_PATH + ".tmp"
            with open(tmp, "w") as f:
                json.dump(recs, f, separators=(",", ":"))
            os.replace(tmp, _AI_PATH)
            _ai["dirty"] = False
            _ai["saved"] = now
        except Exception:
            pass


def agent_index():
    """(records, status) — never blocks.

    status is ("ready", n) once the index covers every transcript, and
    ("indexing", done, total) while the first build is still running. The two
    must render differently: a zero that means "not indexed yet" and a zero
    that means "no agent ever ran" look identical otherwise, which is the same
    trap as a sparkline drawing a measured zero as a blank cell.
    """
    import json
    import threading
    if not _ai["loaded"] and _ai["worker"] is None:
        try:
            with open(_AI_PATH) as f:
                _ai["recs"] = json.load(f)
        except Exception:
            _ai["recs"] = {}
    w = _ai["worker"]
    if w is None or not w.is_alive():
        w = threading.Thread(target=_ai_refresh, daemon=True)
        _ai["worker"] = w
        w.start()
    recs = dict(_ai["recs"])
    if _ai["loaded"]:
        return recs, ("ready", len(recs))
    return recs, ("indexing", _ai["done"], _ai["total"])
