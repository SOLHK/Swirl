# Stage B: native design system

The shared control system uses a near-white canvas, neutral surface hierarchy,
one primary action treatment, consistent keyboard focus, and semantic disabled,
error and selection states. Existing font-axis resolution and native hinting
remain unchanged. The locked sidebar/window geometry and Activity arrangement
are not redesigned.

New reusable components are `SwirlControlSurface`, `SwirlSlider`,
`SwirlRadioButton`, `SwirlPageHeader` and `SwirlSectionTitle`. Buttons, text
inputs, multiline editors, search, checkboxes, switches, segments, scrollbars,
menus, dropdowns, dialogs, tooltips, status badges and empty states use the
shared tokens. The title components wrap content and place actions below the
heading in compact viewports. Destructive confirmation retains its lifecycle
and focus hooks while creating its explanatory body only when needed.

Popup and dropdown movement combines a small spatial expansion with opacity.
Exit timing is shorter; interrupted transitions continue from their current
presentation. New installations follow Windows reduced-motion settings by
default; existing explicit preferences are retained.

Hallmark's app-screen hierarchy and real-state rules, UI/UX Pro Max's focus and
interruptible-state guidance, LottieFiles' directional timing, and Qt's native
control/lifecycle rules informed these changes. Source and license details are
in `V3_IMPLEMENTATION.md`.

Validation before the stage commit: 22 shared QML files passed syntax/type
error checks; five new components also had zero qmllint warnings. Context-
property warnings in existing code remain. A native intermediate integration
smoke visited 61 routes successfully. That intermediate binary is not final
same-commit visual or performance acceptance; full interaction, font, motion,
rendering and installer checks remain part of stages C–E.
