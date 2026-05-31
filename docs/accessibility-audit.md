# Accessibility Audit Report

## Audit Overview

- **Product**: Blackbeard Frontend (React + TypeScript SPA)
- **Scope**: Layout, Login, Register, Toast, Palette, PropertyPanel, Dashboard, ErrorAlert, Spinner
- **Standard**: WCAG 2.1 Level AA
- **Date**: 2026-05-31

## Testing Methodology

- **Manual code review**: All 8 target files reviewed for semantic HTML, ARIA usage, keyboard support, focus management, heading hierarchy, label associations, and color contrast risk areas.
- **Keyboard navigation**: Evaluated tab order, focus indicators, Escape handling, and keyboard traps.
- **Screen reader semantics**: Evaluated roles, states, properties, live regions, and announcement behavior.
- **Visual testing considerations**: Identified font sizes below 10px, `text-muted-foreground` contrast risk areas, and `motion-reduce` support.

## Summary

- **Total Issues Found**: 14
  - Critical: 1
  - Major: 5
  - Minor: 8
- **WCAG Conformance**: PARTIALLY CONFORMS (no critical blockers after fixes applied)
- **Issues Fixed Directly**: 6

---

## Issues Found

### Issue 1: Toast container `aria-live` causes double announcements with child `role="alert"` / `role="status"` [FIXED]

- **WCAG Criterion**: 4.1.3 Status Messages (Level AA)
- **Severity**: Major
- **File**: `frontend/src/components/ui/Toast.tsx`, line 81
- **User Impact**: Screen reader users may hear toast messages announced twice -- once from the container's `aria-live="polite"` and again from each toast item's `role="alert"` or `role="status"`. Error toasts use `role="alert"` (which implies `aria-live="assertive"`), creating a conflict with the container's `polite` politeness level.
- **Fix Applied**: Removed `aria-live="polite"` from the container `div`. Each `ToastItem` already carries the appropriate role (`role="alert"` for errors, `role="status"` for success/info), which handles live-region announcements at the correct urgency level.

### Issue 2: NavSection `aria-expanded` button missing `aria-controls` [FIXED]

- **WCAG Criterion**: 4.1.2 Name, Role, Value (Level A)
- **Severity**: Major
- **File**: `frontend/src/components/Layout.tsx`, line 137-139
- **User Impact**: Screen reader users hear that a section is expanded/collapsed but cannot programmatically determine which content region the button controls. Assistive technologies that support `aria-controls` (like JAWS) cannot jump to the controlled region.
- **Fix Applied**: Added `aria-controls={nav-section-${section.key}}` to the toggle button and `id={nav-section-${section.key}}` to the collapsible content `div`.

### Issue 3: ProjectSwitcher dropdown lacks ARIA listbox semantics [FIXED]

- **WCAG Criterion**: 4.1.2 Name, Role, Value (Level A)
- **Severity**: Major
- **File**: `frontend/src/components/Layout.tsx`, lines 310-333
- **User Impact**: Screen reader users encounter the project list as a set of generic buttons with no indication that they form a single-select list or which project is currently selected. The dropdown behaves like a listbox but lacks `role="listbox"`, `role="option"`, and `aria-selected` attributes.
- **Fix Applied**: Added `role="listbox"` and `aria-label="Available projects"` to the scrollable container. Each project button now has `role="option"` and `aria-selected={ns === current}`. The loading spinner inside the dropdown now has `role="status"` with a screen-reader-only label. The trigger button now has `aria-haspopup="listbox"`.

### Issue 4: Notification button missing `aria-haspopup` [FIXED]

- **WCAG Criterion**: 4.1.2 Name, Role, Value (Level A)
- **Severity**: Major
- **File**: `frontend/src/components/Layout.tsx`, line 749-760
- **User Impact**: Screen reader users are not informed that this button opens a popup panel. The `aria-expanded` attribute is present, but `aria-haspopup` is needed to communicate the button's popup behavior before the user activates it.
- **Fix Applied**: Added `aria-haspopup="true"` to the notification bell button.

### Issue 5: CrewComponentCard uses 8px text that fails minimum font size guidelines [FIXED]

- **WCAG Criterion**: 1.4.4 Resize Text (Level AA)
- **Severity**: Major
- **File**: `frontend/src/components/studio/Palette.tsx`, lines 299-300
- **User Impact**: The crew card summary text ("3A", "2T") uses `text-[8px]` which is below the practical minimum for readability, even with good contrast. At 8px, text becomes unreadable at 200% zoom for many users. The abbreviations also lack full-text alternatives.
- **Fix Applied**: Increased from `text-[8px]` to `text-[10px]` and added `aria-label` attributes with expanded text (e.g. "3 agents", "2 tasks").

### Issue 6: "My Crews" section label uses 9px text and lacks group semantics [FIXED]

