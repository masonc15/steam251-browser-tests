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
    print("Running:", " ".join(args), flush=True)
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if check and p.returncode:
        raise RuntimeError(f'{args}: {p.stderr[-2000:]} {p.stdout[-1000:]}')
    return p.stdout


def screenshot(name):
    run('xcrun', 'simctl', 'io', UDID, 'screenshot', str(OUT / f'{name}.png'))


def wait_for_page(name, expected):
    for attempt in range(10):
        screenshot(name)
        data = json.loads(run('scripts/ocr', str(OUT / f'{name}.png')))
        (OUT / f'{name}-ocr.json').write_text(json.dumps(data, indent=2))
        labels = ' '.join(row['text'] for row in data['rows'])
        if 'View Bookmarks' in labels:
            # Close the first-run tip seen in the iPhone 17 Pro / iOS 26.2
            # screenshot. Coordinates are scaled from that observed screen.
            run('idb', 'ui', 'tap', '--udid', UDID,
                str(round(data['width'] / 3 * .907)), str(round(data['height'] / 3 * .710)))
            time.sleep(1)
            continue
        compact = lambda text: re.sub(r'[^a-z0-9]', '', text.lower())
        if compact(expected) in compact(labels):
            return data
        time.sleep(2)
    raise RuntimeError(f'Safari screenshot did not contain expected page text: {expected}')


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
    # Open the simulator display on the disposable runner so video frames refresh.
    run('open', '-a', 'Simulator', '--args', '-CurrentDeviceUDID', UDID)
    time.sleep(5)
    run('xcrun', 'simctl', 'status_bar', UDID, 'override', '--time', '9:41', '--batteryState', 'charged', '--batteryLevel', '100')
    for name, path, expected in [('home', '/', 'Week Top 50'), ('week', '/7day', 'Hide Early Access'), ('month', '/30day', 'Hide Early Access'), ('detective', '/tag/5613', 'Detective')]:
        if name != 'home':
            run('xcrun', 'simctl', 'terminate', UDID, 'com.apple.mobilesafari', check=False)
        log = (OUT / f'{name}-recording.log').open('w')
        recorder = subprocess.Popen(['xcrun', 'simctl', 'io', UDID, 'recordVideo', '--codec=h264', '--force', str(OUT / f'{name}.mp4')], stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 90
            while 'Recording started' not in (OUT / f'{name}-recording.log').read_text():
                if recorder.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError(f'{name}: video recorder did not become ready')
                time.sleep(.25)
            run('xcrun', 'simctl', 'openurl', UDID, f'https://steam251.com{path}?safari-check={time.time_ns()}')
            data = wait_for_page(name, expected)
            time.sleep(3)
            screenshot(name)
            results.append({'route': path, 'screenshot_text_verified': True, 'visual_review': 'required', 'cache': 'new simulator for home; later routes share asset cache'})
            if name == 'week':
                checkbox = next((row for row in data['rows'] if 'Hide Early Access' in row['text']), None)
                if checkbox:
                    run('idb', 'ui', 'tap', '--udid', UDID,
                        str(round(checkbox['x'] * data['width'] / 3)), str(round(checkbox['y'] * data['height'] / 3)))
                    time.sleep(1)
                    screenshot('week-filter-after')
                    results[-1]['filter_tap_sent'] = True

        finally:
            recorder.send_signal(signal.SIGINT)
            try:
                recorder.wait(timeout=20)
            except subprocess.TimeoutExpired:
                recorder.kill()
                recorder.wait()
            log.close()
            probe = json.loads(run('ffprobe', '-v', 'error', '-count_frames', '-show_entries', 'stream=nb_read_frames:format=duration', '-of', 'json', str(OUT / f'{name}.mp4')))
            (OUT / f'{name}-video-info.json').write_text(json.dumps(probe, indent=2))
            if float(probe['format']['duration']) < 2 or int(probe['streams'][0]['nb_read_frames']) < 10:
                raise RuntimeError(f'{name}: recording lacks enough video frames')
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
