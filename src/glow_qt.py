"""Bilingual desktop forecast window for SunsetBot data."""
import datetime as dt
import io
import json
import os
import pathlib
import threading
from urllib.parse import urljoin, urlparse

import requests
from PIL import Image
from PyQt5.QtCore import QObject, Qt, QTimer, QUrl, pyqtSignal
from PyQt5.QtGui import QDesktopServices, QFont, QPixmap
from PyQt5.QtWidgets import (QComboBox, QDialog, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QMessageBox, QPushButton, QScrollArea, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget)
from PyQt5.QtWebEngineWidgets import QWebEngineView

import glow_location
import glow_map
from glow_i18n import tr
import sunsetbot

BASE = pathlib.Path(__file__).resolve().parent
DATA = pathlib.Path(os.environ.get('LOCALAPPDATA', pathlib.Path.home())) / 'GlowLetters' / 'history'


class Bridge(QObject):
    forecast = pyqtSignal(int, object)
    map = pyqtSignal(int, str, str, object)
    location = pyqtSignal(object)
    search = pyqtSignal(object)
    matched = pyqtSignal(object)


def official_map(day, kind, model):
    event = sunsetbot.EVENTS[f'{day}-{kind}']
    date = (dt.datetime.now(sunsetbot.TZ).date() + dt.timedelta(days=day == 'tomorrow')).strftime('%Y%m%d')
    response = requests.get('https://sunsetbot.top/map/', params={
        'region':'中东', 'event':event, 'intend':'select_region',
        'query_id':str(int(dt.datetime.now().timestamp())), 'model':model}, timeout=20)
    response.raise_for_status()
    path = response.json().get('map_img_src', '')
    parsed = urlparse(urljoin('https://sunsetbot.top/', path))
    if parsed.hostname not in ('sunsetbot.top', 'www.sunsetbot.top') or f'/{model}_中东_{date}_' not in parsed.path or ('_rise_' if kind == 'sunrise' else '_set_') not in parsed.path:
        raise ValueError('官方地图暂无当前日期数据')
    secure = urljoin('https://sunsetbot.top/', path)
    result = {'url': secure, 'image': None}
    try:
        image = requests.get(secure, timeout=20)
        if image.status_code == 567:
            image = requests.get(secure.replace('https://', 'http://', 1),
                headers={'Referer':'http://sunsetbot.top/map/', 'User-Agent':'Mozilla/5.0'}, timeout=20)
        image.raise_for_status()
        if not image.headers.get('Content-Type', '').startswith('image/') or len(image.content) > 10_000_000:
            raise ValueError('地图响应不是图片')
        check = Image.open(io.BytesIO(image.content))
        check.verify()
        result['image'] = image.content
    except (requests.RequestException, ValueError, OSError) as error:
        result['error'] = str(error)
    return result


def label(text='', size=11, bold=False, color='#edf4fb'):
    item = QLabel(text)
    item.setFont(QFont('Microsoft YaHei UI', size, QFont.DemiBold if bold else QFont.Normal))
    item.setStyleSheet(f'color:{color}; background:transparent;')
    return item


