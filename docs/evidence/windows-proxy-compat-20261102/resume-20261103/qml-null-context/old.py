
from PySide6.QtCore import QUrl, qVersion, QObject
from PySide6.QtGui import QGuiApplication
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtQml import QQmlEngine, QQmlComponent, QQmlExpression, qmlContext
app = QGuiApplication([])
engine = QQmlEngine()
component = QQmlComponent(engine)
component.setData(b"""import QtQuick
import QtQuick.Controls
Item {
    width: 300; height: 300
    ScrollView {
        objectName: "form"; anchors.fill: parent
        Item { implicitHeight: 600; width: 300 }
    }
}""", QUrl())
root = component.create()
assert root, component.errors()
form = root.findChild(QObject, "form")
viewport = form.property("contentItem")
print("Qt", qVersion(), "viewport type", type(viewport).__name__,
      "viewportContext", qmlContext(viewport),
      "rootContext", bool(qmlContext(root)), flush=True)
context = qmlContext(viewport)
expression = QQmlExpression(context, viewport, "contentY")
print("constructed", flush=True)
expression.setNotifyOnValueChanged(True)
value = expression.evaluate()
print("evaluated", value, "error", expression.hasError(), flush=True)
assert not expression.hasError()
assert value == (-0.0, False)
