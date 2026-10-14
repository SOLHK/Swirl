import QtQuick
import SwirlQuick
Item {
    id: glass
    required property var targetWindow
    property real tintAmount: Theme.glassTintAmount
    readonly property var description: {
        wallpaperBackdrop.revision
        targetWindow.screen; targetWindow.screen.width; targetWindow.screen.height
        return wallpaperBackdrop.describe(targetWindow)
    }
    readonly property bool enabledEffects: Theme.effectsSupported && Theme.transparency && targetWindow.visible && targetWindow.visibility!==Window.Minimized
    Rectangle {anchors.fill:parent;radius:Theme.windowRadius;visible:!effect.item || !effect.item.ready;color:Theme.dark?"#233044":"#E7F2FD"}
    Loader {
        id:effect;anchors.fill:parent;active:glass.enabledEffects
        sourceComponent:Item {
            readonly property bool ready:blur.ready
            SwirlBlurLayer {id:blur;imageSource:glass.description.url||"";quality:motionPolicy.complexMotion?Theme.glassQuality:0}
            ShaderEffect {
                anchors.fill:parent;visible:blur.ready
                property var source:blur.texture
                property vector4d sampleRect:Qt.vector4d((glass.targetWindow.x-(glass.description.x||0))/Math.max(1,glass.description.width||1),(glass.targetWindow.y-(glass.description.y||0))/Math.max(1,glass.description.height||1),width/Math.max(1,glass.description.width||1),height/Math.max(1,glass.description.height||1))
                property color tint:Theme.dark?"#22334B":"#E7F3FF"
                property real tintAmount:glass.tintAmount
                property real surfaceOpacity:Theme.glassSurfaceOpacity
                fragmentShader:"qrc:/swirl/shaders/swirl-glass.frag.qsb"
            }
        }
    }
}
