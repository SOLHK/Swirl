import QtQuick
import SwirlQuick
// Shared circular rounded-box geometry, identical on software and GPU paths.
// Keep the component API for existing callers, without a separate shader curve.
Rectangle {
    radius: Theme.containerRadius
    color: "transparent"
    border.width: 0
    antialiasing: true
}
