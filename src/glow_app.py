"""Glow Letters desktop entry point and scheduled notification runner."""
import argparse
import sys
from urllib.parse import parse_qs, urlparse
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QApplication
from glow_qt import GlowWindow


def event_from_open_url(value):
    """Accept only this app's notification links and known forecast events."""
    parsed = urlparse(value)
    if parsed.scheme != 'glowletters' or parsed.netloc != 'open' or parsed.path not in ('', '/'):
        return None
    event = parse_qs(parsed.query).get('event', [])
    if len(event) != 1 or event[0] not in ('today-sunset', 'tomorrow-sunrise'):
        return None
    return event[0]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--event', choices=['today-sunset', 'tomorrow-sunrise'], default='today-sunset')
    parser.add_argument('--smoke-ui', action='store_true')
    parser.add_argument('--notify', action='store_true')
    parser.add_argument('--test-notification', action='store_true')
    parser.add_argument('--open-url', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.notify or args.test_notification:
        import glow_notify
        glow_notify.run(args.event, test=args.test_notification)
        return
    if args.open_url:
        event = event_from_open_url(args.open_url)
        if event is None:
            parser.error('invalid notification link')
        args.event = event
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv[:1])
    app.setStyle('Fusion')
    window = GlowWindow(args.event)
    window.show()
    if args.smoke_ui: QTimer.singleShot(3000, app.quit)
    sys.exit(app.exec_())

if __name__ == '__main__': main()
