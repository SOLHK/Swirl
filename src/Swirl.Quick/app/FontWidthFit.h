#pragma once

#include <algorithm>
#include <cmath>
#include <limits>

// A bounded approximation over the permitted part of the wdth axis. A finite
// grid cannot guarantee the global optimum of an arbitrary nonmonotonic font.
// The callback measures the complete shaped string at a real font coordinate.
namespace FontWidthFit {
inline constexpr int sampleCount = 10;
// Retained W1 product limits, not typography standards or per-font validation.
inline constexpr double minimumAdvanceRatio = .85;
inline constexpr double minimumAxisRatio = .90;
inline constexpr double entryMargin = 4.;
inline constexpr double holdMargin = 2.;
inline constexpr double minimumImprovement = .5;

template<class Measure>
double solve(double axisMinimum, double normal, double axisMaximum,
             double natural, double available, double previous, Measure measure)
{
    if (!std::isfinite(axisMinimum) || !std::isfinite(normal)
        || !std::isfinite(axisMaximum) || axisMinimum > normal
        || normal > axisMaximum || normal <= 0
        || std::abs(axisMinimum) > std::numeric_limits<float>::max()
        || axisMaximum > std::numeric_limits<float>::max()
        || !std::isfinite(natural) || natural <= 0
        || !std::isfinite(available) || available <= 0)
        return normal;
    const double minimum = std::max(axisMinimum, normal * minimumAxisRatio);
    if (minimum >= normal)
        return normal;

    // QFont stores float coordinates. Compare and publish what it will receive,
    // and round the lower end inwards so quantization never exceeds our domain.
    const auto coordinate = [=](double value) {
        float rounded = float(value);
        if (double(rounded) < minimum)
            rounded = std::nextafter(rounded, float(normal));
        return std::min(normal, double(rounded));
    };
    const bool wasNarrow = std::isfinite(previous)
        && previous >= minimum && previous < normal;
    if ((!wasNarrow && natural <= available + entryMargin)
        || (wasNarrow && natural <= available - entryMargin))
        return normal;

    const auto admissible = [=](double width) {
        return std::isfinite(width) && width >= natural * minimumAdvanceRatio
            && width < natural - minimumImprovement;
    };
    bool holdPrevious = false;
    if (wasNarrow) {
        previous = coordinate(previous);
        const double width = measure(previous);
        // History can belong to another text, font, size or weight. It must
        // satisfy exactly the same safety checks as every new candidate.
        holdPrevious = previous < normal && admissible(width)
            && width <= available + holdMargin;
    }

    double chosen = normal;
    double bestAdvance = natural;
    double last = normal;
    bool foundFit = false;
    for (int step = 1; step <= sampleCount; ++step) {
        // Cover the actual permitted interval, including asymmetric/narrow
        // ranges, instead of repeatedly clamping default-percent steps.
        const double candidate = coordinate(normal - (normal - minimum) * step / sampleCount);
        if (candidate >= last)
            continue;
        last = candidate;
        const double width = measure(candidate);
        if (!admissible(width))
            continue;
        if (width <= available - holdMargin) {
            if (!foundFit || candidate > chosen) {
                chosen = candidate;
                bestAdvance = width;
            }
            foundFit = true;
        } else if (!foundFit && width < bestAdvance - minimumImprovement) {
            chosen = candidate;
            bestAdvance = width;
        }
    }
    // Search all higher candidates before retaining history: a blocked adjacent
    // coordinate says nothing about a nonmonotonic font's other coordinates.
    if (holdPrevious && (!foundFit || chosen <= previous))
        return previous;
    return chosen;
}
} // namespace FontWidthFit
