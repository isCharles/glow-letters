"""Glow Letters desktop entry point and scheduled notification runner."""
import argparse
import sys
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QApplication
from glow_qt import GlowWindow

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--event', choices=['today-sunset', 'tomorrow-sunrise'], default='today-sunset')
    parser.add_argument('--smoke-ui', action='store_true')
    parser.add_argument('--notify', action='store_true')
    parser.add_argument('--test-notification', action='store_true')
    args = parser.parse_args()
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

if __name__ == '__main__': main()
