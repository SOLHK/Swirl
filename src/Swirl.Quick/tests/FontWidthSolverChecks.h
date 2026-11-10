#pragma once

#include "app/FontWidthFit.h"
#include <array>
#include <set>
#include <vector>

void FontTests::widthSolverRejectsUnsafeHistory()
{
    const double nan = std::numeric_limits<double>::quiet_NaN();
    const double infinity = std::numeric_limits<double>::infinity();
    struct HistoryCase { double width; double available; };
    // A historical coordinate can belong to a different text or font. In the
    // old early-return path, the blocked neighbour allowed unsafe history to
    // bypass both the measured readability floor and the improvement check.
    const std::array<HistoryCase, 7> cases{{
        {84., 90.}, {100., 100.}, {104., 102.}, {99.75, 100.},
        {nan, 90.}, {infinity, 90.}, {-infinity, 90.}
    }};
    for (const auto &test : cases) {
        int calls = 0;
        bool coordinatesValid = true;
        const auto width = [&](double coordinate) {
            if (coordinate == 90.) return test.width;
            if (coordinate == 92.) return 105.;
            return coordinate;
        };
        const double selected = FontWidthFit::solve(75., 100., 125., 100.,
            test.available, 90., [&](double coordinate) {
                ++calls;
                coordinatesValid &= std::isfinite(coordinate)
                    && coordinate >= 90. && coordinate < 100.;
                return width(coordinate);
            });
        QVERIFY(coordinatesValid);
        QVERIFY(calls <= FontWidthFit::sampleCount + 1);
        QVERIFY(std::isfinite(selected));
        QVERIFY(selected >= 90. && selected <= 100.);
        QVERIFY(selected != 90.);
        if (selected != 100.) {
            QVERIFY(std::isfinite(width(selected)));
            QVERIFY(width(selected) >= 85.);
            QVERIFY(width(selected) < 99.5);
        }
    }

    // The exact floor is allowed; one representable value below it is not.
    for (const double previousAdvance : {85., std::nextafter(85., 0.)}) {
        int calls = 0;
        const double selected = FontWidthFit::solve(75., 100., 125., 100., 88.,
            90., [&](double coordinate) {
                ++calls;
                return coordinate == 90. ? previousAdvance : 100.;
            });
        QCOMPARE(selected, previousAdvance == 85. ? 90. : 100.);
        QVERIFY(calls <= FontWidthFit::sampleCount + 1);
    }

    // A blocked adjacent coordinate is not proof that all coordinates nearer
    // the design default are too wide. The 98 candidate must displace history
    // at 94 even though the neighbouring 96 candidate does not fit.
    int calls = 0;
    const double selected = FontWidthFit::solve(75., 100., 150., 100., 92., 94.,
        [&](double coordinate) {
            ++calls;
            if (coordinate == 98.) return 88.;
            if (coordinate == 97.) return 87.;
            if (coordinate == 94.) return 89.;
            return 100.;
        });
    QCOMPARE(selected, 98.);
    QVERIFY(calls <= FontWidthFit::sampleCount + 1);
}

