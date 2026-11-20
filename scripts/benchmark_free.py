#!/usr/bin/env python3
"""CPU-only, provider-blocked capacity probe; never certifies Render Free.

Runs the allowlisted reel check with the complete API imported, four 25 MP
photos, real 30/60-second-limit H.264/AAC exports, and bundled noncustomer audio.
Linux /proc measures combined RSS of the test process tree (including FFmpeg).
The safety limit applies to API/media descendants, excluding the standalone
offline coordinator (which is not deployed). Both totals are reported. Only
this newly created test process group is stopped at the safety limit.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def tree_rss(root_pid):
    processes = {}
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            values = {}
            for row in (entry / 'status').read_text().splitlines():
                if row.startswith(('PPid:', 'VmRSS:')):
                    values[row.split(':', 1)[0]] = int(row.split()[1])
            processes[int(entry.name)] = (values.get('PPid', 0), values.get('VmRSS', 0))
        except (OSError, ValueError):
            continue
    members = {root_pid}
    while True:
        children = {pid for pid, (parent, _) in processes.items() if parent in members}
        if children <= members:
            break
        members |= children
    breakdown = [{'pid': pid, 'rss_mib': round(processes.get(pid, (0, 0))[1] / 1024, 1)} for pid in sorted(members)]
    return sum(processes.get(pid, (0, 0))[1] for pid in members) * 1024, len(members), breakdown


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '.private/render-transition/capacity-probe.json')
    parser.add_argument('--limit-mib', type=int, default=480)
    parser.add_argument('--timeout-seconds', type=int, default=900)
    args = parser.parse_args()
    if sys.platform != 'linux' or not Path('/proc').exists():
        parser.error('This measured process-tree probe requires Linux; it is not a Windows certification.')
    if not 128 <= args.limit_mib <= 480:
        parser.error('Choose a safety limit between 128 and 480 MiB; do not remove the Free-budget guard.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    log_path = args.output.with_suffix('.log')
    start, peak, workload_peak, members, killed, peak_breakdown = time.monotonic(), 0, 0, 0, None, []
    # test_offline.py rebuilds a credential-free allowlisted child environment.
    with log_path.open('wb') as log:
        child = subprocess.Popen([sys.executable, str(ROOT / 'scripts/test_offline.py'), '--benchmark', 'test_reel_streaming.py'], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        while child.poll() is None:
            rss, n, breakdown = tree_rss(child.pid)
            if rss > peak:
                peak, peak_breakdown = rss, breakdown
            members = max(members, n)
            coordinator = next((item['rss_mib'] for item in breakdown if item['pid'] == child.pid), 0)
            workload = max(0, rss - coordinator * 1024 * 1024)
            workload_peak = max(workload_peak, workload)
            if workload > args.limit_mib * 1024 * 1024:
                killed = 'memory_safety_limit'
            elif time.monotonic() - start > args.timeout_seconds:
                killed = 'test_deadline'
            if killed:
                os.killpg(child.pid, signal.SIGKILL)
                break
            time.sleep(0.025)
        status = child.wait()
    report = {'schema': 1, 'scope': 'local Linux offline synthetic media only',
              'peak_combined_rss_mib': round(peak / 1024 / 1024, 1),
              'peak_workload_rss_mib': round(workload_peak / 1024 / 1024, 1),
              'excluded_from_safety_limit': 'offline coordinator only; all API/media/FFmpeg descendants counted', 'peak_process_count': members, 'peak_process_rss': peak_breakdown,
              'wall_seconds': round(time.monotonic() - start, 2), 'sampling_interval_ms': 25,
              'safety_limit_mib': args.limit_mib, 'exit_code': status, 'stopped_reason': killed,
              'passed': status == 0 and not killed,
              'not_proven': ['Render CPU speed, memory enforcement or cold starts', 'remote AI/TTS/storage compatibility', 'worst-case entropy photos/concurrent users', 'physical devices or Windows', 'background-job durability while asleep']}
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    try:
        args.output.chmod(0o600); log_path.chmod(0o600)
    except OSError:
        pass
    print(json.dumps(report, indent=2))
    print('Offline log:', log_path)
    raise SystemExit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()
