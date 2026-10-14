"""Personal-key access to Sunsethue's documented quality forecast API."""
import concurrent.futures
import datetime as dt
import math

import requests
import glow_credentials
import official_weather

URL = 'https://api.sunsethue.com/event'
SIGNUP = 'https://sunsethue.com/account/signup?fwd=/dev-api/portal'
TZ = official_weather.TZ


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError('Invalid timestamp')
    result = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Timestamp requires a timezone')
    return result


def normalize(raw, lat, lon, event, target, now):
    row = {'event': event, 'source': 'Sunsethue', 'available': False,
           'quality': None, 'reason': 'missing_forecast'}
    if not isinstance(raw, dict) or not isinstance(raw.get('data'), dict):
        return row
    data = raw['data']
    if data.get('model_data') is not True:
        return row
    quality = data.get('quality')
    if isinstance(quality, bool) or not isinstance(quality, (int, float)) or not math.isfinite(quality) or not 0 <= quality <= 1:
        return row
    try:
        event_time = timestamp(data['time'])
        response_time = timestamp(raw['time'])  # Request timestamp, not a model run.
        location = raw['location']
        returned_lat, returned_lon = float(location['latitude']), float(location['longitude'])
        if (data.get('type') != event.rsplit('-', 1)[-1] or
                abs((event_time - target).total_seconds()) > 45 * 60 or
                not math.isfinite(returned_lat) or not math.isfinite(returned_lon) or
                abs(returned_lat - lat) > .01 or abs((returned_lon - lon + 180) % 360 - 180) > .01):
            row['reason'] = 'response_mismatch'
            return row
        age = (now - response_time).total_seconds()
        if age < -300 or age > 12 * 3600:
            row['reason'] = 'stale_response'
            return row
    except (KeyError, ValueError, TypeError):
        return row
    category = str(data.get('quality_text', '')).lower()
    if category not in ('poor', 'fair', 'good', 'great', 'excellent'):
        category = 'poor' if quality < .2 else 'fair' if quality < .4 else 'good' if quality < .6 else 'great'
    row.update(available=True, reason=None, quality=float(quality), category=category,
               event_time=event_time.astimezone(TZ).isoformat(), response_time=response_time.isoformat())
    cloud = data.get('cloud_cover')
    if not isinstance(cloud, bool) and isinstance(cloud, (int, float)) and math.isfinite(cloud) and 0 <= cloud <= 1:
        row['cloud_cover'] = cloud
    row['magics'] = {}
    magics = data.get('magics')
    if not isinstance(magics, dict):
        magics = {}
    for kind in ('golden_hour', 'blue_hour'):
        try:
            start, end = [timestamp(value) for value in magics[kind]]
            if start < end and max(abs((value - target).total_seconds()) for value in (start, end)) <= 6 * 3600:
                row['magics'][kind] = [start.astimezone(TZ).isoformat(), end.astimezone(TZ).isoformat()]
        except (KeyError, ValueError, TypeError):
            pass
    grid = raw.get('grid_location', {})
    try:
        grid_lat, grid_lon = float(grid['latitude']), float(grid['longitude'])
        if math.isfinite(grid_lat) and math.isfinite(grid_lon) and -90 <= grid_lat <= 90 and -180 <= grid_lon <= 180:
            row['grid_location'] = {'lat': grid_lat, 'lon': grid_lon}
    except (KeyError, TypeError, ValueError):
        pass
    return row


def one(lat, lon, event, solar, now, key):
    row = {'event': event, 'source': 'Sunsethue', 'available': False,
           'quality': None, 'reason': 'not_configured', 'http_status': None}
    if not key:
        return row
    if not solar:
        row['reason'] = 'no_solar_event'
        return row
    target = timestamp(solar)
    # The API date is local to the location. Solar longitude gives its calendar
    # day even when our UTC+8 display day differs (e.g. an American sunset).
    local_date = (target.astimezone(dt.timezone.utc) + dt.timedelta(hours=lon / 15)).date()
    params = {'latitude': lat, 'longitude': lon, 'date': local_date.isoformat(),
              'type': event.rsplit('-', 1)[-1], 'forecast': 'true'}
    try:
        response = requests.get(URL, params=params, headers={'x-api-key': key}, timeout=(5, 15))
        row['http_status'] = response.status_code
        if response.status_code != 200:
            row['reason'] = 'quota_exceeded' if response.status_code == 429 else 'service_rejected'
            return row
        row.update(normalize(response.json(), lat, lon, event, target, now))
    except (requests.RequestException, ValueError, TypeError) as error:
        row['reason'] = 'transport_or_format_error'
        row['error_type'] = type(error).__name__  # Never log key-bearing headers/errors.
    return row


def fetch(lat, lon, events, key=None, now=None):
    now = now or dt.datetime.now(TZ)
    key = key if key is not None else glow_credentials.load()
    solar = official_weather.solar_events(lat, lon, events, now)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        tasks = [pool.submit(one, lat, lon, event, solar[event], now, key) for event in events]
        rows = [task.result() for task in tasks]
    return {'source': 'Sunsethue', 'fetched_at': now.isoformat(), 'results': rows}
