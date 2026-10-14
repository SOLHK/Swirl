import QtQuick
import QtQuick.Effects
import SwirlQuick
Item {
    id:bench
    property int algorithm:0
    property real strength:3.5
    property bool impulse:false
    Item {
        id:input;anchors.fill:parent
        Rectangle {anchors.fill:parent;color:bench.impulse?"black":"#27416B"}
        Repeater {model:bench.impulse?0:64
            Rectangle {required property int index;x:(index%8)*bench.width/8;y:Math.floor(index/8)*bench.height/8;width:bench.width/8;height:bench.height/8;color:Qt.hsla((index*0.17)%1,0.65,0.55,1);radius:Math.min(width,height)/4
                Text {anchors.centerIn:parent;text:"Swirl "+index;color:"white";font.pixelSize:bench.height/25}
            }
        }
        Rectangle {visible:bench.impulse;x:Math.floor(parent.width/2)-4;width:8;height:parent.height;color:"white"}
    }
    ShaderEffectSource {id:inputTexture;sourceItem:input;hideSource:true;live:true;smooth:true;textureSize:Qt.size(bench.width,bench.height)}
    component Pass:ShaderEffect {property var source;property vector2d stepSize;property real upscale:0;fragmentShader:"qrc:/swirl/shaders/swirl-blur.frag.qsb"}
    Loader {
        anchors.fill:parent
        sourceComponent:bench.algorithm===3?nativeBlur:bench.algorithm===2?dual:separable
    }
    Component {id:separable
        Item {
            Pass {id:first;anchors.fill:parent;source:inputTexture;upscale:bench.algorithm===0?2:3;stepSize:bench.algorithm===0?Qt.vector2d(bench.strength/width,0):Qt.vector2d(bench.strength/width,bench.strength/height);visible:false}
            ShaderEffectSource {id:firstTexture;sourceItem:first;hideSource:true;live:true;smooth:true;textureSize:Qt.size(first.width,first.height)}
            Pass {anchors.fill:parent;source:firstTexture;upscale:bench.algorithm===0?2:3;stepSize:bench.algorithm===0?Qt.vector2d(0,bench.strength/height):Qt.vector2d(bench.strength*2/width,bench.strength*2/height)}
        }
    }
    Component {id:dual
        Item {
            Pass {id:down;width:bench.width/2;height:bench.height/2;source:inputTexture;stepSize:Qt.vector2d(bench.strength/bench.width,bench.strength/bench.height);visible:false}
            ShaderEffectSource {id:downTexture;sourceItem:down;hideSource:true;live:true;smooth:true;textureSize:Qt.size(down.width,down.height)}
            Pass {id:low;width:bench.width/4;height:bench.height/4;source:downTexture;stepSize:Qt.vector2d(bench.strength/down.width,bench.strength/down.height);visible:false}
            ShaderEffectSource {id:lowTexture;sourceItem:low;hideSource:true;live:true;smooth:true;textureSize:Qt.size(low.width,low.height)}
            Pass {id:mid;width:down.width;height:down.height;source:lowTexture;upscale:1;stepSize:Qt.vector2d(bench.strength/low.width,bench.strength/low.height);visible:false}
            ShaderEffectSource {id:midTexture;sourceItem:mid;hideSource:true;live:true;smooth:true;textureSize:Qt.size(mid.width,mid.height)}
            Pass {anchors.fill:parent;source:midTexture;upscale:1;stepSize:Qt.vector2d(bench.strength/mid.width,bench.strength/mid.height)}
        }
    }
    Component {id:nativeBlur
        MultiEffect {anchors.fill:parent;source:inputTexture;blurEnabled:true;blurMax:32;blur:bench.strength/16;autoPaddingEnabled:false}
    }
}
