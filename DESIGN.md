---
name: Pro Desktop Utility Engine
colors:
  surface: '#0f131c'
  surface-dim: '#0f131c'
  surface-bright: '#353942'
  surface-container-lowest: '#0a0e16'
  surface-container-low: '#181c24'
  surface-container: '#1c2028'
  surface-container-high: '#262a33'
  surface-container-highest: '#31353e'
  on-surface: '#dfe2ee'
  on-surface-variant: '#bdc8d1'
  inverse-surface: '#dfe2ee'
  inverse-on-surface: '#2c3039'
  outline: '#87929a'
  outline-variant: '#3e484f'
  surface-tint: '#7bd0ff'
  primary: '#8ed5ff'
  on-primary: '#00354a'
  primary-container: '#38bdf8'
  on-primary-container: '#004965'
  inverse-primary: '#00668a'
  secondary: '#4edea3'
  on-secondary: '#003824'
  secondary-container: '#00a572'
  on-secondary-container: '#00311f'
  tertiary: '#d5c3ff'
  on-tertiary: '#3c0091'
  tertiary-container: '#bda2ff'
  on-tertiary-container: '#520fbb'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#c4e7ff'
  primary-fixed-dim: '#7bd0ff'
  on-primary-fixed: '#001e2c'
  on-primary-fixed-variant: '#004c69'
  secondary-fixed: '#6ffbbe'
  secondary-fixed-dim: '#4edea3'
  on-secondary-fixed: '#002113'
  on-secondary-fixed-variant: '#005236'
  tertiary-fixed: '#e9ddff'
  tertiary-fixed-dim: '#d0bcff'
  on-tertiary-fixed: '#23005c'
  on-tertiary-fixed-variant: '#5516be'
  background: '#0f131c'
  on-background: '#dfe2ee'
  surface-variant: '#31353e'
typography:
  headline-xl:
    fontFamily: Geist
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Geist
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 24px
    letterSpacing: -0.015em
  headline-md:
    fontFamily: Geist
    fontSize: 15px
    fontWeight: '600'
    lineHeight: 20px
    letterSpacing: -0.01em
  body-lg:
    fontFamily: Geist
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  body-md:
    fontFamily: Geist
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 18px
  body-sm:
    fontFamily: Geist
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
  code-lg:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: '500'
    lineHeight: 18px
    letterSpacing: -0.01em
  code-md:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
    letterSpacing: -0.01em
  code-sm:
    fontFamily: JetBrains Mono
    fontSize: 11px
    fontWeight: '400'
    lineHeight: 14px
    letterSpacing: 0em
  label-caps:
    fontFamily: Geist
    fontSize: 11px
    fontWeight: '600'
    lineHeight: 14px
    letterSpacing: 0.06em
  shortcut-key:
    fontFamily: JetBrains Mono
    fontSize: 10px
    fontWeight: '600'
    lineHeight: 12px
    letterSpacing: 0.02em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  gutter: 0.75rem
  margin: 1rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 0.75rem
  space-lg: 1rem
  space-xl: 1.5rem
---

## Brand & Style

This design system targets power users, systems engineers, and technical professionals who require precision, control, and zero visual friction. The brand personality is disciplined, analytical, hyper-focused, and robust—channeling the tactile precision of high-end developer workstations and modern cross-platform desktop frameworks (Tauri, Rust, Electron). 

The visual movement blends **Technical Minimalism** with **Tactile Density**:
- **Information Density:** Zero wasted space, tight structural baselines, and maximum data-to-pixel ratio without visual overcrowding.
- **Micro-Precision Borders:** Deeply layered structural segmentation using crisp, low-opacity 1px borders rather than diffuse, muddy drop shadows.
- **Keyboard-Centric Affordance:** Explicit hotkey visual tags (`⌘K`, `⇧D`, `⌥↵`), clear selection reticles, and strong active-state affordances across every interactive primitive.
- **Diagnostic Color Accents:** Strict functional semantic roles for quick visual scanning— emerald and cyan for unique signatures, amber for collisions, violet for cold storage, and crimson for destructed artifacts.

