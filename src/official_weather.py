"""Direct NOAA GFS / ECMWF IFS forecasts; solar events computed locally."""
import argparse
import concurrent.futures
import datetime as dt
import json
import math
import pathlib
import tempfile
import threading
import sys

import requests
from astral import Observer
from astral.sun import sunrise, sunset
import eccodes as ec

UTC = dt.timezone.utc
TZ = dt.timezone(dt.timedelta(hours=8))
NOAA = 'https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl'
ECMWF = 'https://data.ecmwf.int/forecasts'
FIELDS = {'tcc': 'cloud_total_pct', 'lcc': 'cloud_low_pct',
          'mcc': 'cloud_mid_pct', 'hcc': 'cloud_high_pct',
          '2r': 'humidity_pct', 'vis': 'visibility_m', 'prate': 'precipitation_rate_mm_h',
          '2t': 'temperature_c', '2d': 'dewpoint_c'}
DECODE_LOCK = threading.Lock()


def solar_events(lat, lon, events, now=None):
    now = now or dt.datetime.now(TZ)
    observer = Observer(latitude=lat, longitude=lon)
    result = {}
    for event in events:
        day = now.astimezone(TZ).date() + dt.timedelta(days=event.startswith('tomorrow'))
        function = sunrise if event.endswith('sunrise') else sunset
        try:
            result[event] = function(observer, date=day, tzinfo=TZ).isoformat()
        except ValueError:
            result[event] = None  # Polar day/night: no solar crossing.
    return result


