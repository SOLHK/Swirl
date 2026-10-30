import QtQuick
import QtQuick.Shapes
import SwirlQuick

Item {
    id: outline
    property real radius: 0
    property real strokeWidth: 1 / Screen.devicePixelRatio
    property color strokeColor: "transparent"
    property color fillColor: "transparent"

    // GPU rim and WindowEdge evaluate the same analytic contour and coverage.
    // The rim is inset along its normal, not by shrinking a second rectangle.
    ShaderEffect {
        anchors.fill: parent
        visible: Theme.effectsSupported
        property vector2d surfaceSize: Qt.vector2d(width, height)
        property real cornerRadius: outline.radius
        property real borderWidth: outline.strokeWidth
        property color fillColor: outline.fillColor
        property color rimColor: outline.strokeColor
        fragmentShader: "qrc:/swirl/shaders/swirl-surface.frag.qsb"
    }

    // Software fallback: Hermite cubic spans of the same analytic quarter.
    // At each straight-edge junction the first two handles stay collinear.
    function contourPath() {
        const inset = strokeWidth / 2
        const r = Math.max(0, Math.min(radius, width / 2, height / 2))
        if (r === 0) return "M" + inset + " " + inset + "H" + (width-inset) + "V" + (height-inset) + "H" + inset + "Z"
        const half = Math.pow(0.5, 0.4)
        function sample(t, mirror) {
            const base = Math.max(0.000001, 1-Math.pow(t,2.5))
            let x = 1-Math.pow(base,0.4), y = 1-t
            let dx = Math.pow(t,1.5)*Math.pow(base,-0.6), dy = -1
            if (mirror) { const xx=x; x=y; y=xx; const dd=dx; dx=-dy; dy=-dd }
            const length = Math.hypot(dx,dy)
            return {x:r*x-inset*dy/length, y:r*y+inset*dx/length, dx:dx, dy:dy}
        }
        function map(p, corner) {
            if(corner===0) return {x:p.x,y:p.y}
            if(corner===1) return {x:width-p.y,y:p.x}
            if(corner===2) return {x:width-p.x,y:height-p.y}
            return {x:p.y,y:height-p.x}
        }
        function text(p) { return p.x + " " + p.y }
        let path=""
        for(let corner=0;corner<4;++corner) {
            let previous=sample(0,false)
            path+=(corner?"L":"M")+text(map(previous,corner))
            for(let halfIndex=0;halfIndex<2;++halfIndex) {
                for(let step=1;step<=12;++step) {
                    const mirrored=halfIndex===1
                    const next=sample(half*(mirrored?1-step/12:step/12),mirrored)
                    const h=r*half/12
                    const a={x:previous.x+previous.dx*h/3,y:previous.y+previous.dy*h/3}
                    const b={x:next.x-next.dx*h/3,y:next.y-next.dy*h/3}
                    if(halfIndex===0&&step===1)b.x=inset
                    if(halfIndex===1&&step===12)a.y=inset
                    path+="C"+text(map(a,corner))+" "+text(map(b,corner))+" "+text(map(next,corner))
                    previous=next
                }
            }
        }
        return path+"Z"
    }
    Shape {
        anchors.fill: parent
        visible: !Theme.effectsSupported
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            fillColor: outline.fillColor
            strokeColor: outline.strokeColor
            strokeWidth: outline.strokeWidth
            joinStyle: ShapePath.RoundJoin
            PathSvg { path: outline.contourPath() }
        }
    }
}