## Colors

The system uses a calibrated multi-tiered dark foundation paired with surgical neon-spectral accents designed specifically for high-contrast OLED/IPS desktop displays.

### Foundation Tiers
- **Canvas Base (Deep Space):** `#0B0F17` – System window backgrounds, title bar gutters, and root panels.
- **Surface Elevation 1 (Slate Core):** `#111827` – Sidebars, utility trays, card backgrounds, and data tables.
- **Surface Elevation 2 (Zinc Float):** `#1F2937` – Hover rows, active input fields, segmented buttons, and modal dialogs.
- **Structural Outlines:** `#374151` (Resting), `#4B5563` (Interactive), `#60A5FA` (Focused outline).

### Data Diagnostic Accents
- **Primary / Active Stream:** `#38BDF8` (Cyan) – Cursor targets, global selection state, focus indicators, and active filters.
- **Health / Unique / Valid:** `#10B981` (Emerald) – Hash verification, optimized assets, healthy state tokens, low memory usage.
- **Warning / Duplicate / Attention:** `#F59E0B` (Amber) – Collision alerts, redundant directories, pending operations, elevated CPU state.
- **Archive / Cold Storage / System:** `#8B5CF6` (Violet) – Compressed blocks, system caches, indexed databases, metadata states.
- **Destructive / Freed Space / Error:** `#EF4444` (Crimson) – Purged memory, deleted duplicates, critical errors, blocked processes.

### Text & Glyph Hierarchy
- **Text High-Contrast:** `#F9FAFB` (Headers, active data readouts, primary labels).
- **Text Medium-Contrast:** `#9CA3AF` (Secondary parameters, column headers, metadata).
- **Text Muted / Low-Contrast:** `#6B7280` (Disabled states, hash separators, keyboard glyphs).

## Typography

Typography prioritizes tabular legibility, vertical alignment consistency, and unambiguous glyph differentiation.

- **Primary UI Sans (Geist):** Handles standard user interface elements, titles, menu navigation, body text, and dynamic labels. It provides a sharp, neutral, zero-distortion reading experience.
- **Technical Monospace (JetBrains Mono):** Dedicated to technical strings—UUIDs, MD5/SHA256 hashes, file system paths, memory offsets, byte counts, and raw terminal feedback. Numbers in standard tables default to tabular figures (`font-variant-numeric: tabular-nums`).
- **Caps & Badges:** `label-caps` must always be rendered in `uppercase` to distinguish structural category headers (e.g., `SCAN RULES`, `SYSTEM VOLUMES`) from runtime content values.

## Layout & Spacing

The layout is built for multi-window desktop orchestration using a structural dock-and-panel architecture rather than standard web scroll pages.

- **Primary Shell Layout:** Fixed left sidebar (collapsed at `56px`, expanded at `220px`), persistent system health topbar (`40px`), contextual sub-panel or file inspector (`320px` right panel, collapsible), and an elastic center canvas that hosts tabular data or split diff views.
- **Rhythm & Metrics:** An uncompromising **4px baseline grid**. Standard UI controls are constrained to desktop-optimized heights: `24px` (dense toolbar buttons), `28px` (standard input fields and controls), and `32px` (prominent actions).
- **Tabular Rows:** Compact density runs at `28px` row height; standard density runs at `36px` row height.
- **Responsive Adaptability (Desktop Windows):**
  - `< 960px`: Collapse file inspector panel into floating sliding overlay; sidebar switches to icon-only rail (`56px`).
  - `960px - 1440px`: Full 3-column operational layout (Navigation rail, Active work canvas, File comparison inspector).
  - `> 1440px`: Expand file comparison pane into side-by-side bidirectional visual diffing canvas.

## Elevation & Depth

Visual depth is achieved through **Tonal Boundary Layering** combined with **Surgical Inset Accents**, completely rejecting fuzzy consumer-grade drop shadows.

