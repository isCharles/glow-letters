"""Behaviour checks for public location and forecast claims."""
import datetime as dt
import io
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'src'))
import glow_location
import glow_map
import glow_app
import glow_notify
import sunsetbot


class FakeResponse:
    def raise_for_status(self):
        pass

    def json(self):
        return {'elements': [
            {'lat': 30.00007, 'lon': 120.00005, 'tags': {'name': 'Teaching building', 'building': 'university'}},
            {'lat': 30.00017, 'lon': 120.00015, 'tags': {'name': 'Dormitory 3', 'building': 'dormitory'}},
            {'lat': 30.00027, 'lon': 120.00025, 'tags': {'name': 'Some district', 'boundary': 'administrative'}},
            {'lat': 30.00037, 'lon': 120.00035, 'tags': {'name': 'Unnamed road', 'highway': 'residential'}},
        ]}


class FakePhotonResponse:
    def raise_for_status(self):
        pass

    def json(self):
        return {'features': [
            {'properties': {'name': 'Teaching building', 'osm_key': 'building', 'osm_value': 'university'},
             'geometry': {'coordinates': [120.00005, 30.00007]}},
            {'properties': {'name': 'Dormitory 3', 'osm_key': 'building', 'osm_value': 'dormitory'},
             'geometry': {'coordinates': [120.00015, 30.00017]}},
            {'properties': {'name': 'Some district', 'osm_key': 'boundary'},
             'geometry': {'coordinates': [120.00025, 30.00027]}},
        ]}


class LocationTests(unittest.TestCase):
    def test_nearby_places_are_named_features_not_districts(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(glow_location, 'CACHE', pathlib.Path(directory) / 'cache.json'), \
                 patch.object(glow_location.requests, 'get', return_value=FakePhotonResponse()):
                point = {'lat': 30.0, 'lon': 120.0}
                places = glow_location.nearby_places(point)
                self.assertEqual([p['name'] for p in places], ['Teaching building', 'Dormitory 3'])
                self.assertTrue(all('city' not in p for p in places))
                self.assertEqual(glow_location.nearby_places(point), places)

    def test_nearby_places_falls_back_to_overpass(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(glow_location, 'CACHE', pathlib.Path(directory) / 'cache.json'), \
                 patch.object(glow_location.requests, 'get', side_effect=requests.ConnectionError('Photon down')), \
                 patch.object(glow_location.requests, 'post', return_value=FakeResponse()):
                places = glow_location.nearby_places({'lat': 30.0, 'lon': 120.0})
                self.assertEqual([p['name'] for p in places], ['Teaching building', 'Dormitory 3'])

    def test_map_crop_marker_is_near_target_coordinate(self):
        source = Image.new('RGB', (1344, 1400), '#ffffff')
        buffer = io.BytesIO()
        source.save(buffer, format='JPEG')
        output = glow_map.crop_map(buffer.getvalue(), 30.0, 120.0)
        self.assertIsNotNone(output)
        cropped = Image.open(io.BytesIO(output))
        red_pixels = sum(1 for r, g, b in cropped.getdata() if r > 200 and g < 150 and b < 170)
        self.assertGreater(red_pixels, 10)
        self.assertIsNone(glow_map.crop_map(buffer.getvalue(), 51.5, -0.1))

    def test_zero_glow_is_valid_but_missing_glow_is_not(self):
        now = dt.datetime(2026, 10, 12, 15, tzinfo=sunsetbot.TZ)
        valid = {'status': 'ok', 'tb_quality': '0.0 (no glow)', 'tb_aod': '0.1',
                 'tb_event_time': '2026-10-12 17:40:00', 'display_model': 'GFS',
                 'display_city_name': '北京-海淀区', 'display_times_str': '2026101206z'}
        result = sunsetbot.normalize(valid, '北京-海淀区', 'GFS', 'set_1', now, 36)
        self.assertTrue(result['available'])
        self.assertEqual(result['quality'], 0.0)
        missing = sunsetbot.normalize(dict(valid, tb_quality=''), '北京-海淀区', 'GFS', 'set_1', now, 36)
        self.assertFalse(missing['available'])
        mismatch = sunsetbot.normalize(valid, '北京-海淀区', 'EC', 'set_1', now, 36)
        self.assertEqual(mismatch['reason'], 'response_mismatch')


class NotificationLinkTests(unittest.TestCase):
    def test_notification_links_select_matching_view(self):
        self.assertEqual(glow_app.event_from_open_url('glowletters://open?event=today-sunset'), 'today-sunset')
        self.assertEqual(glow_app.event_from_open_url('glowletters://open?event=tomorrow-sunrise'), 'tomorrow-sunrise')

    def test_other_links_are_rejected(self):
        for url in ('https://example.com/?event=today-sunset',
                    'glowletters://other?event=today-sunset',
                    'glowletters://open?event=unknown',
                    'glowletters://open?event=today-sunset&event=tomorrow-sunrise'):
            self.assertIsNone(glow_app.event_from_open_url(url))

    def test_toast_click_opens_matching_view(self):
        with patch.object(glow_notify, 'Notification') as notification, \
             patch.object(glow_notify.time, 'sleep'):
            glow_notify.notify('Tomorrow', 'Sunrise', 'tomorrow-sunrise')
        self.assertEqual(notification.call_args.kwargs['launch'],
                         'glowletters://open?event=tomorrow-sunrise')


if __name__ == '__main__':
    unittest.main()
