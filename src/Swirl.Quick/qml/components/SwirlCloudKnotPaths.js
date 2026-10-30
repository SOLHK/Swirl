.pragma library

// Original cloud loops, with short tucked ends extended through the crossings.
// Each passage keeps one card identity from the lead to the finished knot.
var passages = [
    {
        "key": "warm",
        "tangent": [
            18,
            -10
        ],
        "guide": "M254 558 C272 548 288 561 283 581 C280 613 249 633 219 633 C173 637 144 604 145 560 C144 511 189 470 242 462 C291 454 315 476 355 500 C399 531 440 545 478 513 C514 487 533 447 516 416 C504 393 475 388 456 404 C439 415 436 430 445 432",
        "start": [
            254,
            558
        ],
        "card": "connections",
        "ink": "#DEA26A"
    },
    {
        "key": "return",
        "tangent": [
            -30,
            7
        ],
        "guide": "M490 558 C460 565 430 580 415 587 C370 606 335 644 338 693 C334 752 390 800 453 801 C515 805 566 764 575 713 C579 697 577 685 575 678 C575 655 568 637 559 620",
        "start": [
            490,
            558
        ],
        "card": "traffic",
        "ink": "#59AD9C"
    },
    {
        "key": "crown",
        "tangent": [
            -14,
            -21
        ],
        "guide": "M390 529 C376 508 363 474 352 447 C336 416 343 376 362 349 C391 308 430 287 475 288 C557 278 624 340 625 430 C630 486 600 533 550 568 C532 580 518 594 503 609",
        "start": [
            390,
            529
        ],
        "card": "connection",
        "ink": "#48A8BD"
    },
    {
        "key": "forward",
        "tangent": [
            58,
            20
        ],
        "guide": "M450 557 C508 577 558 624 611 651 C661 677 715 679 755 662 C801 644 827 607 828 565 C835 516 793 478 749 479 C708 475 675 499 676 535 C673 554 688 568 701 569 C711 569 711 562 710 559",
        "start": [
            450,
            557
        ],
        "card": "sources",
        "ink": "#9C8BC8"
    },
    {
        "key": "heart",
        "tangent": [
            -13,
            -1
        ],
        "guide": "M455 664 C442 663 434 677 443 690 C461 719 505 689 530 647 C548 620 563 594 577 574",
        "start": [
            455,
            664
        ],
        "card": "diagnostics",
        "ink": "#D88B84"
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

// Choreography uses one reversible clock; remote cards depart first.
var timing = {
    connection: [0.16, 0.31, 0.76], traffic: [0.08, 0.43, 0.90],
    sources: [0.04, 0.49, 0.94], diagnostics: [0.02, 0.55, 1.00],
    connections: [0.00, 0.59, 0.98]
};
function point(x, y) { return { x: x, y: y } }
function distance(a, b) { return Math.hypot(a.x - b.x, a.y - b.y) }
function mix(a, b, t) { return point(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t) }
function command(p) { return p.x.toFixed(3) + " " + p.y.toFixed(3) }
function cubicPoint(a, b, c, d, t) {
    const ab = mix(a, b, t), bc = mix(b, c, t), cd = mix(c, d, t);
    return mix(mix(ab, bc, t), mix(bc, cd, t), t);
}

// Route each departure individually. The middle flight lives behind the opaque
// cards; only the launch clearance and reserved emblem are drawn in front.
function route(passage, cards, emblem, origin, scale, wide, gap) {
    const card = passage.card, s = cards[card], status = cards.connection;
    const right = status.x + status.width;
    const outer = Math.max.apply(null, Object.keys(cards).map(key => cards[key].x + cards[key].width)) + gap * 0.5;
    const rowY = status.y + status.height + gap * 0.5;
    const entry = point(origin.x + passage.start[0] * scale, origin.y + passage.start[1] * scale);
    const approach = point(entry.x - passage.tangent[0] * scale, entry.y - passage.tangent[1] * scale);
    let start, points, aperture;
    if (card === "connection") {
        start = point(emblem.x + emblem.width * 0.82, emblem.y + emblem.height * 0.72);
        points = [start, point(start.x + gap * 0.22, start.y - gap * 0.55), point(emblem.x + emblem.width * 0.55, emblem.y + gap)];
        aperture = emblem;
    } else if (card === "traffic") {
        start = point(s.x + gap * 0.25, s.y + s.height - gap * 1.5);
        points = [start, point(s.x - gap * 0.45, start.y + gap * 0.2), point(wide ? right + gap * 0.35 : outer, rowY - gap), point(right + gap * 0.35, emblem.y + emblem.height * 0.7)];
        aperture = {x: s.x - gap, y: start.y - gap * 0.5, width: gap * 1.5, height: gap};
    } else if (card === "sources") {
        start = point(s.x + s.width - gap * 2.5, s.y + gap * 0.25);
        points = [start, point(start.x + gap * 0.25, s.y - gap * 0.45), point(wide ? right + gap * 0.65 : outer, rowY), point(right + gap * 0.65, emblem.y + emblem.height * 0.85)];
        aperture = {x: start.x - gap * 0.5, y: s.y - gap, width: gap, height: gap * 1.5};
    } else if (card === "diagnostics") {
        start = point(s.x + gap * 0.25, s.y + s.height * 0.55);
        points = [start, point(s.x - gap * 0.7, start.y - gap * 0.5), point(s.x - gap * 0.45, rowY), point(right + gap * 0.5, rowY - gap), point(right + gap * 0.5, emblem.y + emblem.height * 0.9)];
        aperture = {x: s.x - gap, y: start.y - gap * 0.7, width: gap * 1.5, height: gap * 1.4};
    } else {
        start = point(s.x + gap * 2.5, s.y + gap * 0.25);
        points = [start, point(start.x - gap * 0.2, s.y - gap * 0.45), point(s.x - gap * 0.55, s.y - gap * 0.5), point(s.x - gap * 0.55, rowY), point(right + gap * 0.7, rowY - gap), point(right + gap * 0.7, emblem.y + emblem.height * 0.6)];
        aperture = {x: start.x - gap * 0.6, y: s.y - gap, width: gap * 1.2, height: gap * 1.5};
    }
    if (!wide && card !== "connection") {
        // Exit behind the source, use the right gutter, then return at the emblem.
        points = [points[0], points[1], point(outer, s.y - gap * 0.5), point(outer, emblem.y + emblem.height * 0.5)];
    }
    points.push(approach, entry);
    let guide = "M" + command(points[0]), leadLength = 0;
    for (let i = 0; i < points.length - 1; ++i) {
        const a = points[i], d = points[i + 1], before = points[Math.max(0, i - 1)], after = points[Math.min(points.length - 1, i + 2)];
        const handle = Math.min(distance(a, d), i ? distance(before, a) : distance(a, d), distance(d, after) || distance(a, d)) * 0.26;
        const tangentA = distance(before, d) || 1, tangentD = distance(a, after) || 1;
        const b = point(a.x + (d.x - before.x) / tangentA * handle, a.y + (d.y - before.y) / tangentA * handle);
        const c = i === points.length - 2 ? approach : point(d.x - (after.x - a.x) / tangentD * handle, d.y - (after.y - a.y) / tangentD * handle);
        guide += " C" + command(b) + " " + command(c) + " " + command(d);
        let previous = a;
        for (let n = 1; n <= 20; ++n) { const p = cubicPoint(a, b, c, d, n / 20); leadLength += distance(previous, p); previous = p; }
    }
    const tokens = passage.guide.match(/[MC]|[-+]?\d*\.?\d+/g);
    let i = 3, previous = entry, knotLength = 0;
    while (i < tokens.length) {
        ++i;
        const b = point(origin.x + Number(tokens[i++]) * scale, origin.y + Number(tokens[i++]) * scale);
        const c = point(origin.x + Number(tokens[i++]) * scale, origin.y + Number(tokens[i++]) * scale);
        const d = point(origin.x + Number(tokens[i++]) * scale, origin.y + Number(tokens[i++]) * scale);
        guide += " C" + command(b) + " " + command(c) + " " + command(d);
        const a = previous;
        for (let n = 1; n <= 20; ++n) { const p = cubicPoint(a, b, c, d, n / 20); knotLength += distance(previous, p); previous = p; }
    }
    const total = leadLength + knotLength;
    return {guide: guide, join: leadLength / total, span: Math.min(100 * gap / 16, Math.max(40 * gap / 16, leadLength * 0.32)) / total, aperture: aperture};
}
function hermite(t, a, b, startSlope, endSlope, duration) {
    return (2*t*t*t-3*t*t+1)*a + (t*t*t-2*t*t+t)*startSlope*duration
        + (-2*t*t*t+3*t*t)*b + (t*t*t-t*t)*endSlope*duration;
}
function head(progress, card, join) {
    const times = timing[card], departure = times[0], arrival = times[1], finish = times[2];
    if (progress <= departure) return 0;
    if (progress >= finish) return 1;
    const speed = Math.min(join / (arrival - departure), (1 - join) / (finish - arrival));
    return progress < arrival ? hermite((progress-departure)/(arrival-departure), 0, join, 0, speed, arrival-departure)
        : hermite((progress-arrival)/(finish-arrival), join, 1, speed, 0, finish-arrival);
}
function tail(progress, card, route, headPosition) {
    const times = timing[card];
    const t = Math.max(0, Math.min(1, (progress - times[1]) / (times[2] - times[1])));
    const tucked = route.join * t * t * (3 - 2 * t);
    return Math.min(headPosition, route.join, Math.max(0, headPosition - route.span, tucked));
}