- **WCAG Criterion**: 1.3.1 Info and Relationships (Level A)
- **Severity**: Minor (upgraded to fix since touched the file)
- **File**: `frontend/src/components/studio/Palette.tsx`, lines 353-356
- **User Impact**: The "My Crews" label uses `text-[9px]` which is very small, and the section lacks grouping semantics for screen readers.
- **Fix Applied**: Increased to `text-[10px]`, added `role="group"` with `aria-label="My Crews"` on the wrapper, and marked the visual label `aria-hidden="true"` to avoid redundant announcements.

---

### Issue 7: NotificationPanel does not trap or manage focus on open (NOT FIXED - architectural)

- **WCAG Criterion**: 2.4.3 Focus Order (Level A)
- **Severity**: Minor
- **File**: `frontend/src/components/Layout.tsx`, lines 768-806
- **User Impact**: When the notification panel opens, focus stays on the bell button. Keyboard users must Tab forward to find the panel content. Because the panel is rendered inside the sidebar footer, it may require many Tab presses to reach. The panel closes on Escape (good), but focus should move into the panel on open for discoverability.
- **Recommendation**: On open, move focus to the first interactive element inside the panel (e.g., the "Mark all read" button, or the panel heading). On close, return focus to the bell button.

### Issue 8: `text-muted-foreground` on various backgrounds may not meet 4.5:1 contrast

- **WCAG Criterion**: 1.4.3 Contrast (Minimum) (Level AA)
- **Severity**: Minor
- **Files**: Multiple (Layout.tsx, Dashboard.tsx, Login.tsx, Register.tsx, Palette.tsx)
- **User Impact**: The `text-muted-foreground` color token is used extensively for secondary text. Depending on the theme's actual HSL values, this may not meet the 4.5:1 minimum contrast ratio against `bg-background`, `bg-card`, or `bg-muted` backgrounds. Common shadcn/ui defaults for muted-foreground are around `hsl(215.4 16.3% 46.9%)` which provides approximately 4.6:1 on white, passing narrowly. However, `text-muted-foreground/70` (used on NavSection labels and "My Crews" label) reduces opacity to 70%, which will reduce contrast below the threshold.
- **Recommendation**: Audit the CSS custom property values for `--muted-foreground` in both light and dark themes. Replace `text-muted-foreground/70` usages with full `text-muted-foreground` or a dedicated token that meets 4.5:1.

### Issue 9: Dashboard stat cards use `<Link>` for navigation, which is correct, but screen readers announce verbose aria-labels

- **WCAG Criterion**: 2.4.4 Link Purpose (Level A)
- **Severity**: Minor
- **File**: `frontend/src/pages/Dashboard.tsx`, lines 56-59
- **User Impact**: The `aria-label` on StatCard (e.g. "Total Resources: 42") is good and provides context. No fix needed, but the loading state announces "Total Resources: loading" which is slightly awkward.
- **Recommendation**: Consider changing to "Total Resources: loading, please wait" or wrapping the loading skeleton in its own `role="status"`.

### Issue 10: Palette search filter has no live announcement of results count

- **WCAG Criterion**: 4.1.3 Status Messages (Level AA)
- **Severity**: Minor
- **File**: `frontend/src/components/studio/Palette.tsx`, lines 307-340
- **User Impact**: When a user types in the filter input, the palette items update visually, but screen reader users get no feedback about how many items match. They must Tab through the results to discover what's available.
- **Recommendation**: Add an `aria-live="polite"` region that announces the count of matching items (e.g. "5 of 15 nodes shown" or "No matches").

### Issue 11: Register page form does not use `aria-errormessage` (uses `aria-describedby` instead)

- **WCAG Criterion**: 3.3.1 Error Identification (Level A)
- **Severity**: Minor
- **File**: `frontend/src/pages/Register.tsx`, lines 97-108
- **User Impact**: The form uses `aria-describedby` pointing to error messages, which works and is announced by screen readers. Using `aria-errormessage` (ARIA 1.1+) would be more semantically precise, but `aria-describedby` has broader support. No action required, but `aria-errormessage` is the recommended modern approach.
- **Recommendation**: Consider migrating to `aria-errormessage` for error associations, keeping `aria-describedby` for hint/description text only.

### Issue 12: PropertyPanel FieldGroup generates non-unique IDs for fields with identical labels

- **WCAG Criterion**: 4.1.1 Parsing / 1.3.1 Info and Relationships (Level A)
- **Severity**: Minor
- **File**: `frontend/src/components/studio/PropertyPanel.tsx`, line 132
- **User Impact**: The `fieldId` is generated as `panel-${label.toLowerCase().replace(...)}`. If two different node forms are rendered at the same time (unlikely in single-panel view but possible in future), or if a form has two fields with the same label, the IDs would collide. Labels like "Description" appear in multiple form types (AgentForm, TaskForm).
- **Recommendation**: Include the node ID or form type in the generated field ID to guarantee uniqueness.

### Issue 13: Mobile hamburger menu does not set `aria-controls`

