import sys
import json
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineWidgets import QWebEngineView

app = QApplication(sys.argv)
view = QWebEngineView()
view.load(QUrl("https://lua.tools/"))

def on_load(ok):
    if not ok:
        print("Failed to load")
        app.quit()
        return

    js = """
    fetch('/api/manifest/check?appid=4108000')
        .then(r => r.text())
        .then(t => t)
        .catch(e => e.message);
    """
    def cb(res):
        print("Raw response:", res)
        app.quit()
        
    # Also check /api/steam/search?query=4108000
    js2 = """
    fetch('/api/steam/search?query=4108000')
        .then(r => r.text())
        .then(t => t)
        .catch(e => e.message);
    """
    def cb2(res):
        print("Search response:", res)
        view.page().runJavaScript(js, 0, cb)

    view.page().runJavaScript(js2, 0, cb2)

view.loadFinished.connect(on_load)
app.exec()
