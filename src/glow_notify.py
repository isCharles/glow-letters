"""Windows 消息通知入口；定时任务运行它，不打开完整窗口。"""
import argparse
import concurrent.futures
import datetime as dt
import json
import os
import pathlib
import sys
import time

from winotify import Notification, audio

import glow_location
import sunsetbot
import official_weather
import sunsethue
import glow_outlook


def message(data, event):
    now = dt.datetime.now(sunsetbot.TZ)
    date = now.date() + dt.timedelta(days=event.startswith('tomorrow'))
    language = glow_location.load().get('language', 'en')
    label = ('朝霞' if event.endswith('sunrise') else '晚霞') if language == 'zh' else ('sunrise' if event.endswith('sunrise') else 'sunset')
    title = (f'{date.month}月{date.day}日{label}来信' if language == 'zh' else
             f'{label.title()} letter · {date:%b %d}')
    official = data.get('official', {})
    solar = official.get('solar', {}).get(event)
    advice = glow_outlook.result(event, data.get('sunsethue'), data, solar, language, now)
    lines = [advice['summary'], advice['plan'], advice['source_text']]
    if solar:
        lines.append(('太阳时刻 ' if language == 'zh' else 'Sun event ') + solar[11:16])
    lines = [line for line in lines if line]
    return title, '\n'.join(lines)


def launch_uri(event):
    """Installed shortcuts preserve the event when a Windows toast is clicked."""
    if not getattr(sys, 'frozen', False):
        return ''
    name = 'Open Sunrise.lnk' if event == 'tomorrow-sunrise' else 'Open Sunset.lnk'
    shortcut = pathlib.Path(sys.executable).with_name(name)
    return shortcut.as_uri() if shortcut.is_file() else ''


def notify(title, content, event='today-sunset'):
    language = glow_location.load().get('language', 'en')
    toast = Notification(app_id='霞光来信' if language == 'zh' else 'Glow Letters',
                         title=title, msg=content, duration='long',
                         launch=launch_uri(event))
    toast.set_audio(audio.Default, loop=False)
    toast.show()
    time.sleep(2)


def run(event='today-sunset', test=False):
    if test:
        notify('Glow Letters · test / 霞光来信 · 测试', 'A little note from the sky. / 天空递来一封测试信。')
        return
    location = glow_location.load()
    city = location.get('city')
    has_coordinates = 'lat' in location and 'lon' in location
    if not city and not has_coordinates:
        return
    try:
        data = {'results': []}
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            sb = pool.submit(sunsetbot.fetch, city, [event], retry_count=0, request_timeout=(5, 10)) if city else None
            official = pool.submit(official_weather.fetch, location['lat'], location['lon'], [event]) if has_coordinates else None
            hue = pool.submit(sunsethue.fetch, location['lat'], location['lon'], [event]) if has_coordinates else None
            if sb:
                try: data = sb.result()
                except Exception: pass
            if official:
                try: data['official'] = official.result()
                except Exception as error: data['official'] = {'results': [], 'error': str(error)}
            if hue:
                try: data['sunsethue'] = hue.result()
                except Exception: data['sunsethue'] = {'results': []}
        logs = pathlib.Path(os.environ.get('LOCALAPPDATA', pathlib.Path.home())) / 'GlowLetters' / 'history'
        logs.mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now(sunsetbot.TZ).strftime('%Y%m%d-%H%M%S-%f')
        (logs / f'{stamp}-{event}.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        title, content = message(data, event)
    except Exception:
        language = glow_location.load().get('language', 'en')
        title, content = (('霞光来信 · 查询失败', '这次天空暂时没回信，打开软件可以重试。') if language == 'zh' else
                          ('Glow Letters · unavailable', 'The sky has not replied this time. Open the app to retry.'))
    notify(title, content, event)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--event', choices=['today-sunset', 'tomorrow-sunrise'], default='today-sunset')
    parser.add_argument('--test', action='store_true')
    args = parser.parse_args()
    run(args.event, args.test)


if __name__ == '__main__': main()
