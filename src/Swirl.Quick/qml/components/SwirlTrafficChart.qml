pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import SwirlQuick

Item {
    id: graph
    property bool updatesEnabled: true
    property bool showUpload: false
    property bool showDownload: true
    property string series: showDownload ? "down" : "up"
    property int rangeIndex: 0
    property int axisFontSize: Theme.fontSize(12)
    property var points: []
    property bool componentReady: false
    property real endTime: Date.now()
    readonly property int rangeSeconds: [60, 60, 300, 3600][rangeIndex]
    readonly property real startTime: endTime - rangeSeconds * 1000
    readonly property var samples: points.map(point => point.value)
    readonly property real maximum: Math.max(1, ...samples)
    readonly property var axisLabels: [0, 1, 2, 3].map(index => points.length
        ? engineController.telemetry.formatBytes(maximum * (1 - index / 3)) + "/s" : "—")
    readonly property real axisWidth: {
        axisMetrics.font
        return Math.ceil(axisLabels.reduce((result, label) =>
            Math.max(result, axisMetrics.advanceWidth(label)), 0)) + Theme.dp(10)
    }
    readonly property int timeTicks: plot.width < Theme.dp(300) ? 3 : 5
    readonly property int hoveredIndex: hover.containsMouse && plot.width > 0
        ? nearestIndex(hover.mouseX / plot.width) : -1
    readonly property color seriesColor: series === "up" ? Theme.green : series === "total" ? Theme.muted : Theme.accent
    implicitHeight: Theme.dp(130)
    implicitWidth: Theme.dp(550)

    function refresh() {
        if (!componentReady || !visible || !updatesEnabled) return
        endTime = Date.now()
        points = engineController.telemetry.historyPoints(series, rangeSeconds)
        repaint()
    }
    function repaint() {
        if (componentReady && visible && Window.window && Window.window.visibility !== Window.Minimized) plot.requestPaint()
    }
    function nearestIndex(fraction) {
        const time = startTime + fraction * (endTime - startTime)
        let nearest = -1, distance = 3000
        for (let index = 0; index < points.length; ++index) {
            const difference = Math.abs(points[index].time - time)
            if (difference < distance) { distance = difference; nearest = index }
        }
        return nearest
    }
    function pointX(index) {
        return Math.max(0, Math.min(plot.width, (points[index].time - startTime) * plot.width / (endTime - startTime)))
    }
    function pointY(index) { return Math.max(0, plot.height - Theme.dp(1)) * (1 - points[index].value / maximum) }
    function timeLabel(index) {
        if (index === timeTicks - 1) return qsTr("现在")
        const seconds = Math.round(rangeSeconds * (1 - index / (timeTicks - 1)))
        return seconds >= 60 ? qsTr("%1分钟前").arg(seconds / 60) : qsTr("%1秒前").arg(seconds)
    }
    onVisibleChanged: if (visible) refresh()
    onUpdatesEnabledChanged: if (updatesEnabled) refresh()
    onSeriesChanged: refresh()
    onRangeIndexChanged: refresh()
    onPointsChanged: repaint()
    onSeriesColorChanged: repaint()
    Component.onCompleted: { componentReady = true; refresh() }
    Timer { interval: 1000; running: graph.visible && graph.updatesEnabled; repeat: true; onTriggered: graph.refresh() }
    Connections { target: Theme; function onDarkChanged() { graph.repaint() } function onIncreaseContrastChanged() { graph.repaint() } }
    FontMetrics {
        id: axisMetrics
        font.family: Theme.fontFamily; font.pixelSize: graph.axisFontSize
        font.weight: Theme.bodyFontWeight; font.features: ({"tnum": 1})
        font.hintingPreference: Font.PreferFullHinting
    }

    Repeater {
        model: 4
        SwirlText {
            required property int index
            x: 0; y: plot.y + index * (plot.height - Theme.dp(1)) / 3 - implicitHeight / 2
            width: Math.max(0, graph.axisWidth - Theme.dp(10))
            text: graph.axisLabels[index]
            tabularFigures: true; color: Theme.muted; font.pixelSize: graph.axisFontSize
            horizontalAlignment: Text.AlignRight
        }
    }
    Canvas {
        id: plot
        x: graph.axisWidth; y: Theme.dp(10)
        width: Math.max(0, graph.width - x - Theme.dp(4))
        height: Math.max(0, graph.height - y - Theme.dp(26))
        onWidthChanged: graph.repaint()
        onHeightChanged: graph.repaint()
        onPaint: {
            const context = getContext("2d")
            context.reset()
            const w = width, h = Math.max(0, height - Theme.dp(1)), points = graph.points
            context.strokeStyle = Theme.chartGrid
            context.lineWidth = Theme.dp(1)
            for (let row = 0; row < 4; ++row) {
                context.beginPath(); context.moveTo(0, row * h / 3); context.lineTo(w, row * h / 3); context.stroke()
            }
            if (!points.length) return
            const fill = context.createLinearGradient(0, 0, 0, h)
            fill.addColorStop(0, Theme.withAlpha(graph.seriesColor, 0.22))
            fill.addColorStop(1, Theme.withAlpha(graph.seriesColor, 0.03))
            function trace(first, last) {
                context.moveTo(graph.pointX(first), graph.pointY(first))
                for (let index = first + 1; index <= last; ++index)
                    context.lineTo(graph.pointX(index), graph.pointY(index))
            }
            for (let first = 0; first < points.length;) {
                let last = first
                while (last + 1 < points.length && points[last + 1].time - points[last].time <= 6000) ++last
                if (last === first) {
                    context.beginPath(); context.arc(graph.pointX(first), graph.pointY(first), Theme.dp(2), 0, Math.PI * 2)
                    context.fillStyle = graph.seriesColor; context.fill()
                } else {
                    context.beginPath(); trace(first, last)
                    context.lineTo(graph.pointX(last), h); context.lineTo(graph.pointX(first), h); context.closePath()
                    context.fillStyle = fill; context.fill()
                    context.beginPath(); trace(first, last)
                    context.strokeStyle = graph.seriesColor; context.lineWidth = Theme.dp(2); context.stroke()
                }
                first = last + 1
            }
        }
        MouseArea {
            id: hover
            anchors.fill: parent
            acceptedButtons: Qt.NoButton
            hoverEnabled: true
            Rectangle {
                visible: graph.hoveredIndex >= 0
                x: graph.hoveredIndex >= 0 ? graph.pointX(graph.hoveredIndex) : 0
                width: Theme.dp(1); height: plot.height
                color: Theme.withAlpha(graph.seriesColor, 0.35)
            }
            Rectangle {
                visible: graph.hoveredIndex >= 0
                x: graph.hoveredIndex >= 0 ? graph.pointX(graph.hoveredIndex) - width / 2 : 0
                y: graph.hoveredIndex >= 0 ? graph.pointY(graph.hoveredIndex) - height / 2 : 0
                width: Theme.dp(6); height: width; radius: width / 2; color: graph.seriesColor
            }
            SwirlToolTip {
                parent: hover
                visible: graph.hoveredIndex >= 0 && !previewCaptureMode
                text: graph.hoveredIndex >= 0
                    ? Qt.formatDateTime(new Date(graph.points[graph.hoveredIndex].time), "MM-dd HH:mm:ss") + " · "
                        + engineController.telemetry.formatBytes(graph.points[graph.hoveredIndex].value) + "/s" : ""
            }
        }
        SwirlText {
            visible: graph.points.length === 0
            anchors.centerIn: parent
            text: qsTr("等待实际采样"); color: Theme.muted; font.pixelSize: Theme.fontSize(12)
        }
    }
    Repeater {
        model: graph.timeTicks
        SwirlText {
            required property int index
            text: graph.timeLabel(index)
            x: plot.x + Math.max(0, Math.min(plot.width - implicitWidth,
                index * plot.width / (graph.timeTicks - 1) - implicitWidth / 2))
            y: plot.y + plot.height + Theme.dp(7)
            color: Theme.muted; font.pixelSize: graph.axisFontSize
        }
    }
}
