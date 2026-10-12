"""Local position, nearby OSM places, and separate SunsetBot district matching."""
import json
import math
import os
import pathlib
import subprocess
import time

import requests

BASE = pathlib.Path(__file__).resolve().parent
CONFIG = pathlib.Path(os.environ.get('APPDATA', pathlib.Path.home())) / 'GlowLetters'
SETTINGS = CONFIG / 'location.json'
CACHE = pathlib.Path(os.environ.get('LOCALAPPDATA', pathlib.Path.home())) / 'GlowLetters' / 'nearby-cache.json'
SEARCH_CACHE = CACHE.with_name('search-cache.json')
UA = {'User-Agent': 'GlowLetters/0.1 (https://github.com/isCharles/glow-letters)'}
NOMINATIM = os.environ.get('GLOW_NOMINATIM_URL', 'https://nominatim.openstreetmap.org').rstrip('/')
PHOTON = os.environ.get('GLOW_PHOTON_URL', 'https://photon.komoot.io').rstrip('/')
OVERPASS = tuple(filter(None, [os.environ.get('GLOW_OVERPASS_URL'),
                                'https://overpass.private.coffee/api/interpreter',
                                'https://overpass-api.de/api/interpreter']))


def load():
    try:
        data = json.loads(SETTINGS.read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            raise ValueError('Invalid saved settings')
        if not isinstance(data.get('city'), str):
            data['city'] = None
        return data
    except (OSError, ValueError, TypeError):
        return {'city': None, 'name': None}


def save(data):
    CONFIG.mkdir(parents=True, exist_ok=True)
    temp = SETTINGS.with_suffix('.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(SETTINGS)


def locate():
    # Windows provides an estimated coordinate; it may only be accurate to a few hundred metres.
    script = '''[Console]::InputEncoding=[System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false)
$OutputEncoding=[System.Text.UTF8Encoding]::new($false)
Add-Type -AssemblyName System.Device
$watcher = New-Object System.Device.Location.GeoCoordinateWatcher
try {
  $watcher.Start($false)
  $deadline = [DateTime]::UtcNow.AddSeconds(25)
  while ($watcher.Position.Location.IsUnknown -and [DateTime]::UtcNow -lt $deadline) {
    if ($watcher.Permission.ToString() -eq 'Denied') { throw 'Location permission denied' }
    Start-Sleep -Milliseconds 200
  }
  if ($watcher.Position.Location.IsUnknown) { throw 'Windows did not return a location' }
  $point = $watcher.Position.Location
  @{lat=$point.Latitude; lon=$point.Longitude; accuracy=$point.HorizontalAccuracy; name='Current position'; source='Windows'} | ConvertTo-Json -Compress
} finally { $watcher.Stop(); $watcher.Dispose() }
'''
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
        capture_output=True, encoding='utf-8', errors='replace', timeout=35,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise ValueError('Windows location unavailable. Check its location settings or search for a place.')
    point = json.loads(result.stdout.strip())
    validate(point)
    return point


def validate(point):
    lat, lon = float(point['lat']), float(point['lon'])
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError('Invalid coordinates')
    return lat, lon


def search(text):
    term = text.strip()
    if not term:
        return []
    try:
        cache = json.loads(SEARCH_CACHE.read_text(encoding='utf-8'))
        cached = cache.get(term.casefold())
        if cached and time.time() - cached['fetched_at'] < 30 * 24 * 3600:
            return cached['places']
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        cache = {}
    response = requests.get(NOMINATIM + '/search', params={
        'q': text, 'format': 'jsonv2', 'limit': 8, 'accept-language': 'en,zh-CN'},
        headers=UA, timeout=25)
    response.raise_for_status()
    places = [{'lat': float(row['lat']), 'lon': float(row['lon']),
               'name': row['display_name'], 'source': 'OpenStreetMap'} for row in response.json()]
    cache[term.casefold()] = {'fetched_at': time.time(), 'places': places}
    try:
        SEARCH_CACHE.parent.mkdir(parents=True, exist_ok=True)
        temporary = SEARCH_CACHE.with_suffix('.tmp')
        temporary.write_text(json.dumps(cache, ensure_ascii=False), encoding='utf-8')
        temporary.replace(SEARCH_CACHE)
    except OSError:
        pass
    return places


def kilometres(lat, lon, other_lat, other_lon):
    a, b = math.radians(lat), math.radians(float(other_lat))
    dlat, dlon = b - a, math.radians(float(other_lon) - lon)
    return 6371 * 2 * math.asin(min(1, math.sqrt(
        math.sin(dlat / 2) ** 2 + math.cos(a) * math.cos(b) * math.sin(dlon / 2) ** 2)))


def nearby_places(point, radius_m=1200, limit=12):
    """Return real named OSM features; never substitute districts for buildings."""
    lat, lon = validate(point)
    cache_key = f'{round(lat, 3):.3f},{round(lon, 3):.3f},{int(radius_m)}'
    try:
        cache = json.loads(CACHE.read_text(encoding='utf-8'))
        cached = cache.get(cache_key)
        if cached and time.time() - cached['fetched_at'] < 24 * 3600:
            return cached['places'][:limit]
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        cache, cached = {}, None
    errors = []
    try:
        response = requests.get(PHOTON + '/reverse', params={
            'lat': lat, 'lon': lon, 'radius': radius_m / 1000,
            'limit': max(50, limit * 4)}, headers=UA, timeout=22)
        response.raise_for_status()
        places, seen = [], set()
        for feature in response.json().get('features', []):
            properties = feature.get('properties') or {}
            name = properties.get('name')
            kind = properties.get('osm_key')
            if not name or kind in ('highway', 'railway', 'boundary', 'place'):
                continue
            coordinates = (feature.get('geometry') or {}).get('coordinates') or []
            if len(coordinates) < 2:
                continue
            other_lon, other_lat = map(float, coordinates[:2])
            distance_m = round(kilometres(lat, lon, other_lat, other_lon) * 1000)
            key = (name.casefold(), distance_m // 75)
            if key in seen or distance_m > radius_m:
                continue
            seen.add(key)
            places.append({'name': name, 'lat': other_lat, 'lon': other_lon,
                           'distance_m': distance_m, 'source': 'OpenStreetMap / Photon',
                           'type': properties.get('osm_value') or kind or 'place'})
        if places:
            places.sort(key=lambda row: (row['distance_m'], row['name']))
            _save_nearby(cache, cache_key, places)
            return places[:limit]
        errors.append('Photon returned no named nearby places')
    except (requests.RequestException, ValueError, TypeError, KeyError) as error:
        errors.append(f'Photon: {error}')

    query = (f'[out:json][timeout:20];'
             f'nwr(around:{int(radius_m)},{lat:.6f},{lon:.6f})[name];'
             f'out center 180;')
    for endpoint in OVERPASS:
        try:
            response = requests.post(endpoint, data={'data': query}, headers=UA, timeout=28)
            response.raise_for_status()
            elements = response.json().get('elements', [])
            break
        except (requests.RequestException, ValueError) as error:
            errors.append(f'{endpoint}: {error}')
    else:
        if cached and time.time() - cached['fetched_at'] < 7 * 24 * 3600:
            return [dict(place, source='OpenStreetMap (cached)') for place in cached['places'][:limit]]
        raise ValueError('Nearby places are unavailable from OpenStreetMap right now. ' + '; '.join(errors))
    places = []
    seen = set()
    for row in elements:
        tags = row.get('tags', {})
        name = tags.get('name:en') or tags.get('name')
        if not name or tags.get('highway') or tags.get('railway') or tags.get('boundary') or tags.get('place'):
            continue
        coord = row.get('center', row)
        if 'lat' not in coord or 'lon' not in coord:
            continue
        distance_m = round(kilometres(lat, lon, coord['lat'], coord['lon']) * 1000)
        key = (name.casefold(), distance_m // 75)
        if key in seen or distance_m > radius_m:
            continue
        seen.add(key)
        places.append({'name': name, 'lat': float(coord['lat']), 'lon': float(coord['lon']),
                       'distance_m': distance_m, 'source': 'OpenStreetMap',
                       'type': next((tags[k] for k in ('building', 'amenity', 'shop', 'tourism', 'leisure')
                                     if tags.get(k)), 'place')})
    places.sort(key=lambda row: (row['distance_m'], row['name']))
    _save_nearby(cache, cache_key, places)
    return places[:limit]


def _save_nearby(cache, cache_key, places):
    cache[cache_key] = {'fetched_at': time.time(), 'places': places[:50]}
    try:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        temporary = CACHE.with_suffix('.tmp')
        temporary.write_text(json.dumps(cache, ensure_ascii=False), encoding='utf-8')
        temporary.replace(CACHE)
    except OSError:
        pass


def suggest_forecast_areas(point, limit=6):
    """Nearest district representative coordinates, separately verified with SunsetBot."""
    lat, lon = validate(point)
    places = json.loads((BASE / 'city-geo.json').read_text(encoding='utf-8'))
    ranked = sorted((r for r in places if r.get('lat') and r.get('lng')),
                    key=lambda r: kilometres(lat, lon, r['lat'], r['lng']))
    checked, selected = set(), []
    for row in ranked[:40]:
        keyword = row['area'] or (row['province'] if row['city'] == '市辖区' else row['city'])
        if keyword in checked:
            continue
        checked.add(keyword)
        try:
            response = requests.get('https://sunsetbot.top/', params={
                'intend': 'change_city', 'city_name_incomplete': keyword, 'query_id': '901'},
                timeout=12)
            response.raise_for_status()
            cities = response.json().get('city_list', [])
        except (requests.RequestException, ValueError):
            continue
        if not isinstance(cities, list):
            continue
        prefix = row['province'] if row['city'] == '市辖区' else row['city']
        variants = {prefix, prefix.removesuffix('市')}
        choices = [city for city in cities if city.split('-')[0] in variants
                   and city.split('-')[-1] == keyword]
        if choices:
            selected.append({'city': choices[0],
                             'approximate_distance_km': round(kilometres(lat, lon, row['lat'], row['lng']), 1),
                             'match_method': 'district representative coordinate, not forecast grid distance'})
            if len(selected) >= limit:
                break
    if not selected:
        raise ValueError('No supported SunsetBot forecast area matched this place.')
    return selected


def match(point):
    return dict(point, **suggest_forecast_areas(point, limit=1)[0])


# Backwards-compatible name for the older desktop window during migration.
suggest = suggest_forecast_areas
