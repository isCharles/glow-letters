"""Documented API fixtures test contracts; these are not live forecasts."""
import copy
import datetime as dt
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'src'))
import sunsethue as hue
import glow_credentials
import glow_outlook
import glow_notify


class SunsethueTests(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime(2026, 10, 14, 13, tzinfo=hue.TZ)
        self.target = dt.datetime(2026, 10, 15, 6, 24, tzinfo=hue.TZ)
        self.event = 'tomorrow-sunrise'
        self.raw = {'time': self.now.isoformat(), 'location': {'latitude': 40, 'longitude': 116},
                    'data': {'type': 'sunrise', 'time': self.target.isoformat(), 'model_data': True,
                             'quality': .7, 'quality_text': 'Great'}}

    def normalize(self, raw):
        return hue.normalize(raw, 40, 116, self.event, self.target, self.now)

    def test_zero_is_available_but_missing_is_not(self):
        self.raw['data']['quality'] = 0
        self.raw['data']['quality_text'] = 'Poor'
        self.assertTrue(self.normalize(self.raw)['available'])
        for value in (None, True, float('nan'), -1, 2):
            self.raw['data']['quality'] = value
            self.assertFalse(self.normalize(self.raw)['available'])

    def test_mismatch_stale_missing_model_and_malformed_time_rejected(self):
        for section, key, value in [('data', 'type', 'sunset'), ('data', 'model_data', False),
                                    ('data', 'time', None), ('location', 'latitude', 41)]:
            raw = copy.deepcopy(self.raw)
            raw[section][key] = value
            self.assertFalse(self.normalize(raw)['available'])
        self.raw['time'] = (self.now - dt.timedelta(days=1)).isoformat()
        self.assertEqual(self.normalize(self.raw)['reason'], 'stale_response')

    def test_key_is_header_only_and_errors_do_not_leak_it(self):
        class Response:
            status_code = 401
        with patch.object(hue.requests, 'get', return_value=Response()) as get:
            row = hue.one(40, 116, self.event, self.target.isoformat(), self.now, 'test-private-key')
        kwargs = get.call_args.kwargs
        self.assertEqual(kwargs['headers']['x-api-key'], 'test-private-key')
        self.assertNotIn('key', kwargs['params'])
        self.assertEqual(kwargs['params']['date'], '2026-10-15')
        self.assertNotIn('test-private-key', str(row))

    def test_unconfigured_does_not_request_network(self):
        with patch.object(hue.requests, 'get') as get:
            row = hue.one(40, 116, self.event, self.target.isoformat(), self.now, None)
        get.assert_not_called()
        self.assertEqual(row['reason'], 'not_configured')

    def test_encrypted_storage_roundtrip(self):
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / 'test-key.dat'
            glow_credentials.save('test-private-key', path)
            self.assertNotIn(b'test-private-key', path.read_bytes())
            self.assertEqual(glow_credentials.load(path), 'test-private-key')
            self.assertIsNone(glow_credentials.load(path.with_name('missing')))

    def test_primary_result_and_preparation_times(self):
        row = self.normalize(self.raw)
        advice = glow_outlook.result(self.event, {'results': [row]}, language='zh', now=self.now)
        self.assertEqual(advice['source'], 'Sunsethue')
        self.assertIn('中烧候选', advice['summary'])
        self.assertIn('05:39', advice['plan'])
        self.assertIn('05:59', advice['plan'])
        self.assertIn('不是发生概率', advice['source_text'])

    def test_weather_alone_never_becomes_quality_and_fallback_is_named(self):
        advice = glow_outlook.result(self.event, now=self.now)
        self.assertIsNone(advice['category'])
        advice = glow_outlook.result(self.event, sb_data={'results': [
            {'event': self.event, 'available': True, 'quality': .5}]}, now=self.now)
        self.assertEqual(advice['source'], 'SunsetBot')
        self.assertIn('regional', advice['source_text'])

    def test_disagreement_does_not_recommend_special_trip(self):
        advice = glow_outlook.result(self.event, {'results': [self.normalize(self.raw)]},
            {'results': [{'event': self.event, 'available': True, 'quality': .073}]}, language='zh', now=self.now)
        self.assertIn('分歧', advice['summary'])
        self.assertNotIn('最晚', advice['plan'])

    def test_notification_leads_with_result_without_cloud_dump(self):
        data = {'results': [], 'sunsethue': {'results': [self.normalize(self.raw)]}}
        with patch.object(glow_notify.glow_location, 'load', return_value={'language': 'zh'}):
            _, content = glow_notify.message(data, self.event)
        self.assertIn('Sunsethue', content)
        self.assertNotIn('NOAA GFS cloud', content)


if __name__ == '__main__': unittest.main()
