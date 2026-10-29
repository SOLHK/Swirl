import QtQuick
import QtQuick.Shapes

Shape {
    id: outline
    property real radius: 0
    property real strokeWidth: 1 / Screen.devicePixelRatio
    property color strokeColor: "transparent"
    property color fillColor: "transparent"
    preferredRendererType: Shape.CurveRenderer
    // The reference contour uses a 2.5-power corner. Sample only the outline;
    // no text or child content is rendered into a scaled texture.
    function contourPath() {
        const inset = strokeWidth / 2
        const w = Math.max(0, width - strokeWidth)
        const h = Math.max(0, height - strokeWidth)
        const r = Math.max(0, Math.min(radius - inset, w / 2, h / 2))
        let path = ""
        for (let corner = 0; corner < 4; ++corner) {
            for (let step = 0; step <= 64; ++step) {
                const angle = (corner + step / 64) * Math.PI / 2
                const cx = Math.cos(angle), sy = Math.sin(angle)
                const x = inset + (corner === 0 || corner === 3 ? w - r : r)
                    + r * Math.sign(cx) * Math.pow(Math.abs(cx), 0.8)
                const y = inset + (corner < 2 ? h - r : r)
                    + r * Math.sign(sy) * Math.pow(Math.abs(sy), 0.8)
                path += (corner === 0 && step === 0 ? "M" : "L") + x + " " + y
            }
        }
        return path + "Z"
    }
    ShapePath {
        fillColor: outline.fillColor
        strokeColor: outline.strokeColor
        strokeWidth: outline.strokeWidth
        joinStyle: ShapePath.RoundJoin
        PathSvg { path: outline.contourPath() }
    }
}
