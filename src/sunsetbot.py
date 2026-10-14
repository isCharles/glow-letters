"""SunsetBot 本机客户端：保留原始响应，明确区分缺数据与零鲜艳度。"""
import argparse
import datetime as dt
import json
import pathlib
import re
import sys
import uuid
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

TZ = dt.timezone(dt.timedelta(hours=8))
EVENTS = {'today-sunset': 'set_1', 'tomorrow-sunrise': 'rise_2',
          'today-sunrise': 'rise_1', 'tomorrow-sunset': 'set_2'}

def number(value):
    match = re.match(r'^\s*(\d+(?:\.\d+)?)', str(value))
    return float(match[1]) if match else None

def normalize(raw, city, model, event, now, max_age):
    result = {'available': False, 'reason': 'missing_forecast',
              'quality': None, 'aod': None, 'event_time': None,
              'resolved_city': raw.get('display_city_name'),
              'model_run': raw.get('display_times_str'), 'raw': raw}
    if raw.get('status') != 'ok':
        result['reason'] = 'city_not_found' if raw.get('status') == 'not_found' else 'upstream_error'
        return result
    quality = number(raw.get('tb_quality'))
    try:
        event_time = dt.datetime.strptime(raw['tb_event_time'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=TZ)
    except (ValueError, KeyError, TypeError):
        return result
    result.update(quality=quality, aod=number(raw.get('tb_aod')), event_time=event_time.isoformat())
    expected_date = now.date() + dt.timedelta(days=1 if event.endswith('2') else 0)
    if event_time.date() != expected_date or raw.get('display_model') != model or raw.get('display_city_name') != city:
        result['reason'] = 'response_mismatch'
        return result
    if quality is None:
        return result
    try:
        run = dt.datetime.strptime(raw['display_times_str'], '%Y%m%d%Hz').replace(tzinfo=dt.timezone.utc)
        age = (now - run).total_seconds() / 3600
        result['model_age_hours'] = round(age, 2)
        if age < 0 or age > max_age:
            result['reason'] = 'stale_model'
            return result
    except (KeyError, ValueError, TypeError):
        result['reason'] = 'unknown_model_time'
        return result
    result.update(available=True, reason=None)
    return result

def fetch(city, events=None, max_age=36, retry_count=2, request_timeout=(10, 25)):
    if not city:
        raise ValueError('Choose a forecast area first')
    now = dt.datetime.now(TZ)
    session = requests.Session()
    retry = Retry(total=retry_count, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504], allowed_methods=['GET'], respect_retry_after_header=False)
    session.mount('https://', HTTPAdapter(max_retries=retry))
    results = []
    for name in events or ['today-sunset', 'tomorrow-sunrise']:
        for model in ['GFS', 'EC']:
            params = dict(query_id=str(uuid.uuid4().int % 10000000), intend='select_city', query_city=city,
                          event_date='None', event=EVENTS[name], times='None', model=model)
            row = {'event': name, 'model': model, 'http_status': None, 'available': False,
                   'quality': None, 'reason': 'transport_error'}
            try:
                # 每次显式传城市，不依赖网站 cookie。TLS 证书校验保持开启。
                session.cookies.clear()
                response = session.get('https://sunsetbot.top/', params=params, timeout=request_timeout)
                row.update(http_status=response.status_code, url=response.url,
                           request_headers=dict(response.request.headers),
                           response_headers={k:v for k,v in response.headers.items() if k.lower() != 'set-cookie'},
                           response_body=response.text)
                response.raise_for_status()
                raw = response.json()
                if not isinstance(raw, dict):
                    raise ValueError('Expected JSON object')
                row.update(normalize(raw, city, model, EVENTS[name], now, max_age))
            except (requests.RequestException, ValueError) as error:
                row['error'] = str(error)
                row['reason'] = 'http_error' if row['http_status'] and row['http_status'] >= 400 else 'transport_or_format_error'
            results.append(row)
    valid = sum(row['available'] for row in results)
    return {'schema_version': 1, 'source': 'SunsetBot', 'fetched_at': now.isoformat(),
            'location': city + ' (regional forecast, not a prediction at the selected coordinates)',
            'requested_city': city, 'status': 'ok' if valid == len(results) else 'partial' if valid else 'unavailable',
            'results': results}

def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--event', choices=['all', *EVENTS], default='all')
    parser.add_argument('--city', required=True, help='SunsetBot official city name')
    parser.add_argument('--max-model-age-hours', type=float, default=36)
    parser.add_argument('--output', type=pathlib.Path)
    args = parser.parse_args()
    data = fetch(args.city, None if args.event == 'all' else [args.event], args.max_model_age_hours)
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix+'.tmp')
        temporary.write_text(text+'\n', encoding='utf-8')
        temporary.replace(args.output)
    print(text)
    return 0 if data['status'] == 'ok' else 2 if data['status'] == 'partial' else 3

if __name__ == '__main__':
    sys.exit(main())