void FontTests::widthSolverBoundsAndNonmonotonic()
{
    const double nan = std::numeric_limits<double>::quiet_NaN();
    const double infinity = std::numeric_limits<double>::infinity();
    const double floatMaximum = std::numeric_limits<float>::max();
    struct Input { double minimum, normal, maximum, natural, available; };
    const std::vector<Input> invalid{
        {101., 100., 125., 100., 80.}, {75., 100., 99., 100., 80.},
        {nan, 100., 125., 100., 80.}, {-infinity, 100., 125., 100., 80.},
        {75., nan, 125., 100., 80.}, {75., infinity, infinity, 100., 80.},
        {75., 100., infinity, 100., 80.}, {75., 100., nan, 100., 80.},
        {-10., 0., 125., 100., 80.}, {-10., -1., 125., 100., 80.},
        {-2. * floatMaximum, 100., 125., 100., 80.},
        {75., 100., 2. * floatMaximum, 100., 80.},
        {75., 100., 125., 0., 80.}, {75., 100., 125., -1., 80.},
        {75., 100., 125., nan, 80.}, {75., 100., 125., infinity, 80.},
        {75., 100., 125., 100., 0.}, {75., 100., 125., 100., -1.},
        {75., 100., 125., 100., nan}, {75., 100., 125., 100., infinity}
    };
    for (const auto &input : invalid) {
        int calls = 0;
        const double selected = FontWidthFit::solve(input.minimum, input.normal,
            input.maximum, input.natural, input.available, nan,
            [&](double) { ++calls; return 90.; });
        QCOMPARE(calls, 0);
        // Malformed metadata is rejected before measurement. The helper returns
        // its unchanged default sentinel; FontManager filters invalid axes
        // before calling it, so a NaN sentinel is never published as a font axis.
        if (std::isnan(input.normal)) QVERIFY(std::isnan(selected));
        else QCOMPARE(selected, input.normal);
    }

    // Roomy text retains the designer default, including when leaving a fitted
    // state. The retained four-pixel entry band is a product choice under test.
    for (const auto [available, previous] : std::array<std::array<double, 2>, 4>{{
             {{110., 100.}}, {{110., 94.}}, {{100., 100.}}, {{96., 100.}}
         }}) {
        int calls = 0;
        QCOMPARE(FontWidthFit::solve(75., 100., 125., 100., available, previous,
            [&](double) { ++calls; return 88.; }), 100.);
        QCOMPARE(calls, 0);
    }

    // A fractional, asymmetric lower range must actually be sampled. The old
    // one-percent steps only tried 99 and 98.7, missing this safe interior fit.
    std::set<double> sampled;
    const double interior = double(float(99.61));
    const double asymmetric = FontWidthFit::solve(98.7, 100., 180., 100., 92., nan,
        [&](double coordinate) {
            sampled.insert(coordinate);
            return std::abs(coordinate - 99.61) < .00005 ? 88. : 100.;
        });
    QCOMPARE(asymmetric, interior);
    QCOMPARE(int(sampled.size()), FontWidthFit::sampleCount);
    QVERIFY(*sampled.begin() >= 98.7);
    QVERIFY(*sampled.rbegin() < 100.);

    // There is only one representable float below 100 in this interval. Ten
    // ideal double samples must not cause ten identical real font measurements.
    const double oneUlpBelow = double(std::nextafter(100.f, 0.f));
    int calls = 0;
    const double quantized = FontWidthFit::solve(oneUlpBelow, 100., 125., 100., 50.,
        nan, [&](double coordinate) {
            ++calls;
            sampled.insert(coordinate);
            return 90.;
        });
    QCOMPARE(calls, 1);
    QCOMPARE(quantized, oneUlpBelow);

    // If nothing is readable, retain default and let the owner elide. When a
    // readable candidate still overflows, select the best measured improvement
    // rather than claiming containment or assuming the lowest axis is best.
    for (const double invalidAdvance : {80., 100., 101., nan, infinity}) {
        calls = 0;
        QCOMPARE(FontWidthFit::solve(75., 100., 125., 100., 50., nan,
            [&](double) { ++calls; return invalidAdvance; }), 100.);
        QVERIFY(calls <= FontWidthFit::sampleCount);
    }
    calls = 0;
    const double overflowing = FontWidthFit::solve(75., 100., 125., 100., 50., nan,
        [&](double coordinate) {
            ++calls;
            if (coordinate == 99.) return 95.;
            if (coordinate == 98.) return 93.;
            if (coordinate == 97.) return 96.;
            return 100.;
        });
    QCOMPARE(overflowing, 98.);
    QVERIFY(calls <= FontWidthFit::sampleCount);

    // This counterexample deliberately documents the finite grid's limitation:
    // an extremely narrow feasible valley between samples can be missed. It is
    // evidence for a bounded approximation, not a global-optimum guarantee.
    const auto narrowValley = [](double coordinate) {
        return std::abs(coordinate - 95.5) < .001 ? 88. : 100.;
    };
    calls = 0;
    QCOMPARE(FontWidthFit::solve(75., 100., 125., 100., 92., nan,
        [&](double coordinate) { ++calls; return narrowValley(coordinate); }), 100.);
    QVERIFY(narrowValley(95.5) <= 92. - FontWidthFit::holdMargin);
    QCOMPARE(calls, FontWidthFit::sampleCount);

    // Exercise all policy/metadata bounds over varying available widths and
    // history, including a collapsed interval and a non-100 designer default.
    const std::array<std::array<double, 3>, 5> axes{{
        {{75., 100., 125.}}, {{98.7, 100., 180.}}, {{90., 95., 110.}},
        {{1., 2., 8.}}, {{100., 100., 100.}}
    }};
    for (const auto &[low, normal, high] : axes) {
        const double minimum = std::max(low, normal * FontWidthFit::minimumAxisRatio);
        for (const double available : {1., 70., 84., 85., 89., 93., 95.9, 96., 100., 104., 200.}) {
            for (const double previous : {normal, minimum, nan, infinity, -1., high + 1.}) {
                calls = 0;
                bool valid = true;
                const double selected = FontWidthFit::solve(low, normal, high, 100.,
                    available, previous, [&](double coordinate) {
                        ++calls;
                        valid &= std::isfinite(coordinate) && coordinate >= minimum
                            && coordinate < normal && coordinate == double(float(coordinate));
                        return 85. + 15. * (coordinate - minimum) / (normal - minimum);
                    });
                QVERIFY(valid);
                QVERIFY(calls <= FontWidthFit::sampleCount + 1);
                QVERIFY(std::isfinite(selected));
                QVERIFY(selected >= minimum && selected <= normal);
            }
        }
    }
}
