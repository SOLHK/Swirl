import QtQuick
import SwirlQuick
SpringAnimation {
    spring: SwirlMotion.spring
    damping: SwirlMotion.damping
    mass: 0.25
    epsilon: 0.001
}
