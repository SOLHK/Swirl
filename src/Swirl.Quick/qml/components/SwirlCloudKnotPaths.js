.pragma library

// Original cloud loops, with short tucked ends extended through the crossings.
// Each passage keeps one card identity from the lead to the finished knot.
var passages = [
    {
        "key": "warm",
        "tangent": [18, -10],
        "index": 0,
        "guide": "M254 558 C272 548 288 561 283 581 C280 613 249 633 219 633 C173 637 144 604 145 560 C144 511 189 470 242 462 C291 454 315 476 355 500 C399 531 440 545 478 513 C514 487 533 447 516 416 C504 393 475 388 456 404 C439 415 436 430 445 432",
        "start": [
            254,
            558
        ],
        "gradient": [
            135.0,
            575.0,
            510.0,
            405.0
        ],
        "stops": [
            {
                "position": 0.0,
                "light": "#DEA26A",
                "dark": "#DEA26A"
            },
            {
                "position": 0.5,
                "light": "#D79363",
                "dark": "#D79363"
            },
            {
                "position": 1.0,
                "light": "#CF8767",
                "dark": "#CF8767"
            }
        ],
        "card": "connections",
        "order": 4
    },
    {
        "key": "return",
        "tangent": [-30, 7],
        "index": 1,
        "guide": "M490 558 C460 565 430 580 415 587 C370 606 335 644 338 693 C334 752 390 800 453 801 C515 805 566 764 575 713 C579 697 577 685 575 678 C575 655 568 637 559 620",
        "start": [
            490,
            558
        ],
        "gradient": [
            342.0,
            636.0,
            546.0,
            775.0
        ],
        "stops": [
            {
                "position": 0.0,
                "light": "#59AD9C",
                "dark": "#59AD9C"
            },
            {
                "position": 0.5,
                "light": "#419E91",
                "dark": "#419E91"
            },
            {
                "position": 1.0,
                "light": "#6BAA86",
                "dark": "#6BAA86"
            }
        ],
        "card": "traffic",
        "order": 1
    },
    {
        "key": "crown",
        "tangent": [-14, -21],
        "index": 2,
        "guide": "M390 529 C376 508 363 474 352 447 C336 416 343 376 362 349 C391 308 430 287 475 288 C557 278 624 340 625 430 C630 486 600 533 550 568 C532 580 518 594 503 609",
        "start": [
            390,
            529
        ],
        "gradient": [
            365.0,
            315.0,
            594.0,
            559.0
        ],
        "stops": [
            {
                "position": 0.0,
                "light": "#48A8BD",
                "dark": "#48A8BD"
            },
            {
                "position": 0.5,
                "light": "#3794B9",
                "dark": "#3794B9"
            },
            {
                "position": 1.0,
                "light": "#527CB4",
                "dark": "#527CB4"
            }
        ],
        "card": "connection",
        "order": 0
    },
    {
        "key": "forward",
        "tangent": [58, 20],
        "index": 3,
        "guide": "M450 557 C508 577 558 624 611 651 C661 677 715 679 755 662 C801 644 827 607 828 565 C835 516 793 478 749 479 C708 475 675 499 676 535 C673 554 688 568 701 569 C711 569 711 562 710 559",
        "start": [
            450,
            557
        ],
        "gradient": [
            444.0,
            562.0,
            827.0,
            538.0
        ],
        "stops": [
            {
                "position": 0.0,
                "light": "#9C8BC8",
                "dark": "#9C8BC8"
            },
            {
                "position": 0.5,
                "light": "#9180BC",
                "dark": "#9180BC"
            },
            {
                "position": 1.0,
                "light": "#AA8FC5",
                "dark": "#AA8FC5"
            }
        ],
        "card": "sources",
        "order": 2
    },
    {
        "key": "heart",
        "tangent": [-13, -1],
        "index": 4,
        "guide": "M455 664 C442 663 434 677 443 690 C461 719 505 689 530 647 C548 620 563 594 577 574",
        "start": [
            455,
            664
        ],
        "gradient": [
            442.0,
            706.0,
            531.0,
            644.0
        ],
        "stops": [
            {
                "position": 0.0,
                "light": "#D88B84",
                "dark": "#D88B84"
            },
            {
                "position": 0.5,
                "light": "#D5797D",
                "dark": "#D5797D"
            },
            {
                "position": 1.0,
                "light": "#C97585",
                "dark": "#C97585"
            }
        ],
        "card": "diagnostics",
        "order": 3
    }
];

// Four local overpasses alternate depth; no global strand z-order can express this.
// Positions are arc-length fractions on the centre lines above.
var crossings = [
    { passage: 0, start: 0.595, end: 0.677 }, // orange over cyan
    { passage: 1, start: 0.000, end: 0.091 }, // green over purple
    { passage: 2, start: 0.918, end: 1.000 }, // cyan over purple
    { passage: 3, start: 0.112, end: 0.193 }  // purple over coral
];

function point(x, y) { return { x: x, y: y } }

// All coordinates are mapped QML content coordinates. Lanes run through gaps,
// then enter only the reserved emblem box; no screen pixels or DPR thresholds.
function route(card, cards, emblem, end, approach, wide, order, gap) {
    const source = cards[card];
    const status = cards.connection;
    const lane = gap * (0.10 + order * 0.20);
    const right = status.x + status.width;
    const channel = wide ? right + lane : Math.max.apply(null, Object.keys(cards).map(key => cards[key].x + cards[key].width)) + lane;
    const gateY = emblem.y + emblem.height * (0.28 + order * 0.10);
    let start, a, c1, c2;
    if (!wide || card === 'connection' || card === 'traffic') {
        const edge = wide && card === 'traffic' ? source.x : source.x + source.width;
        start = point(edge, card === 'connection' ? emblem.y + emblem.height * 0.78 : source.y + source.height * 0.56);
        a = point(channel, start.y + (gateY - start.y) * 0.5);
        c1 = point(channel, start.y);
        c2 = point(channel, start.y);
    } else {
        const rowGapY = status.y + status.height + lane;
        if (card === 'sources') {
            start = point(Math.min(source.x + source.width - gap * 2, channel + gap * 1.5), source.y);
            c1 = point(start.x, rowGapY);
        } else {
            start = point(source.x, source.y + Math.min(source.height * 0.45, gap * 3));
            c1 = point(source.x - gap * 0.5, start.y);
        }
        a = point(card === 'sources' ? start.x - gap : source.x - gap * 0.5, rowGapY);
        c2 = point(a.x, rowGapY);
    }
    const b = point(channel, a.y - Math.min(gap * 0.35, Math.abs(a.y - gateY) * 0.25));
    const c = point(channel, gateY);
    return { start: start, c1: c1, c2: c2, a: a,
        c3: point(channel, a.y), c4: point(channel, a.y), b: b,
        c5: point(channel, b.y + (gateY - b.y) * 0.4), c6: point(channel, gateY), c: c,
        c7: point(right, gateY), c8: approach, end: end };
}