def cycles(now, delay):
    latest = now.astimezone(UTC) - dt.timedelta(hours=delay)
    latest = latest.replace(hour=latest.hour // 6 * 6, minute=0, second=0, microsecond=0)
    return [latest - dt.timedelta(hours=6 * i) for i in range(5)]


def request(url, **kwargs):
    response = requests.get(url, timeout=(6, 25), **kwargs)
    response.raise_for_status()
    return response


def decode(content, lat, lon, run, valid):
    # ecCodes' Windows definition parser must not initialize concurrently.
    with DECODE_LOCK:
        return _decode(content, lat, lon, run, valid)


def _decode(content, lat, lon, run, valid):
    if not content.startswith(b'GRIB'):
        raise ValueError('Expected GRIB data')
    values, grid = {}, None
    with tempfile.TemporaryFile() as stream:
        stream.write(content)
        stream.seek(0)
        while (handle := ec.codes_grib_new_from_file(getattr(stream, 'file', stream))) is not None:
            try:
                if ec.codes_get(handle, 'stepType') != 'instant':
                    continue
                name = ec.codes_get(handle, 'shortName')
                if name not in FIELDS:
                    continue
                stamp = lambda date, time: dt.datetime.strptime(str(date) + f'{int(time):04d}', '%Y%m%d%H%M').replace(tzinfo=UTC)
                actual_run = stamp(ec.codes_get(handle, 'dataDate'), ec.codes_get(handle, 'dataTime'))
                actual_valid = stamp(ec.codes_get(handle, 'validityDate'), ec.codes_get(handle, 'validityTime'))
                if actual_run != run or actual_valid != valid:
                    raise ValueError('Model run or valid time mismatch')
                point = ec.codes_grib_find_nearest(handle, lat, lon)[0]
                value = float(point['value'])
                if not math.isfinite(value) or value == ec.codes_get(handle, 'missingValue'):
                    continue
                units = ec.codes_get(handle, 'units')
                if name in ('tcc', 'lcc', 'mcc', 'hcc') and units == '(0 - 1)':
                    value *= 100
                if name in ('2t', '2d'):
                    value -= 273.15
                if name == 'prate':
                    value *= 3600
                values[FIELDS[name]] = round(value, 2)
                grid = {'lat': point['lat'], 'lon': point['lon'], 'distance_km': round(point['distance'], 2)}
            finally:
                ec.codes_release(handle)
    if 'cloud_total_pct' not in values:
        raise ValueError('No usable total cloud forecast')
    return values, grid


def gfs_bytes(lat, lon, run, step):
    params = {'file': f'gfs.t{run:%H}z.pgrb2.0p25.f{step:03d}',
              'dir': f'/gfs.{run:%Y%m%d}/{run:%H}/atmos', 'subregion': '',
              'leftlon': max(0, (lon % 360) - .5), 'rightlon': min(360, (lon % 360) + .5),
              'bottomlat': max(-90, lat - .5), 'toplat': min(90, lat + .5)}
    for field in ('TCDC', 'LCDC', 'MCDC', 'HCDC', 'RH', 'VIS', 'PRATE'):
        params['var_' + field] = 'on'
    for level in ('entire_atmosphere', 'low_cloud_layer', 'middle_cloud_layer',
                  'high_cloud_layer', '2_m_above_ground', 'surface'):
        params['lev_' + level] = 'on'
    response = request(NOAA, params=params)
    return response.content, response.url, response.status_code


def ifs_bytes(run, step):
    base = f'{ECMWF}/{run:%Y%m%d}/{run:%H}z/ifs/0p25/oper/{run:%Y%m%d%H}0000-{step}h-oper-fc'
    index = request(base + '.index')
    entries = [json.loads(line) for line in index.text.splitlines()]
    selected = [entry for entry in entries if entry.get('levtype') == 'sfc' and entry.get('param') in ('tcc', '2t', '2d')]
    if not any(entry['param'] == 'tcc' for entry in selected):
        raise ValueError('ECMWF index has no total cloud forecast')
    content = bytearray()
    for entry in selected:
        start, length = int(entry['_offset']), int(entry['_length'])
        response = request(base + '.grib2', headers={'Range': f'bytes={start}-{start + length - 1}'}, stream=True)
        if response.status_code != 206:
            response.close()
            raise ValueError('Server did not return the requested GRIB byte range')
        if len(response.content) != length:
            raise ValueError('Server did not return the requested GRIB byte range')
        content.extend(response.content)
    return bytes(content), base + '.grib2', 206


def model_forecast(model, lat, lon, event, event_time, now):
    row = {'model': model, 'event': event, 'available': False, 'fields': {},
           'provider': 'NOAA/NCEP' if model == 'GFS' else 'ECMWF', 'attempts': []}
    if event_time is None:
        row['reason'] = 'no_solar_event'
        return row
    target = dt.datetime.fromisoformat(event_time).astimezone(UTC)
    delay = 1
    latest_possible = min(now.astimezone(UTC) - dt.timedelta(hours=delay), target)
    for run in cycles(latest_possible, 0):
        if (now.astimezone(UTC) - run).total_seconds() > 30 * 3600:
            continue
        interval = 1 if model == 'GFS' else 3
        step = max(0, int(math.floor((target - run).total_seconds() / (3600 * interval) + .5)) * interval)
        valid = run + dt.timedelta(hours=step)
        attempt = {'run_time': run.isoformat(), 'step_hours': step}
        try:
            payload, url, status = gfs_bytes(lat, lon, run, step) if model == 'GFS' else ifs_bytes(run, step)
            attempt.update(url=url, http_status=status)
            fields, grid = decode(payload, lat, lon, run, valid)
            row.update(available=True, reason=None, fields=fields, grid=grid,
                       run_time=run.isoformat(), valid_time=valid.isoformat(),
                       event_time=event_time, time_offset_minutes=round((valid-target).total_seconds()/60, 1),
                       url=url, http_status=status)
            return row
        except Exception as error:
            attempt['error'] = str(error)
            status = getattr(getattr(error, 'response', None), 'status_code', None)
            if status is not None: attempt['http_status'] = status
            row['attempts'].append(attempt)
    row['reason'] = 'official_source_unavailable'
    return row


def fetch(lat, lon, events, now=None):
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError('Invalid coordinates')
    now = now or dt.datetime.now(TZ)
    solar = solar_events(lat, lon, events, now)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        tasks = [pool.submit(model_forecast, model, lat, lon, event, solar[event], now)
                 for event in events for model in ('GFS', 'EC')]
        rows = [task.result() for task in tasks]
    return {'source': 'NOAA/NCEP GFS + ECMWF IFS (direct)', 'fetched_at': now.isoformat(),
            'coordinates': {'lat': lat, 'lon': lon}, 'solar': solar, 'results': rows}


def describe(row, language='en'):
    if not row or not row.get('available'):
        return '官方天气预报暂不可用' if language == 'zh' else 'Official weather forecast unavailable'
    fields = row['fields']
    number = lambda key, unit: f'{fields[key]:g}{unit}' if key in fields else '—'
    clouds = ' / '.join(number(key, '%') for key in ('cloud_total_pct', 'cloud_low_pct', 'cloud_mid_pct', 'cloud_high_pct'))
    conditions = ' / '.join((number('humidity_pct', '%'), number('visibility_m', ' m'), number('precipitation_rate_mm_h', ' mm/h')))
    thermal = ' / '.join((number('temperature_c', '°C'), number('dewpoint_c', '°C')))
    thermal_line = (('温度 / 露点：' if language == 'zh' else 'Temperature / dew point: ') + thermal + '\n') if 'temperature_c' in fields else ''
    run = dt.datetime.fromisoformat(row['run_time']).astimezone(TZ).strftime('%m-%d %H:%M')
    valid = dt.datetime.fromisoformat(row['valid_time']).astimezone(TZ).strftime('%m-%d %H:%M')
    grid = row['grid']
    if language == 'zh':
        return (f"{row['provider']} 官方直连 · 总/低/中/高云：{clouds}\n"
                f"湿度 / 能见度 / 降水率：{conditions}\n"
                f"{thermal_line}"
                f"起报 {run} · 有效 {valid}（北京时间）\n"
                f"网格 {grid['lat']:g}°, {grid['lon']:g}° · 距所选点 {grid['distance_km']:g} km；— 表示未提供")
    return (f"{row['provider']} direct · Total/low/mid/high cloud: {clouds}\n"
            f"Humidity / visibility / precipitation rate: {conditions}\n"
            f"{thermal_line}"
            f"Run {run} · Valid {valid} (UTC+8)\n"
            f"Grid {grid['lat']:g}°, {grid['lon']:g}° · {grid['distance_km']:g} km from selected place; — not provided")


def exit_code(data):
    rows = data['results']
    valid = sum(bool(row.get('available')) for row in rows)
    return 0 if rows and valid == len(rows) else 2 if valid else 3


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--lat', type=float, required=True)
    parser.add_argument('--lon', type=float, required=True)
    parser.add_argument('--event', choices=['today-sunset', 'tomorrow-sunrise', 'all'], default='all')
    parser.add_argument('--output', type=pathlib.Path)
    args = parser.parse_args()
    events = ['today-sunset', 'tomorrow-sunrise'] if args.event == 'all' else [args.event]
    data = fetch(args.lat, args.lon, events)
    output = json.dumps(data, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(output, encoding='utf-8')
    print(output)
    sys.exit(exit_code(data))
