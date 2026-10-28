import QtQuick
import SwirlQuick
Item {
    id:light
    property real amount:0
    property real cornerRadius:Theme.buttonRadius
    readonly property bool useShader:Theme.effectsSupported && motionPolicy.complexMotion && !SwirlMotion.reduced
    visible:amount>0
    Loader {
        objectName:"clickLightShaderLoader"
        anchors.fill:parent
        active:light.visible && light.useShader
        sourceComponent:ShaderEffect {
            opacity:light.amount
            vertexShader:"qrc:/swirl/shaders/swirlclicklight.vert.qsb"
            fragmentShader:"qrc:/swirl/shaders/swirlclicklight.frag.qsb"
        }
    }
    Rectangle {
        anchors.fill:parent;radius:light.cornerRadius
        color:Theme.glassHighlight;opacity:light.amount
        visible:!light.useShader
    }
}
