"""Check actual GRIB semantics and independence from SunsetBot."""
import datetime as dt
import pathlib
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'src'))
import official_weather as weather
import glow_notify


class OfficialTests(unittest.TestCase):
    def grib(self, value=0):
        handle = weather.ec.codes_grib_new_from_samples('regular_ll_sfc_grib2')
        try:
            for key, item in [('centre', 'ecmf'), ('paramId', 164), ('dataDate', 20261014),
                              ('dataTime', 0), ('forecastTime', 9)]:
                weather.ec.codes_set(handle, key, item)
            count = weather.ec.codes_get(handle, 'numberOfPoints')
            weather.ec.codes_set_values(handle, [value] * count)
            return weather.ec.codes_get_message(handle)
        finally:
            weather.ec.codes_release(handle)

    def test_grib_zero_cloud_is_real_and_fraction_converts_to_percent(self):
        run = dt.datetime(2026, 10, 14, tzinfo=weather.UTC)
        valid = run + dt.timedelta(hours=9)
        zero, _ = weather.decode(self.grib(), 30, 10, run, valid)
        self.assertEqual(zero['cloud_total_pct'], 0)
        half, _ = weather.decode(self.grib(.5), 30, 10, run, valid)
        self.assertEqual(half['cloud_total_pct'], 50)

    def test_mismatched_grib_time_is_rejected(self):
        run = dt.datetime(2026, 10, 14, tzinfo=weather.UTC)
        with self.assertRaisesRegex(ValueError, 'mismatch'):
            weather.decode(self.grib(), 30, 10, run, run + dt.timedelta(hours=12))

    def test_solar_event_date_is_beijing_tomorrow_even_before_utc_midnight(self):
        now = dt.datetime(2026, 10, 13, 18, tzinfo=weather.UTC)
        times = weather.solar_events(40, 116, ['today-sunset', 'tomorrow-sunrise'], now)
        self.assertEqual(dt.datetime.fromisoformat(times['today-sunset']).date(), dt.date(2026, 10, 14))
        self.assertEqual(dt.datetime.fromisoformat(times['tomorrow-sunrise']).date(), dt.date(2026, 10, 15))

    def test_polar_day_has_no_fabricated_sunrise(self):
        now = dt.datetime(2026, 6, 21, tzinfo=weather.TZ)
        self.assertIsNone(weather.solar_events(89, 0, ['today-sunrise'], now)['today-sunrise'])

    def test_weather_only_notification_does_not_invent_glow_result(self):
        data = {'results': [], 'official': {'solar': {'today-sunset': '2026-10-14T17:37:00+08:00'},
                'results': [{'model': 'GFS', 'available': True, 'fields': {'cloud_total_pct': 0}}]}}
        with patch.object(glow_notify.glow_location, 'load', return_value={'language': 'en'}):
            _, message = glow_notify.message(data, 'today-sunset')
        self.assertIn('Cannot judge', message)
        self.assertNotIn('cloud 0%', message)
        self.assertIn('17:37', message)

    def test_ecmwf_full_file_response_is_rejected(self):
        class Index:
            text = '{"levtype":"sfc","param":"tcc","_offset":0,"_length":10}'
        class Full:
            status_code = 200
            content = b'GRIB123456'
            def close(self): pass
        with patch.object(weather, 'request', side_effect=[Index(), Full()]):
            with self.assertRaisesRegex(ValueError, 'byte range'):
                weather.ifs_bytes(dt.datetime(2026, 10, 14, tzinfo=weather.UTC), 9)

    def test_past_sunrise_never_uses_a_run_started_after_sunrise(self):
        now = dt.datetime(2026, 10, 14, 12, tzinfo=weather.UTC)
        target = '2026-10-14T06:24:00+08:00'
        with patch.object(weather, 'gfs_bytes', return_value=(b'GRIB', 'https://nomads.ncep.noaa.gov/', 200)), \
             patch.object(weather, 'decode', return_value=({'cloud_total_pct': 0}, {})):
            row = weather.model_forecast('GFS', 40, 116, 'today-sunrise', target, now)
        self.assertLessEqual(dt.datetime.fromisoformat(row['run_time']), dt.datetime.fromisoformat(target))
        self.assertLessEqual(abs(row['time_offset_minutes']), 30)


if __name__ == '__main__': unittest.main()