- **WCAG Criterion**: 4.1.2 Name, Role, Value (Level A)
- **Severity**: Minor
- **File**: `frontend/src/components/Layout.tsx`, lines 581-588
- **User Impact**: The mobile menu button has `aria-expanded` and a descriptive `aria-label`, but no `aria-controls` pointing to the sidebar `<aside>`. While `aria-controls` has limited AT support, it is the recommended pattern per WAI-ARIA Authoring Practices.
- **Recommendation**: Add `id="main-sidebar"` to the `<aside>` and `aria-controls="main-sidebar"` to the hamburger button.

### Issue 14: Palette instruction text uses 10px font

- **WCAG Criterion**: 1.4.4 Resize Text (Level AA)
- **Severity**: Minor
- **File**: `frontend/src/components/studio/Palette.tsx`, lines 365-367
- **User Impact**: The instruction text "Drag onto canvas or press Enter/Space to add" uses `text-[10px]`. While this passes as supplementary instruction text, it is very small. At 200% zoom it renders at 20px which is adequate.
- **Recommendation**: Consider increasing to `text-xs` (12px) for better baseline readability.

---

## What's Working Well

These patterns are well-implemented and should be preserved:

- **Skip navigation link**: Layout.tsx includes a proper "Skip to main content" link (line 571-575) that becomes visible on focus. Good implementation.
- **Focus indicators**: All interactive elements consistently use `focus-visible:ring-2 focus-visible:ring-ring`, providing clear, visible focus indicators.
- **Mobile menu focus management**: When the mobile sidebar opens, focus moves to the first link. When it closes, focus returns to the hamburger button (lines 449-459). Escape key closes the sidebar.
- **Minimum touch target sizes**: Buttons consistently use `min-h-[44px] min-w-[44px]` ensuring WCAG 2.5.5 (AAA) / 2.5.8 (AA) compliance for touch targets.
- **`inert` attribute usage**: The main content area gets `inert` when the mobile sidebar is open, and the full layout gets `inert` during the guided tour, preventing focus from escaping to background content.
- **Form accessibility on Login/Register**: Both forms have proper `<label htmlFor>` associations, `aria-required`, `aria-invalid`, `aria-describedby` pointing to error messages, and `autoComplete` attributes.
- **Password visibility toggle**: Both Login and Register pages have properly labeled show/hide password buttons with dynamic `aria-label`.
- **ErrorAlert component**: Has `role="alert"`, `aria-hidden="true"` on the icon, a screen-reader-only "Error:" prefix, and proper button labels for actions.
- **Spinner component**: Uses `role="status"` (implicit `aria-live="polite"`), `aria-hidden="true"` on the spinning icon, and a screen-reader-only label.
- **Skeleton components**: All skeleton variants use `role="status"`, `aria-label`, and screen-reader-only "Loading..." text.
- **Heading hierarchy**: Dashboard uses `<h1>` (via PageHeader) followed by `<h2>` for each section, with proper `id` + `aria-labelledby` pattern.
- **Data table accessibility**: The recent executions table has `scope="col"` on headers, a screen-reader-only "Details" column header, and clickable rows with keyboard support (`onKeyDown` for Enter/Space) and descriptive `aria-label`.
- **Meter roles**: Resource and spend bar charts use `role="meter"` with `aria-valuenow`, `aria-valuemin`, `aria-valuemax`, and `aria-label`.
- **Motion preferences**: Animations use `motion-reduce:transition-none` or `motion-reduce:animate-none` throughout, respecting `prefers-reduced-motion`.
- **Palette keyboard alternatives**: Each draggable palette card has `role="button"`, `tabIndex={0}`, and `onKeyDown` handlers for Enter/Space, providing a complete keyboard alternative to drag-and-drop.
- **Toast pause on focus/hover**: Toasts pause their dismiss timer on both `onFocus` and `onMouseEnter`, giving keyboard and pointer users equal time to read them.

## Remediation Priority

### Immediate (fixed in this audit)

1. Toast container double-announcement removed (Issue 1)
2. NavSection `aria-controls` added (Issue 2)
3. ProjectSwitcher listbox semantics added (Issue 3)
4. Notification button `aria-haspopup` added (Issue 4)
5. CrewComponentCard 8px text increased and labeled (Issue 5)
6. "My Crews" section grouping and font size fixed (Issue 6)

### Short-term (fix within next sprint)

1. Notification panel focus management on open/close (Issue 7)
2. Audit `text-muted-foreground/70` contrast values in both themes (Issue 8)
3. Add live region for palette filter results count (Issue 10)
4. Add `aria-controls` to mobile hamburger button (Issue 13)

### Ongoing (address in regular maintenance)

1. Evaluate `aria-errormessage` migration (Issue 11)
2. Make PropertyPanel field IDs more unique (Issue 12)
3. Review all `text-[10px]` usages for readability (Issue 14)
4. Consider richer loading-state aria-labels (Issue 9)
