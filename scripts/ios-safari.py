"""Collect real Mobile Safari evidence on a disposable GitHub runner."""
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time

OUT = Path('evidence')
OUT.mkdir(exist_ok=True)
UDID = None
results = []


def run(*args, timeout=60, check=True):
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if check and p.returncode:
        raise RuntimeError(f'{args}: {p.stderr[-2000:]} {p.stdout[-1000:]}')
    return p.stdout


def ax(name):
    raw = run('idb', 'ui', 'describe-all', '--udid', UDID, '--json')
    (OUT / f'{name}.json').write_text(raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = [json.loads(line) for line in raw.splitlines() if line.startswith('{')]
    return data


def elements(data):
    if isinstance(data, list):
        for item in data:
            yield from elements(item)
    elif isinstance(data, dict):
        yield data
        for value in data.values():
            if isinstance(value, (list, dict)):
                yield from elements(value)


def tap(node):
    f = node.get('frame', {})
    if not all(k in f for k in ('x', 'y', 'width', 'height')):
        return False
    run('idb', 'ui', 'tap', '--udid', UDID,
        str(f['x'] + f['width'] / 2), str(f['y'] + f['height'] / 2))
    return True


def screenshot(name):
    run('xcrun', 'simctl', 'io', UDID, 'screenshot', str(OUT / f'{name}.png'))


def wait_for_page(name, expected):
    for attempt in range(10):
        data = ax(f'{name}-ax')
        labels = ' '.join(str(n.get('AXLabel', '')) for n in elements(data))
        if expected.lower() in labels.lower():
            return data
        for n in elements(data):
            label = str(n.get('AXLabel', ''))
            if label in ('Continue', 'Start Browsing', 'Not Now', 'Use Safari'):
                tap(n)
        time.sleep(2)
    screenshot(f'{name}-blocked')
    raise RuntimeError(f'Safari did not expose expected page text: {expected}')


try:
    inventory = json.loads(run('xcrun', 'simctl', 'list', '--json'))
    (OUT / 'simulator-inventory.json').write_text(json.dumps(inventory, indent=2))
    runtimes = [r for r in inventory['runtimes'] if r.get('isAvailable') and '.iOS-' in r['identifier']]
    runtimes.sort(key=lambda r: tuple(map(int, re.findall(r'\d+', r['version']))), reverse=True)
    if not runtimes:
        raise RuntimeError('No installed iOS runtime')
    runtime = runtimes[0]
    devices = inventory['devices'].get(runtime['identifier'], [])
    device = next(d for d in devices if d.get('isAvailable') and d['name'].startswith('iPhone'))
    dtype = device.get('deviceTypeIdentifier')
    if not dtype:
        dtype = next(d['identifier'] for d in inventory['devicetypes'] if d['name'] == device['name'])
    UDID = run('xcrun', 'simctl', 'create', 'Steam251 Safari QA', dtype, runtime['identifier']).strip()
    (OUT / 'environment.json').write_text(json.dumps({'runtime': runtime, 'device': device['name'], 'udid': UDID}, indent=2))
    run('xcrun', 'simctl', 'boot', UDID)
    run('xcrun', 'simctl', 'bootstatus', UDID, '-b', timeout=240)
    run('xcrun', 'simctl', 'status_bar', UDID, 'override', '--time', '9:41', '--batteryState', 'charged', '--batteryLevel', '100')
    run('xcrun', 'simctl', 'openurl', UDID, 'https://steam251.com/')
    wait_for_page('initial', 'Helping you')
    screenshot('initial')
    for name, path, expected in [('home', '/', 'Helping you'), ('week', '/7day', 'Hide Early Access'), ('month', '/30day', 'Hide Early Access'), ('detective', '/tag/5613', 'Detective')]:
        run('xcrun', 'simctl', 'terminate', UDID, 'com.apple.mobilesafari', check=False)
        log = (OUT / f'{name}-recording.log').open('w')
        recorder = subprocess.Popen(['xcrun', 'simctl', 'io', UDID, 'recordVideo', '--codec=h264', '--force', str(OUT / f'{name}.mp4')], stdout=log, stderr=log)
        try:
            time.sleep(1)
            run('xcrun', 'simctl', 'openurl', UDID, f'https://steam251.com{path}?safari-check={time.time_ns()}')
            data = wait_for_page(name, expected)
            time.sleep(3)
            screenshot(name)
            results.append({'route': path, 'content_exposed': True, 'visual_review': 'required', 'cache': 'fresh URL; shared assets may be cached'})
            if name == 'week':
                checkbox = next((n for n in elements(data) if 'Hide Early Access' in str(n.get('AXLabel', '')) and 'check' in str(n.get('role', '')).lower()), None)
                if checkbox and tap(checkbox):
                    time.sleep(1)
                    ax('week-filter-after')
                    screenshot('week-filter-after')
        finally:
            recorder.send_signal(signal.SIGINT)
            try:
                recorder.wait(timeout=20)
            except subprocess.TimeoutExpired:
                recorder.kill()
                recorder.wait()
            log.close()
except Exception as error:
    results.append({'error': str(error)})
    if UDID:
        try:
            screenshot('failure')
        except Exception:
            pass
    raise
finally:
    (OUT / 'results.json').write_text(json.dumps(results, indent=2))
    if UDID:
        run('xcrun', 'simctl', 'shutdown', UDID, check=False)