- **Base Floor (Z-0):** Window canvas at `#0B0F17`.
- **Structural Inset / Surface Tier (Z-1):** Sidebars and nested toolbars at `#111827`, delineated by a crisp `1px solid rgba(255, 255, 255, 0.07)` border.
- **Raised Interactive Panels (Z-2):** Metric cards and contextual panels at `#1F2937` with an inner top highlight border: `box-shadow: inset 0 1px 0 0 rgba(255, 255, 255, 0.06)`.
- **Overlays / Command Palettes (Z-3):** Quick-switcher palettes (`⌘K`) and context menus float using a deep dark backdrop blur (`backdrop-filter: blur(12px) bg-[#111827]/90`), surrounded by a high-contrast boundary: `1px solid rgba(56, 189, 248, 0.25)` and a clean ambient drop: `box-shadow: 0 16px 32px -8px rgba(0, 0, 0, 0.7)`.

## Shapes

The geometric identity is calibrated to `roundedness: 1` (Soft/Crisp Precision):
- **Base Components (Buttons, Inputs, Badges):** `4px` (`0.25rem`) border radius. This delivers an engineered, technical look that avoids consumer "pill" roundness.
- **Cards, Modals, & Dock Panels:** `6px` to `8px` (`rounded-lg`), maximizing readable interior space without corner clipping.
- **Kbd / Shortcut Tags:** `3px` corner radius with strict square symmetry on single glyphs (`18px × 18px`).
- **Segmented Progress / Breakdown Bars:** `2px` micro-radii on segments to maintain visual connection between contiguous data slices.

## Components

### Buttons & Quick Triggers
- **Primary Action:** Background `#38BDF8`, text `#0B0F17`, weight `600`, height `28px`, padding `0 12px`. Hover state lightens to `#7DD3FC`. Active state snaps down with a `transform: scale(0.98)`.
- **Secondary Ghost:** Background `transparent`, border `1px solid #374151`, text `#F9FAFB`. Hover state introduces `#1F2937` background and `#4B5563` border.
- **Destructive Flush Button:** Background `rgba(239, 68, 68, 0.1)`, border `1px solid rgba(239, 68, 68, 0.3)`, text `#EF4444`. Includes an embedded shortcut tag (e.g., `⌘⌫`).

### Data Breakdown & Metric Cards
- **Metric Cards:** `#111827` background, `1px solid #1F2937` perimeter. Contains category micro-label in `label-caps` (`#9CA3AF`), huge tabular data metric (`20px` Geist Semibold), and delta micro-pill (e.g., `+14.2 GB` in emerald or crimson).
- **Segmented Storage / Duplicate Bar:** Multi-segment horizontal track (`8px` tall) composed of colored fractional segments (Cyan: unique files, Amber: duplicates, Violet: system images, Dark Gray: unallocated). Hovering any slice displays an interactive tooltip with size and file count.

### Tabular Lists & Data Grid
- **Header:** Sticky `24px` height, `#0B0F17` background, `label-caps` text in `#6B7280`, 1px bottom border `#1F2937`.
- **Rows:** Alternating subtle row highlights or uniform dark rows with `1px solid rgba(255, 255, 255, 0.02)`. Active row highlighted in `rgba(56, 189, 248, 0.08)` with a left indicator notch (`2px` solid `#38BDF8`).
- **Data Cells:** JetBrains Mono for hashes and paths; paths truncate with middle ellipsis (`/usr/.../cache.db`).

### Action Toolbars & Keyboard Accents
- **Command Bar:** Integrated filter input alongside action buttons. Keyboard tags (`KBD`) rendered with `#111827` background, `#374151` 1px border, `#9CA3AF` color, and `3px` radius.
- **Filter Chips:** Toggled states with distinct semantic count tags (e.g., `Duplicates (4,129)` with an amber count badge).

### File Comparison Panels (Diff Split View)
- Dual-column pane divided by a draggable `2px` splitter (`#1F2937`).
- Redundant lines highlighted in `rgba(239, 68, 68, 0.12)` with crimson gutter markers; optimized replacements highlighted in `rgba(16, 185, 129, 0.12)` with emerald gutter markers. Monospace code font locked to strict `16px` line-height alignment across both panes.