class GlowWindow(QWidget):
    def __init__(self, event):
        super().__init__()
        self.day = 'tomorrow' if event.startswith('tomorrow') else 'today'
        self.model = 'GFS'
        self.location = glow_location.load()
        self.language = self.location.get('language', 'en')
        self.data = None
        self.maps_data = {}
        self.generation = 0
        self.bridge = Bridge()
        self.bridge.forecast.connect(self.on_forecast)
        self.bridge.map.connect(self.on_map)
        self.bridge.location.connect(self.on_location)
        self.bridge.matched.connect(self.on_matched)
        self.setWindowTitle(tr(self.language, 'app') + ' · SunsetBot')
        self.resize(940, 790)
        self.setMinimumSize(800, 650)
        self.setStyleSheet('''
          QWidget { background:#0e1a2a; color:#eff5fb; }
          QFrame#card, QFrame#mapbox, QFrame#clockbox { background:#1b2e45; border:1px solid #35506a; border-radius:13px; }
          QComboBox, QPushButton, QLineEdit { background:#294563; border:1px solid #53718d; border-radius:8px; color:white; padding:8px 12px; font:11pt 'Microsoft YaHei UI'; }
          QComboBox:hover, QPushButton:hover { background:#395b7d; }
          QPushButton#primary { background:#f0b680; color:#162337; border:none; font-weight:600; }
          QComboBox QAbstractItemView { background:#294563; color:white; selection-background-color:#587fa6; }
          QScrollArea { border:none; }
        ''')
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(16)
        head = QHBoxLayout()
        self.app_title = label(tr(self.language, 'app'), 24, True)
        head.addWidget(self.app_title)
        head.addStretch()
        self.location_label = label('', 10, color='#b2c6d9')
        head.addWidget(self.location_label)
        layout.addLayout(head)
        self.subtitle = label(tr(self.language, 'subtitle'), 10, color='#92afc9')
        layout.addWidget(self.subtitle)
        self.coordinate_label = label('', 10, color='#a8c1d8')
        layout.addWidget(self.coordinate_label)
        controls = QHBoxLayout()
        controls.setSpacing(10)
        self.day_select = QComboBox()
        self.day_select.addItems([tr(self.language, 'today'), tr(self.language, 'tomorrow')])
        self.day_select.setCurrentIndex(self.day == 'tomorrow')
        self.day_select.currentIndexChanged.connect(self.change_day)
        self.model_select = QComboBox()
        self.model_select.addItems(['GFS', 'EC'])
        self.model_select.currentTextChanged.connect(self.change_model)
        self.language_select = QComboBox()
        self.language_select.addItems(['English', '中文'])
        self.language_select.setCurrentIndex(1 if self.language == 'zh' else 0)
        controls.addWidget(self.day_select)
        controls.addWidget(self.model_select)
        controls.addWidget(self.language_select)
        controls.addStretch()
        self.action_buttons = {}
        for key, action, primary in [('locate', self.get_location, False), ('search', self.search_location, False), ('refresh', self.query, True)]:
            button = QPushButton(tr(self.language, key))
            if primary: button.setObjectName('primary')
            button.clicked.connect(action)
            controls.addWidget(button)
            self.action_buttons[key] = button
        layout.addLayout(controls)
        clock_frame = QFrame(objectName='clockbox')
        clock_layout = QVBoxLayout(clock_frame)
        clock_layout.setContentsMargins(20, 15, 20, 15)
        self.clock = label('', 17, True)
        clock_layout.addWidget(self.clock)
        layout.addWidget(clock_frame)
        self.cards = {}
        for kind in ('sunrise', 'sunset'):
            card = QFrame(objectName='card')
            box = QVBoxLayout(card)
            box.setContentsMargins(20, 15, 20, 17)
            box.setSpacing(2)
            title = label('', 16, True)
            box.addWidget(title)
            box.addSpacing(8)
            fields = {}
            names = ['time', 'remaining_' + kind, 'quality', 'aod']
            for index, name in enumerate(names):
                row = QFrame()
                row.setStyleSheet('background:' + ('#263f5a' if index % 2 else '#223750') + '; border-radius:4px;')
                line = QHBoxLayout(row)
                line.setContentsMargins(16, 8, 16, 8)
                row_label = label(tr(self.language, name), 11, color='#c2d1e0')
                line.addWidget(row_label)
                line.addStretch()
                value = label(tr(self.language, 'loading'), 12, True)
                line.addWidget(value)
                fields[name] = (row_label, value)
                box.addWidget(row)
            self.cards[kind] = (title, fields)
            layout.addWidget(card)
        maps_frame = QFrame(objectName='mapbox')
        map_line = QHBoxLayout(maps_frame)
        map_line.setContentsMargins(18, 16, 18, 16)
        map_line.setSpacing(18)
        self.map_labels = {}
        self.map_stacks = {}
        self.map_browsers = {}
        self.browser_urls = {}
        self.map_urls = {}
        self.map_captions = {}
        for kind in ('sunrise', 'sunset'):
            column = QVBoxLayout()
            image = label(tr(self.language, 'map_loading'), 11, color='#b9cadd')
            image.setAlignment(Qt.AlignCenter)
            image.setMinimumHeight(218)
            image.setStyleSheet('background:#29425e; border-radius:8px; color:#b9cadd;')
            stack = QStackedWidget()
            stack.setFixedHeight(218)
            stack.setMinimumWidth(0)
            stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            stack.addWidget(image)
            browser = QWebEngineView()
            browser.setMinimumWidth(0)
            browser.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
            browser.setContextMenuPolicy(Qt.NoContextMenu)
            browser.loadFinished.connect(lambda ok, k=kind: self.on_browser_map_loaded(k, ok))
            stack.addWidget(browser)
            column.addWidget(stack)
            caption = label(tr(self.language, 'map_' + kind), 11, color='#b9cadd')
            caption.setAlignment(Qt.AlignCenter)
            column.addWidget(caption)
            self.map_captions[kind] = caption
            url_line = QLineEdit()
            url_line.setReadOnly(True)
            url_line.setPlaceholderText(tr(self.language, 'map_url'))
            url_line.setToolTip(tr(self.language, 'map_url'))
            url_row = QHBoxLayout()
            url_row.addWidget(url_line)
            open_button = QPushButton(tr(self.language, 'open'))
            open_button.clicked.connect(lambda _, field=url_line: QDesktopServices.openUrl(QUrl(field.text())) if field.text() else None)
            url_row.addWidget(open_button)
            column.addLayout(url_row)
            self.map_urls[kind] = url_line
            map_line.addLayout(column)
            self.map_labels[kind] = image
            self.map_stacks[kind] = stack
            self.map_browsers[kind] = browser
        layout.addWidget(maps_frame)
        self.status = label('', 9, color='#a8bed3')
        layout.addWidget(self.status)
        self.note = label(tr(self.language, 'disclaimer') + '\n' + tr(self.language, 'map_note'), 9, color='#8da7bd')
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        self.attribution = label(tr(self.language, 'attribution'), 9, color='#8da7bd')
        self.attribution.setWordWrap(True)
        layout.addWidget(self.attribution)
        self.language_select.currentIndexChanged.connect(self.change_language)
        self.update_location_label()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(1000)
        self.tick()
        self.query()

    def change_day(self, index):
        self.day = 'tomorrow' if index else 'today'
        self.query()

    def change_language(self, index):
        self.language = 'zh' if index else 'en'
        self.location['language'] = self.language
        glow_location.save(self.location)
        self.setWindowTitle(tr(self.language, 'app') + ' · SunsetBot')
        self.app_title.setText(tr(self.language, 'app'))
        self.subtitle.setText(tr(self.language, 'subtitle'))
        for index, key in enumerate(('today', 'tomorrow')):
            self.day_select.setItemText(index, tr(self.language, key))
        for key, button in self.action_buttons.items():
            button.setText(tr(self.language, key))
        for kind, (_, fields) in self.cards.items():
            for key, (row_label, _) in fields.items():
                row_label.setText(tr(self.language, key))
            self.map_captions[kind].setText(tr(self.language, 'map_' + kind))
        self.note.setText(tr(self.language, 'disclaimer') + '\n' + tr(self.language, 'map_note'))
        self.attribution.setText(tr(self.language, 'attribution'))
        self.update_location_label()
        self.render()
        self.render_maps()
        self.tick()

    def update_location_label(self):
        place = self.location.get('name') or tr(self.language, 'select_location')
        self.location_label.setText(place)
        if 'lat' in self.location and 'lon' in self.location:
            detail = f"{tr(self.language, 'selected')}: {self.location['lat']:.6f}°, {self.location['lon']:.6f}°"
            accuracy = self.location.get('accuracy')
            if isinstance(accuracy, (int, float)) and self.location.get('source') == 'Windows':
                detail += '  ·  ' + tr(self.language, 'accuracy', metres=accuracy)
            detail += '  ·  ' + tr(self.language, 'forecast_area') + ': ' + (self.location.get('city') or '—')
            self.coordinate_label.setText(detail)
        else:
            self.coordinate_label.setText(tr(self.language, 'select_location'))

    def change_model(self, model):
        self.model = model
        self.render()
        self.render_maps()

    def query(self):
        if not self.location.get('city'):
            self.status.setText(tr(self.language, 'select_location'))
            self.render()
            self.render_maps()
            return
        self.generation += 1
        generation = self.generation
        day, city = self.day, self.location['city']
        self.data = None
        self.maps_data = {}
        self.status.setText(tr(self.language, 'querying'))
        self.render()
        self.render_maps()
        def forecast_worker():
            try:
                data = sunsetbot.fetch(city=city, events=[f'{day}-sunrise', f'{day}-sunset'])
                DATA.mkdir(parents=True, exist_ok=True)
                stamp = dt.datetime.now(sunsetbot.TZ).strftime('%Y%m%d-%H%M%S-%f')
                (DATA / f'{stamp}-{day}.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
                self.bridge.forecast.emit(generation, data)
            except Exception as error: self.bridge.forecast.emit(generation, str(error))
        threading.Thread(target=forecast_worker, daemon=True).start()
        for model in ('GFS', 'EC'):
            for kind in ('sunrise', 'sunset'):
                def map_worker(m=model, k=kind):
                    try: data = official_map(day, k, m)
                    except Exception as error: data = str(error)
                    self.bridge.map.emit(generation, m, k, data)
                threading.Thread(target=map_worker, daemon=True).start()

    def on_forecast(self, generation, result):
        if generation != self.generation: return
        if isinstance(result, dict):
            self.data = result
            self.status.setText(tr(self.language, 'updated') + ' ' + result['fetched_at'].replace('T', ' ')[:19] + '  ·  SunsetBot')
        else: self.status.setText(tr(self.language, 'query_failed') + result)
        self.render()

    def on_map(self, generation, model, kind, result):
        if generation == self.generation:
            self.maps_data[(model, kind)] = result
            self.render_maps()

    def render_maps(self):
        for kind, widget in self.map_labels.items():
            stack = self.map_stacks[kind]
            result = self.maps_data.get((self.model, kind))
            image_bytes = (result.get('crop_image') or result.get('image')) if isinstance(result, dict) else None
            url = result.get('url', '') if isinstance(result, dict) else ''
            self.map_urls[kind].setText(url)
            if isinstance(image_bytes, bytes):
                if not result.get('crop_image') and 'lat' in self.location and 'lon' in self.location:
                    image_bytes = glow_map.crop_map(image_bytes, self.location['lat'], self.location['lon'])
                    if image_bytes is None:
                        widget.setPixmap(QPixmap())
                        widget.setText(tr(self.language, 'map_outside'))
                        stack.setCurrentWidget(widget)
                        continue
                pixmap = QPixmap()
                if pixmap.loadFromData(image_bytes):
                    stack.setCurrentWidget(widget)
                    widget.setPixmap(pixmap.scaled(400, 218, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                    widget.setText('')
                    continue
            widget.setPixmap(QPixmap())
            widget.setText(tr(self.language, 'map_unavailable') if result is not None else
                           tr(self.language, 'no_map_coords') if not self.location.get('city') else
                           tr(self.language, 'map_loading'))
            if url:
                browser = self.map_browsers[kind]
                if self.browser_urls.get(kind) != url:
                    self.browser_urls[kind] = url
                    browser.load(QUrl(url))
                stack.setCurrentWidget(browser)
            else:
                stack.setCurrentWidget(widget)

    def on_browser_map_loaded(self, kind, ok):
        if not ok:
            self.map_stacks[kind].setCurrentWidget(self.map_labels[kind])
            self.map_labels[kind].setText(tr(self.language, 'map_unavailable'))
            return
        url = self.browser_urls.get(kind)
        model = self.model
        result = self.maps_data.get((model, kind))
        if not isinstance(result, dict) or result.get('url') != url:
            return
        def measured(size):
            if not isinstance(size, list) or len(size) != 2 or not all(isinstance(n, (int, float)) and n > 0 for n in size):
                self.map_stacks[kind].setCurrentWidget(self.map_labels[kind])
                self.map_labels[kind].setText(tr(self.language, 'map_unavailable'))
                return
            if 'lat' not in self.location or 'lon' not in self.location:
                return
            geometry = glow_map.crop_geometry(self.location['lat'], self.location['lon'], *size)
            if geometry is None:
                self.map_stacks[kind].setCurrentWidget(self.map_labels[kind])
                self.map_labels[kind].setText(tr(self.language, 'map_outside'))
                return
            left, top, right, bottom, cx, cy = geometry
            # Reposition the image already loaded by Chromium. Drawing it to a
            # canvas can fail for image-document security origins.
            script = f'''(() => {{
              try {{
                const img = document.images[0];
                if (!img) return false;
                const width = {right-left}, height = {bottom-top};
                const scale = Math.min(innerWidth / width, innerHeight / height);
                const frame = document.createElement('div');
                frame.style.cssText = `position:relative;overflow:hidden;width:${{width*scale}}px;height:${{height*scale}}px;margin:auto;background:white`;
                img.remove(); frame.appendChild(img);
                document.body.replaceChildren(frame);
                document.documentElement.style.cssText = 'margin:0;padding:0;background:#29425e';
                document.body.style.cssText = 'margin:0;padding:0;background:#29425e;display:flex;align-items:center;justify-content:center;min-height:100vh';
                for (const [key,value] of Object.entries({{
                  position:'absolute',left:`${{-left*scale}}px`,top:`${{-top*scale}}px`,
                  width:`${{img.naturalWidth*scale}}px`,height:`${{img.naturalHeight*scale}}px`,
                  'max-width':'none','max-height':'none',transform:'none',margin:'0'
                }})) img.style.setProperty(key,value,'important');
                const cx = {cx:.2f}, cy = {cy:.2f};
                const marker = document.createElement('div');
                marker.style.cssText = `position:absolute;left:${{(cx-left)*scale-7}}px;top:${{(cy-top)*scale-7}}px;width:14px;height:14px;border:3px solid white;border-radius:50%;background:#e95464;box-sizing:border-box`;
                frame.appendChild(marker);
                return true;
              }} catch (error) {{ return false; }}
            }})()'''
            def cropped(success):
                current = self.maps_data.get((model, kind))
                if model != self.model or not isinstance(current, dict) or current.get('url') != url:
                    return
                if not success:
                    self.map_stacks[kind].setCurrentWidget(self.map_labels[kind])
                    self.map_labels[kind].setText(tr(self.language, 'map_unavailable'))
            self.map_browsers[kind].page().runJavaScript(script, cropped)
        self.map_browsers[kind].page().runJavaScript(
            'document.contentType.startsWith("image/") && document.images[0] ? [document.images[0].naturalWidth, document.images[0].naturalHeight] : null', measured)

    def rows(self):
        return {row['event']: row for row in (self.data or {}).get('results', []) if row['model'] == self.model}

    def render(self):
        rows = self.rows()
        for kind, (title, fields) in self.cards.items():
            title.setText(tr(self.language, self.day) + ' · ' + tr(self.language, kind) + ' · ' + self.model)
            row = rows.get(f'{self.day}-{kind}')
            valid = bool(row and row.get('available'))
            raw = row.get('raw', {}) if valid else {}
            placeholder = (tr(self.language, 'select_location') if not self.location.get('city') else
                           tr(self.language, 'missing') if self.data else tr(self.language, 'loading'))
            time = placeholder
            if valid:
                center = dt.datetime.fromisoformat(row['event_time'])
                before, after = (15, 5) if kind == 'sunrise' else (5, 15)
                time = (center - dt.timedelta(minutes=before)).strftime('%H:%M:%S') + ' ~ ' + (center + dt.timedelta(minutes=after)).strftime('%H:%M:%S')
            fields['time'][1].setText(time)
            quality_text = raw.get('tb_quality')
            aod_text = raw.get('tb_aod')
            fields['quality'][1].setText(str(quality_text) if quality_text is not None else placeholder)
            fields['aod'][1].setText(str(aod_text) if aod_text is not None else placeholder)
            aod = row.get('aod') if valid else None
            color = '#ff8b88' if aod is not None and aod >= 1 else '#efbd86' if aod is not None and aod >= .5 else '#f1f5fb'
            fields['aod'][1].setStyleSheet(f'color:{color}; background:transparent;')
        self.tick()

    def tick(self):
        now = dt.datetime.now(sunsetbot.TZ)
        self.clock.setText(tr(self.language, 'beijing_time') + '   ' + now.strftime('%Y / %m / %d     %H:%M:%S'))
        rows = self.rows()
        for kind, (_, fields) in self.cards.items():
            row = rows.get(f'{self.day}-{kind}')
            text = '—'
            if row and row.get('available'):
                seconds = int((dt.datetime.fromisoformat(row['event_time']) - now).total_seconds())
                text = tr(self.language, 'passed') if seconds < 0 else f'{seconds//3600:02d}:{seconds//60%60:02d}:{seconds%60:02d}'
            fields['remaining_' + kind][1].setText(text)

    def get_location(self):
        self.status.setText(tr(self.language, 'finding'))
        def worker():
            try:
                point = glow_location.locate()
                self.bridge.location.emit({'point': point, 'pending_nearby': True})
            except Exception as error: self.bridge.location.emit(str(error))
        threading.Thread(target=worker, daemon=True).start()

    def fetch_nearby(self, point):
        def worker():
            try:
                options = glow_location.nearby_places(point)
                error = None
            except Exception as failure:
                options, error = [], str(failure)
            self.bridge.location.emit({'point': point, 'options': options, 'error': error})
        threading.Thread(target=worker, daemon=True).start()

    def on_location(self, result):
        if isinstance(result, dict):
            if result.get('pending_nearby'):
                point = result['point']
                box = QMessageBox(self)
                box.setWindowTitle(tr(self.language, 'nearby_privacy_title'))
                box.setText(tr(self.language, 'nearby_privacy'))
                proceed = box.addButton(tr(self.language, 'continue'), QMessageBox.AcceptRole)
                box.addButton(tr(self.language, 'coordinate_only'), QMessageBox.RejectRole)
                box.exec_()
                if box.clickedButton() != proceed:
                    self.choose_nearby(point, [], error='declined')
                    return
                self.status.setText(tr(self.language, 'finding'))
                self.fetch_nearby(point)
                return
            self.choose_nearby(result['point'], result['options'], result.get('error'))
            return
        box = QMessageBox(self)
        box.setWindowTitle(tr(self.language, 'location_unavailable'))
        box.setText(result)
        settings = box.addButton(tr(self.language, 'settings'), QMessageBox.ActionRole)
        box.addButton(tr(self.language, 'ok'), QMessageBox.AcceptRole)
        box.exec_()
        if box.clickedButton() == settings: QDesktopServices.openUrl(QUrl('ms-settings:privacy-location'))
        self.status.setText(tr(self.language, 'location_unavailable'))

    def choose_nearby(self, point, options, error=None):
        dialog = QDialog(self)
        dialog.setWindowTitle(tr(self.language, 'location_dialog'))
        dialog.resize(670, 460)
        box = QVBoxLayout(dialog)
        box.setContentsMargins(24, 22, 24, 22)
        box.setSpacing(12)
        box.addWidget(label(tr(self.language, 'current_position'), 17, True))
        detail = f"{point['lat']:.6f}°, {point['lon']:.6f}°"
        if isinstance(point.get('accuracy'), (int, float)):
            detail += '  ·  ' + tr(self.language, 'accuracy', metres=point['accuracy'])
        box.addWidget(label(detail, 11, color='#b9cadb'))
        box.addWidget(label(tr(self.language, 'nearby_prompt'), 12, True))
        places = QListWidget()
        places.setStyleSheet('background:#263d58; color:white; font:11pt "Microsoft YaHei UI"; border-radius:8px;')
        for item in options:
            places.addItem(f"{item['name']}    ·    {tr(self.language, 'distance', metres=item['distance_m'])}")
        if options:
            places.setCurrentRow(0)
        else:
            notice_key = 'nearby_skipped' if error == 'declined' else 'nearby_error' if error else 'nearby_empty'
            notice = label(tr(self.language, notice_key), 10, color='#efbd86')
            notice.setWordWrap(True)
            box.addWidget(notice)
        box.addWidget(places)
        explanation = label(tr(self.language, 'location_note'), 9, color='#91a9bf')
        explanation.setWordWrap(True)
        box.addWidget(explanation)
        buttons = QHBoxLayout()
        cancel = QPushButton(tr(self.language, 'cancel'))
        cancel.clicked.connect(dialog.reject)
        buttons.addWidget(cancel)
        use_position = QPushButton(tr(self.language, 'use_position'))
        use_position.clicked.connect(lambda: (places.setCurrentRow(-1), dialog.accept()))
        buttons.addWidget(use_position)
        use = QPushButton(tr(self.language, 'use_place'))
        use.setObjectName('primary')
        use.setEnabled(bool(options))
        use.clicked.connect(dialog.accept)
        buttons.addWidget(use)
        box.addLayout(buttons)
        if dialog.exec_() != QDialog.Accepted: return
        index = places.currentRow()
        chosen = dict(options[index]) if index >= 0 else dict(point)
        if index >= 0 and point.get('accuracy'):
            chosen['position_accuracy'] = point['accuracy']
        self.use_place(chosen)

    def use_place(self, point):
        self.status.setText(tr(self.language, 'matching'))
        def worker():
            try:
                self.bridge.matched.emit(glow_location.match(point))
            except Exception as error:
                self.bridge.matched.emit(str(error))
        threading.Thread(target=worker, daemon=True).start()

    def on_matched(self, result):
        if not isinstance(result, dict):
            self.status.setText(tr(self.language, 'query_failed') + result)
            return
        result['language'] = self.language
        glow_location.save(result)
        self.location = result
        self.update_location_label()
        self.query()

    def search_location(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(tr(self.language, 'search_title'))
        dialog.resize(700, 420)
        box = QVBoxLayout(dialog)
        box.setContentsMargins(22, 20, 22, 20)
        box.addWidget(label(tr(self.language, 'search_title'), 16, True))
        entry = QLineEdit()
        entry.setPlaceholderText(tr(self.language, 'search_hint'))
        box.addWidget(entry)
        results = QListWidget()
        results.setStyleSheet('background:#263d58; color:white; font:11pt "Microsoft YaHei UI";')
        box.addWidget(results)
        search_button = QPushButton(tr(self.language, 'search'))
        box.addWidget(search_button)
        choose_button = QPushButton(tr(self.language, 'use_place'))
        choose_button.setObjectName('primary')
        box.addWidget(choose_button)
        choices = []
        def on_result(value):
            search_button.setEnabled(True)
            choices.clear()
            results.clear()
            if isinstance(value, list):
                choices.extend(value)
                for place in value: results.addItem(place['name'])
                if not value: results.addItem(tr(self.language, 'no_places'))
            else: results.addItem(tr(self.language, 'search_failed') + value)
        self.bridge.search.connect(on_result)
        def search():
            term = entry.text().strip()
            if not term: return
            search_button.setEnabled(False)
            results.clear()
            results.addItem(tr(self.language, 'searching'))
            def worker():
                try: self.bridge.search.emit(glow_location.search(term))
                except Exception as error: self.bridge.search.emit(str(error))
            threading.Thread(target=worker, daemon=True).start()
        search_button.clicked.connect(search)
        entry.returnPressed.connect(search)
        def choose():
            index = results.currentRow()
            if 0 <= index < len(choices):
                place = choices[index]
                dialog.accept()
                self.use_place(place)
        choose_button.clicked.connect(choose)
        results.itemDoubleClicked.connect(lambda _:choose())
        dialog.exec_()
        try: self.bridge.search.disconnect(on_result)
        except TypeError: pass
