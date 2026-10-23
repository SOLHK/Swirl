import QtQuick
import SwirlQuick

Rectangle {
    id: glass
    readonly property bool glassEnabled: Theme.transparency && (backdrop.blurActive || backdrop.active || backdrop.translucent)
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
        : Theme.dark ? Theme.withAlpha("#FFFFFF", 0.18) : Theme.withAlpha("#777777", 0.12)
    Behavior on color { ColorAnimation { duration: SwirlMotion.hoverDuration } }

    Canvas {
        id: shadow
        readonly property real margin: Theme.dp(18)
        x: -margin; y: -margin
        width: glass.width + 2 * margin; height: glass.height + 2 * margin
        z: -1
        visible: Theme.effectsSupported
        antialiasing: true
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        onVisibleChanged: if (visible) requestPaint()
        Connections { target: Theme; function onDarkChanged() { shadow.requestPaint() } }
        Connections { target: glass; function onRadiusChanged() { shadow.requestPaint() } }

        function roundedPath(ctx, x, y, w, h, r) {
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
            if (glass.width <= 0 || glass.height <= 0) return
            const compact = glass.height < Theme.dp(50)
            const r = Math.min(glass.radius, glass.width / 2, glass.height / 2)
            ctx.save()
            ctx.fillStyle = "#000000"
            ctx.shadowColor = Theme.dark ? "rgba(0,0,0,0.16)" : "rgba(0,0,0,0.08)"
            ctx.shadowBlur = Theme.dp(compact ? 8 : 10)
            ctx.shadowOffsetX = Theme.dp(1)
            ctx.shadowOffsetY = Theme.dp(compact ? 2 : 3)
            roundedPath(ctx, margin, margin, glass.width, glass.height, r)
            ctx.fill()
            ctx.shadowColor = "transparent"
            ctx.shadowBlur = 0
            ctx.shadowOffsetX = 0
            ctx.shadowOffsetY = 0
            ctx.globalCompositeOperation = "destination-out"
            const inset = Theme.dp(1)
            roundedPath(ctx, margin - inset, margin - inset,
                        glass.width + 2 * inset, glass.height + 2 * inset, r + inset)
            ctx.fill()
            ctx.restore()
        }
    }
}
