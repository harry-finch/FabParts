---
name: pyside-ui-ux
description: Design, refactor, or review KiPart Manager PySide6 interfaces for visual quality, usability, consistency, responsive layouts, and reusable UI components.
---

# KiPart Manager — PySide6 UI/UX workflow

Use this skill whenever creating, significantly modifying, or reviewing user-facing PySide6 interfaces.

## Shared visual reference

Use [Professional Workshop UI](../../../.agents/skills/professional-workshop-ui/SKILL.md) for the
shared visual language. This skill adds the KiPart Manager integration and
verification conventions. Preserve user-requested scope and all domain rules.

## Objective

KiPart Manager must look and behave like a deliberate modern desktop application, not a collection of default Qt widgets assembled for functional testing.

Functional correctness remains mandatory, but visual hierarchy, spacing, consistency, discoverability, and interaction quality are also acceptance criteria.

## General principles

Prefer:

- clear visual hierarchy;
- restrained desktop UI;
- consistent spacing;
- readable typography;
- predictable navigation;
- reusable presentation components;
- useful empty states;
- explicit status feedback;
- contextual actions;
- progressive disclosure of complexity.

Avoid:

- arbitrary widget placement;
- excessive borders and frames;
- dense forms with no grouping;
- default Qt appearance when a small amount of styling materially improves clarity;
- inconsistent button sizes or alignment;
- modal dialogs for actions that fit naturally in the main workflow;
- giant forms shown all at once;
- decorative visual effects that reduce legibility.

## Application shell

Prefer a stable application structure:

- top-level application window;
- persistent left navigation/sidebar when appropriate;
- main content area;
- consistent page header;
- primary action placed consistently;
- optional secondary/detail panel for contextual information.

Initial major navigation may include:

- Components
- Inventories
- Collections
- KiCad Local
- Publications
- Settings

Do not add navigation entries for functionality that does not yet exist.

## Page hierarchy

A normal page should generally contain:

1. page title;
2. short contextual description when useful;
3. primary action;
4. search/filter controls where relevant;
5. main content;
6. selection/detail area where relevant.

Do not force every page into exactly the same layout if its workflow requires something different.

## Spacing

Use a small consistent spacing scale rather than arbitrary values.

For example, conceptually:

- XS
- S
- M
- L
- XL

Centralize recurring spacing values where practical.

Avoid extremely compact default Qt layouts.

Give related controls proximity and unrelated groups sufficient separation.

## Typography

Establish a small hierarchy:

- application/page title;
- section heading;
- normal content;
- secondary metadata;
- status/helper text.

Do not create many arbitrary font sizes.

Prefer the system UI font unless there is a strong reason otherwise.

## Colors

Use restrained semantic colors.

Semantic states:

- success / PASS;
- warning / WARNING;
- error / ERROR;
- informational / neutral.

Do not rely on color alone to communicate state. Combine it with text and/or iconography.

Do not hard-code semantic colors throughout individual widgets. Centralize styling/theme values.

## Status components

Create reusable presentation for states such as:

- PASS
- WARNING
- ERROR
- DRAFT
- VALIDATED
- PUBLISHED
- missing asset
- official KiCad asset
- user-provided asset

Use badges/chips/status indicators consistently.

## Icons

Use one coherent icon source/style.

Prefer Qt/system-supported or a deliberately selected lightweight icon set.

Icons should clarify actions, not decorate every label.

Always retain text for non-obvious actions.

## Forms

For component and asset forms:

- align labels and controls;
- group related fields;
- distinguish required from optional information;
- show validation close to the relevant field;
- avoid forcing users to complete irrelevant fields;
- preserve entered data when validation fails.

Use sensible control types rather than free-text fields for everything.

## Tables and lists

Tables are important in KiPart Manager.

Requirements:

- readable column spacing;
- sensible default widths;
- sortable columns where useful;
- selection state clearly visible;
- row actions should not clutter every row unnecessarily;
- search/filter should be easy to find;
- important statuses should be visually scannable;
- identifiers should not dominate over human-readable names.

When a table becomes too wide, reconsider the information architecture rather than simply adding more columns.

## Master/detail workflows

For entities such as Components or KiCad Local resources, prefer a master/detail structure when useful:

- list/table on one side or main area;
- selected-item details in a contextual panel or page.

Avoid opening a new dialog for every inspection action.

## Empty states

Every significant empty page/list should explain:

- what is empty;
- why that might be;
- the next useful action.

Example:

"No components yet. Add a component to start building your catalogue."

Prefer an action button when there is an obvious next step.

