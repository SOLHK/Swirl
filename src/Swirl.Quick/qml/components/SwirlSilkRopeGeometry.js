.pragma library

function flatten(path) {
    const tokens = path.match(/[a-zA-Z]|[-+]?(?:\d*\.?\d+)(?:[eE][-+]?\d+)?/g) || []
    const points = []
    let index = 0
    let command = ""
    let current = { x: 0, y: 0 }
    while (index < tokens.length) {
        if (/^[a-zA-Z]$/.test(tokens[index])) command = tokens[index++]
        const relative = command === command.toLowerCase()
        const kind = command.toUpperCase()
        if (kind === "M" || kind === "L") {
            const x = Number(tokens[index++]) + (relative ? current.x : 0)
            const y = Number(tokens[index++]) + (relative ? current.y : 0)
            current = { x: x, y: y }
            points.push(current)
            if (kind === "M") command = relative ? "l" : "L"
        } else if (kind === "C") {
            const origin = current
            const x1 = Number(tokens[index++]) + (relative ? origin.x : 0)
            const y1 = Number(tokens[index++]) + (relative ? origin.y : 0)
            const x2 = Number(tokens[index++]) + (relative ? origin.x : 0)
            const y2 = Number(tokens[index++]) + (relative ? origin.y : 0)
            const x = Number(tokens[index++]) + (relative ? origin.x : 0)
            const y = Number(tokens[index++]) + (relative ? origin.y : 0)
            for (let step = 1; step <= 20; ++step) {
                const t = step / 20
                const s = 1 - t
                points.push({
                    x: s * s * s * origin.x + 3 * s * s * t * x1 + 3 * s * t * t * x2 + t * t * t * x,
                    y: s * s * s * origin.y + 3 * s * s * t * y1 + 3 * s * t * t * y2 + t * t * t * y
                })
            }
            current = { x: x, y: y }
        } else {
            throw new Error("Silk rope guides require an open M/L/C path")
        }
    }
    return points
}

function build(path, width) {
    if (!path.length || width <= 0) return []
    const source = flatten(path)
    if (source.length < 2) return []
    const arc = [0]
    for (let i = 1; i < source.length; ++i)
        arc.push(arc[i - 1] + Math.hypot(source[i].x - source[i - 1].x, source[i].y - source[i - 1].y))
    const length = arc[arc.length - 1]
    if (length === 0) return []
    // Three material paths share at most 720 points. This work runs only when
    // the guide geometry changes, never when the animation changes its trim.
    const count = Math.min(240, Math.max(24, Math.ceil(length / (width * 0.12))))
    const samples = []
    let segment = 1
    for (let i = 0; i < count; ++i) {
        const distance = length * i / (count - 1)
        while (segment < arc.length - 1 && arc[segment] < distance) ++segment
        const a = source[segment - 1]
        const b = source[segment]
        const t = (distance - arc[segment - 1]) / (arc[segment] - arc[segment - 1])
        samples.push({ x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t })
    }
    const pitch = Math.max(width * 1.85, length / (count - 1) * 6)
    const fibers = []
    for (let lane = 0; lane < 3; ++lane) {
        const points = []
        const lengths = [0]
        for (let i = 0; i < count; ++i) {
            const before = samples[Math.max(0, i - 1)]
            const after = samples[Math.min(count - 1, i + 1)]
            const dx = after.x - before.x
            const dy = after.y - before.y
            const magnitude = Math.hypot(dx, dy)
            const distance = length * i / (count - 1)
            const offset = width * 0.27 * Math.sin(distance / pitch * Math.PI * 2 + lane * Math.PI * 2 / 3)
            const point = { x: samples[i].x - dy / magnitude * offset, y: samples[i].y + dx / magnitude * offset }
            if (i > 0) lengths.push(lengths[i - 1] + Math.hypot(point.x - points[i - 1].x, point.y - points[i - 1].y))
            points.push(point)
        }
        const total = lengths[lengths.length - 1]
        for (let i = 0; i < lengths.length; ++i) lengths[i] /= total
        fibers.push({
            path: points.map((point, index) => (index ? "L" : "M") + point.x.toFixed(3) + " " + point.y.toFixed(3)).join(" "),
            lengths: lengths,
            count: count
        })
    }
    return fibers
}

function fraction(fiber, progress) {
    if (!fiber) return 0
    const index = Math.max(0, Math.min(1, progress)) * (fiber.lengths.length - 1)
    const lower = Math.floor(index)
    const upper = Math.min(fiber.lengths.length - 1, lower + 1)
    return fiber.lengths[lower] + (fiber.lengths[upper] - fiber.lengths[lower]) * (index - lower)
}
