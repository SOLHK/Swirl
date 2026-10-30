pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Shapes
import SwirlQuick

Item {
    id: wing
    property real progress: 0
    property bool largeWing: false
    readonly property int featherCount: paths.length
    readonly property real artWidth: largeWing ? 1000 : 96
    readonly property real artHeight: largeWing ? 760 : 48
    readonly property real fit: Math.min(width / artWidth, height / artHeight)
    readonly property var roots: largeWing ? [Qt.point(-60, 738), Qt.point(-15, 752), Qt.point(50, 758), Qt.point(120, 760), Qt.point(190, 765)]
                                                : [Qt.point(5, 39), Qt.point(10, 42), Qt.point(18, 44), Qt.point(30, 45)]
    readonly property var paths: largeWing ? [
        "M -60 738 C 101 641 101 414 285 265 C 449 132 673 83 940 64 C 802 153 686 203 512 230 C 290 265 228 636 -60 738 Z",
        "M -15 752 C 178 655 205 454 383 356 C 549 265 707 252 906 244 C 779 327 653 359 503 375 C 318 396 236 693 -15 752 Z",
        "M 50 758 C 251 686 319 536 472 473 C 586 426 708 420 813 424 C 722 483 632 510 518 514 C 348 522 251 725 50 758 Z",
        "M 120 760 C 307 714 388 618 503 589 C 566 572 633 567 704 574 C 642 616 577 634 513 633 C 390 632 293 747 120 760 Z",
        "M 190 765 C 358 734 418 685 490 675 C 532 669 574 672 615 680 C 573 711 525 719 484 715 C 391 708 321 765 190 765 Z"
    ] : [
        "M5 39C21 37 26 22 42 14C57 6 76 5 92 4C83 12 72 17 58 20C39 24 26 39 5 39Z",
        "M10 42C30 39 40 27 57 24C67 22 77 20 85 16C79 25 67 30 55 31C36 33 25 43 10 42Z",
        "M18 44C34 41 43 35 56 34C65 33 71 31 77 28C70 36 62 39 52 39C38 39 30 45 18 44Z",
        "M30 45C40 42 47 42 54 42C59 42 63 41 67 39C62 44 56 46 50 45C42 44 37 46 30 45Z"
    ]
    readonly property var shafts: [
        "M -60 738 C 189 646 174 359 435 239 C 582 171 751 132 940 64",
        "M -15 752 C 244 660 278 433 493 363 C 634 318 767 294 906 244",
        "M 50 758 C 281 703 367 531 529 498 C 642 476 730 458 813 424",
        "M 120 760 C 323 728 408 637 518 619 C 589 607 652 600 704 574",
        "M 190 765 C 343 752 421 706 490 702 C 537 700 578 694 615 680"
    ]
    readonly property var veins: [
        "M 260 388 Q 262 332 285 265 M 326 310 Q 352 254 389 197 M 420 247 Q 456 188 512 145 M 532 199 Q 586 147 653 104 M 336 300 Q 370 263 410 256 M 470 225 Q 507 232 550 224 M 616 169 Q 665 191 708 175 M 758 122 Q 798 144 836 126",
        "M 337 456 Q 346 407 383 356 M 425 394 Q 450 338 493 305 M 544 347 Q 581 289 629 271 M 676 310 Q 715 272 756 256 M 400 407 Q 443 389 469 391 M 535 349 Q 576 373 617 356 M 689 307 Q 733 334 767 321",
        "M 402 570 Q 429 512 472 473 M 504 504 Q 536 454 577 430 M 612 481 Q 649 439 689 424 M 465 525 Q 500 527 533 513 M 584 487 Q 620 514 651 498 M 698 458 Q 727 482 753 465",
        "M 427 651 Q 460 608 503 589 M 529 617 Q 559 581 589 574 M 493 624 Q 519 640 544 631 M 588 607 Q 615 625 639 611",
        "M 424 723 Q 453 687 490 675 M 489 702 Q 511 720 536 711 M 542 699 Q 565 682 587 676"
    ]
    readonly property var featherColors: Theme.dark
        ? ["#7CAFBF", "#9BA5C6", "#87B4A6", "#C6A0AA", "#90B8BE"]
        : ["#91BFCA", "#B3ACCE", "#A1C4B6", "#D4B4BA", "#A5C5CA"]
    implicitWidth: Theme.dp(40)
    implicitHeight: Theme.dp(20)
    visible: progress > 0
    Accessible.ignored: true

    function featherProgress(index) {
        const stagger = 0.6 / (featherCount - 1)
        const value = Math.max(0, Math.min(1, (progress - index * stagger) / 0.4))
        return value * value * (3 - 2 * value)
    }

    Item {
        x: (wing.width - wing.artWidth * wing.fit) / 2
        y: (wing.height - wing.artHeight * wing.fit) / 2
        width: wing.artWidth
        height: wing.artHeight
        scale: wing.fit
        transformOrigin: Item.TopLeft
        Repeater {
            model: wing.featherCount
            Item {
                id: feather
                required property int index
                objectName: "wingFeather" + index
                readonly property real reveal: wing.featherProgress(index)
                readonly property point rootPoint: wing.roots[index]
                readonly property color featherColor: wing.featherColors[index]
                // Preserve the pointed contour while each feather extends and fans from its root.
                width: wing.artWidth
                height: wing.artHeight
                visible: reveal > 0
                opacity: Math.min(1, reveal * 8) * (wing.largeWing ? 1 : 1 - index * 0.18)
                transform: [
                    Scale {
                        origin.x: feather.rootPoint.x; origin.y: feather.rootPoint.y
                        xScale: 0.12 + 0.88 * feather.reveal
                        yScale: 0.18 + 0.82 * feather.reveal
                    },
                    Rotation {
                        origin.x: feather.rootPoint.x; origin.y: feather.rootPoint.y
                        angle: (1 - feather.reveal) * (12 + feather.index * 2)
                    }
                ]
                Shape {
                    objectName: wing.largeWing && feather.index === 0 ? "apecFlatWingPaths" : "wingFeatherPath" + feather.index
                    width: wing.artWidth
                    height: wing.artHeight
                    preferredRendererType: Shape.CurveRenderer
                    ShapePath {
                        strokeWidth: 0
                        strokeColor: "transparent"
                        fillRule: ShapePath.WindingFill
                        fillGradient: LinearGradient {
                            x1: wing.largeWing ? 0 : 8
                            y1: wing.largeWing ? 760 : 42
                            x2: wing.largeWing ? 920 : 83
                            y2: wing.largeWing ? 80 : 5
                            GradientStop { position: 0; color: wing.largeWing ? Theme.withAlpha(feather.featherColor, 0.10) : Theme.wingSmallStart }
                            GradientStop { position: 0.16; color: wing.largeWing ? Theme.withAlpha(feather.featherColor, 0.20) : Theme.wingSmallStart }
                            GradientStop { position: 0.33; color: wing.largeWing ? Theme.withAlpha(feather.featherColor, 0.32) : Theme.wingSmallMid }
                            GradientStop { position: 0.55; color: wing.largeWing ? Theme.withAlpha(feather.featherColor, 0.46) : Theme.wingSmallMid }
                            GradientStop { position: 0.79; color: wing.largeWing ? Theme.withAlpha(feather.featherColor, 0.34) : Theme.wingSmallEnd }
                            GradientStop { position: 1; color: wing.largeWing ? Theme.withAlpha(feather.featherColor, 0.12) : Theme.wingSmallEnd }
                        }
                        PathSvg { path: wing.paths[feather.index] }
                    }
                    ShapePath {
                        fillColor: "transparent"
                        strokeColor: wing.largeWing ? Theme.withAlpha(feather.featherColor, 0.67) : "transparent"
                        strokeWidth: 2.2
                        capStyle: ShapePath.RoundCap
                        joinStyle: ShapePath.RoundJoin
                        PathSvg { path: wing.largeWing ? wing.shafts[feather.index] : "" }
                    }
                    ShapePath {
                        fillColor: "transparent"
                        strokeColor: wing.largeWing ? Theme.withAlpha(feather.featherColor, 0.44) : "transparent"
                        strokeWidth: 1.5
                        capStyle: ShapePath.RoundCap
                        joinStyle: ShapePath.RoundJoin
                        PathSvg { path: wing.largeWing ? wing.veins[feather.index] : "" }
                    }
                }
            }
        }
    }
}