## Destructive actions

Destructive actions must:

- be visually distinct but not dominant;
- require confirmation when data loss is significant;
- explain what will actually be removed;
- avoid ambiguous labels like "OK".

## Responsiveness

Layouts must remain usable when the window is resized.

Avoid fixed pixel geometry for main layout structure.

Use Qt layouts, stretch factors, size policies, splitters, and sensible minimum sizes.

Test at least:

- normal desktop size;
- moderately narrow window;
- large window.

## Styling architecture

Do not spread large QSS strings across arbitrary widgets.

Prefer a small centralized styling/theme layer.

Keep domain/application logic independent from presentation styling.

Reusable UI elements should live in an appropriate UI components/widgets package.

Do not build a custom design-system framework prematurely.

## Interaction quality

Where applicable:

- disable impossible actions rather than letting them fail later;
- explain disabled states when not obvious;
- show loading/progress for operations that take noticeable time;
- show success/error feedback without unnecessary modal dialogs;
- maintain selection when refreshing data if possible;
- make keyboard navigation reasonable.

## Accessibility and usability

Ensure:

- readable contrast;
- visible focus states;
- controls have labels/tooltips where needed;
- the interface does not depend exclusively on icons or colors;
- tab order is sensible for important forms.

## Refactoring rule

When improving an existing ugly but functional UI:

1. preserve working business behavior;
2. identify repeated visual patterns;
3. establish the shell/navigation;
4. establish shared spacing/theme/components;
5. refactor screens progressively;
6. avoid rewriting domain/application code solely for visual reasons.

Do not combine a visual refactor with unrelated architecture changes unless required.

## Verification

Before completing UI work:

1. run existing tests;
2. add tests only where UI logic meaningfully warrants them;
3. launch the application;
4. inspect every modified screen manually;
5. resize the window;
6. inspect empty, populated, selected, warning, and error states available in the current milestone;
7. check consistency across screens.

At a milestone checkpoint, report:

- screens changed;
- reusable components introduced;
- important UX decisions;
- manual visual checks performed;
- remaining visual debt.

Do not claim a UI is polished based solely on automated tests.


## Established KiPart Manager conventions

Read [UI_GUIDELINES.md](../../../docs/UI_GUIDELINES.md) before adding or changing
screens; inspect the current primitives rather than introducing a parallel style.

- Preserve the six task spaces and secondary tabs described in the guide.
  Optional services absent from a composition do not create placeholder pages.
- Reuse the durable primitives in ui/components.py: PageLayout, PageHeader,
  SectionCard, ScrollPanel, SearchBar, EmptyState, StatusBadge, MessageBanner,
  DetailText and primary(). Compose existing layouts rather than building a generic
  master/detail framework. ResourceRow and WorkflowStrip serve the component workflow;
  Disclosure hides secondary help and technical properties.
- Use theme.py for QSS/palette and XS/S/M/L/XL spacing (4/8/12/16/24). Keep the current
  dark Fusion appearance; no screen-specific palette or copied stylesheet.
- Keep UUIDs and hashes in contextual/advanced technical details, not main rows.
  Keep plain-text metadata selectable and wrapped, using DetailText.
- Association is not selection; selection is not qualification; collection
  membership is not publication. PUBLISHED describes an engaged version;
  PASS/ERROR after verification describe observed integrity. Never infer status
  from badge color or manufacture domain states.
- Use contextual text actions and explanatory empty states. Disable actions that
  require missing selection, preserve valid selection/filter on refresh, and clear
  stale feedback when the context changes. Preserve explicit M4/M5/M8 confirmations.
- Keep form actions outside scrolling fields; use scrolling detail panels when
  actions would overlap at narrow sizes. Inspect populated/empty/error/warning
  states at approximately 1200×800, 900×680 and 1600×950 (subject to screen limits).

For a consistency-only task, retain current behavior and appearance, factor only
clear repetitions and document actual patterns. Use primary(), quiet() and the
central destructive role; do not introduce deletion behavior as a visual cleanup.
Lucide SVGs are local in ui/icons (license packaged), loaded by ui/icons.py.
Keep ordinary provenance muted; qualification uses lightweight semantic labels,
not colored pills. The component catalogue has 32 px rows, numeric stock sorting,
an identity-preserving selection and a local state filter.
Routine entity editors are modeless and single-instance per window. Preserve the
existing modal decisions for resource replacement, import/export and qualification.
AI stays in Documentation with a contextual shortcut from the component; preserve
per-request consent and human acceptance. Existing A1 viewers remain read-only.
