import QtQuick
import SwirlQuick

Rectangle {
    id: glass
    readonly property bool glassEnabled: Theme.transparency && (backdrop.blurActive || backdrop.active || backdrop.translucent)
    readonly property bool compact: height < Theme.dp(50)
    property bool focused: false
    property bool hovered: false
    property bool pressed: false
    radius: Theme.dp(14)
    antialiasing: true
    color: pressed ? Theme.withAlpha(Theme.dark ? "#FFFFFF" : "#000000", Theme.dark ? 0.16 : 0.08)
        : hovered ? Theme.withAlpha(Theme.dark ? "#FFFFFF" : "#000000", Theme.dark ? 0.09 : 0.035)
        : glassEnabled ? Theme.withAlpha("#FFFFFF", Theme.dark ? 0.05 : 0.04)
        : Theme.dark ? "#333B46" : "#FBFBFB"
    border.width: Theme.dp(1)
    border.color: focused ? Theme.focusBorder
        : Theme.dark ? Theme.withAlpha("#FFFFFF", 0.28) : Theme.withAlpha("#777777", 0.16)

    Canvas {
        id: shadow
        readonly property real margin: Theme.dp(28)
        x: -margin; y: -margin
        width: glass.width + 2 * margin; height: glass.height + 2 * margin
        visible: Theme.effectsSupported
        antialiasing: true
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        Connections { target: Theme; function onDarkChanged() { shadow.requestPaint() } }
        Connections { target: glass; function onRadiusChanged() { shadow.requestPaint() } }
        function outline(ctx, x, y, w, h, r) {
            ctx.beginPath()
            ctx.moveTo(x + r, y)
            ctx.lineTo(x + w - r, y)
            ctx.quadraticCurveTo(x + w, y, x + w, y + r)
            ctx.lineTo(x + w, y + h - r)
            ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h)
            ctx.lineTo(x + r, y + h)
            ctx.quadraticCurveTo(x, y + h, x, y + h - r)
            ctx.lineTo(x, y + r)
            ctx.quadraticCurveTo(x, y, x + r, y)
            ctx.closePath()
        }
        onPaint: {
            const ctx = getContext("2d")
            ctx.clearRect(0, 0, width, height)
            const r = Math.min(glass.radius, glass.width / 2, glass.height / 2)
            ctx.save()
            ctx.fillStyle = "#000000"
            ctx.shadowColor = Theme.dark ? "rgba(0,0,0,0.28)" : "rgba(0,0,0,0.14)"
            ctx.shadowBlur = Theme.dp(glass.compact ? 14 : 20)
            ctx.shadowOffsetY = Theme.dp(glass.compact ? 3 : 5)
            outline(ctx, margin, margin, glass.width, glass.height, r)
            ctx.fill()
            ctx.shadowColor = Theme.dark ? "rgba(0,0,0,0.17)" : "rgba(0,0,0,0.08)"
            ctx.shadowBlur = Theme.dp(glass.compact ? 4 : 5)
            ctx.shadowOffsetY = Theme.dp(1)
            outline(ctx, margin, margin, glass.width, glass.height, r)
            ctx.fill()
            ctx.shadowColor = "transparent"
            ctx.shadowBlur = 0
            ctx.shadowOffsetY = 0
            ctx.globalCompositeOperation = "destination-out"
            const clearInset = Theme.dp(2)
            outline(ctx, margin - clearInset, margin - clearInset,
                    glass.width + 2 * clearInset, glass.height + 2 * clearInset, r + clearInset)
            ctx.fill()
            ctx.restore()
        }
    }
    Rectangle {
        anchors.fill: parent
        anchors.margins: Theme.dp(1)
        radius: Math.max(0, glass.radius - Theme.dp(1))
        color: "transparent"
        border.width: Theme.dp(1)
        border.color: Theme.withAlpha("#FFFFFF", Theme.dark ? 0.18 : 0.58)
    }
}
