"""Glow Letters desktop entry point and scheduled notification runner."""
import argparse
import sys
import json
import pathlib
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QApplication
from glow_qt import GlowWindow

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--event', choices=['today-sunset', 'tomorrow-sunrise'], default='today-sunset')
    parser.add_argument('--smoke-ui', action='store_true')
    parser.add_argument('--notify', action='store_true')
    parser.add_argument('--test-notification', action='store_true')
    parser.add_argument('--official-json', type=pathlib.Path, help='Write fresh official weather JSON without opening the app')
    parser.add_argument('--lat', type=float)
    parser.add_argument('--lon', type=float)
    args = parser.parse_args()
    if args.official_json:
        import glow_location
        import official_weather
        location = glow_location.load()
        lat = args.lat if args.lat is not None else location.get('lat')
        lon = args.lon if args.lon is not None else location.get('lon')
        if lat is None or lon is None:
            parser.error('Choose a location or provide --lat and --lon')
        data = official_weather.fetch(lat, lon, [args.event])
        args.official_json.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        return official_weather.exit_code(data)
    if args.notify or args.test_notification:
        import glow_notify
        glow_notify.run(args.event, test=args.test_notification)
        return
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv[:1])
    app.setStyle('Fusion')
    window = GlowWindow(args.event)
    window.show()
    if args.smoke_ui: QTimer.singleShot(3000, app.quit)
    sys.exit(app.exec_())

if __name__ == '__main__': sys.exit(main())
