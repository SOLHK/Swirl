pragma ComponentBehavior: Bound
import QtQuick
import SwirlQuick

Item {
    id: graph
    property bool proxyOnly: false
    property var records: []
    property bool dirty: true
    readonly property var samples: records.filter(row => row.sampled)
    readonly property real maximumRate: Math.max(1, ...samples.map(row => row.value / 1800))
    readonly property real axisMaximum: samples.length ? maximumRate * 1.1 : 1

    function refresh() {
        if (!visible) return
        const next = engineController.telemetry.dailyTraffic(proxyOnly)
        if (JSON.stringify(next) !== JSON.stringify(records)) records = next
        dirty = false
    }

    onProxyOnlyChanged: { dirty = true; refresh() }
    onVisibleChanged: if (visible) refresh()
    Component.onCompleted: refresh()
    Connections { target: engineController.telemetry; function onChanged() { graph.dirty = true } }
    Timer { interval: 400; running: graph.visible && graph.dirty; repeat: true; onTriggered: graph.refresh() }

    Item {
        id: plot
        x: Theme.dp(58); y: Theme.dp(2)
        width: Math.max(0, graph.width - x - Theme.dp(2))
        height: Math.max(0, graph.height - Theme.dp(23))

        Repeater {
            model: 3
            Item {
                required property int index
                y: index * (plot.height - Theme.dp(1)) / 2
                width: plot.width; height: Theme.dp(1)
                Repeater {
                    model: Math.floor(parent.width / Theme.dp(5))
                    Rectangle {
                        required property int index
                        x: index * Theme.dp(5)
                        width: Theme.dp(2); height: Theme.dp(1)
                        color: Theme.border
                    }
                }
            }
        }
        Rectangle { width: Theme.dp(1); height: plot.height; color: Theme.border }

        Repeater {
            model: graph.records
            Rectangle {
                required property int index
                required property var modelData
                visible: modelData.sampled
                width: Theme.dp(5); height: width; radius: width / 2
                x: (index + 0.5) * plot.width / 48 - width / 2
                y: plot.height * (1 - modelData.value / 1800 / graph.axisMaximum) - height / 2
                color: Theme.cyan
                Accessible.ignored: true
            }
        }
    }

    Repeater {
        model: 3
        SwirlText {
            required property int index
            x: 0; y: index * plot.height / 2 - Theme.dp(7)
            width: Theme.dp(52); height: Theme.dp(15)
            horizontalAlignment: Text.AlignRight
            text: index === 2 ? "0 B/s" : graph.samples.length
                ? engineController.telemetry.formatBytes(graph.axisMaximum * (1 - index / 2)) + "/s" : "—"
            color: Theme.muted; font.pixelSize: Theme.fontSize(10)
        }
    }
    Repeater {
        model: ["12AM", "6AM", "12PM", "6PM"]
        SwirlText {
            required property int index
            required property string modelData
            x: plot.x + index * plot.width / 4 - (index === 0 ? 0 : Theme.dp(16))
            y: plot.y + plot.height + Theme.dp(5)
            width: Theme.dp(36); height: Theme.dp(16)
            text: modelData; color: Theme.muted; font.pixelSize: Theme.fontSize(10)
            horizontalAlignment: index === 0 ? Text.AlignLeft : Text.AlignHCenter
        }
    }
}
