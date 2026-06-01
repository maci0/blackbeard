# PRD 12  -- Onboarding & First-Run Experience

## 1. Purpose

Provide a guided first-run experience that helps new users understand Blackbeard's value, navigate the platform, and successfully build and run their first crew  -- all within the first 5 minutes of opening the UI.

### 1.1 MVP Scope

**Implemented:** Onboarding wizard  -- a 5-step welcome dialog that introduces new users to the platform on first visit, stored in localStorage. The "Load Example" button is available on the empty canvas.

**Implemented (beyond MVP):**
- Global keyboard shortcuts: `Cmd+Shift+S` (save), `Cmd+Shift+E` (executions), `Cmd+Shift+N` (new resource), `Cmd+.` (settings), `?` (shortcuts dialog). Keyboard shortcuts dialog accessible from the Help menu or by pressing `?`.
- Loading skeletons: Dashboard, Chat, and KnowledgeSources pages display pulse-animated placeholder shapes while data loads, replacing blank/flashing states.

**Implemented (post-MVP):** Guided tour with spotlight overlay (`GuidedTour` component), step-by-step tooltip walkthrough of Studio UI elements. Help menu with "Restart tour" option and documentation links.

**Deferred to post-MVP:** Progressive disclosure (contextual tooltips on first interaction), interactive tutorial, "What's new" dialog.

---

## 2. Problem Statement

Today, a new user who opens Blackbeard sees the Studio with an empty canvas and a palette sidebar. There is no explanation of what the platform does, what the workflow is, or how to get started. The user must already know CrewAI concepts (agents, tasks, crews) and Blackbeard's resource model to be productive. This creates a steep learning curve that blocks adoption.

## 3. Target Users

| Persona | Need |
|---------|------|
| **First-time user** | Understand what Blackbeard is and how to use it |
| **AI/ML developer new to CrewAI** | Learn the agent → task → crew mental model |
| **Returning user** | Quick access to "what's new" or re-trigger the tour |

## 4. Design Principles

| # | Principle | Implication |
|---|-----------|-------------|
| 1 | **Non-blocking** | The wizard can be dismissed at any time. Never force completion. |
| 2 | **Progressive disclosure** | Show only what's needed at each step. Don't overwhelm. |
| 3 | **Learn by doing** | Guide users to perform real actions, not just read text. |
| 4 | **Persistent but respectful** | Remember completion state in localStorage. Offer a "Restart tour" option in the sidebar. |
| 5 | **Zero backend dependency** | The onboarding is purely frontend  -- no API calls, no database state. |

## 5. Components

### 5.1 Welcome Dialog (first visit)

A modal dialog shown on the very first visit (no `blackbeard_onboarding_completed` in localStorage).

**Content:**
- Blackbeard logo/name
- One-line description: "Build, run, and manage AI agent crews visually"
- Three value propositions with icons:
  1. **Visual Studio**  -- Drag-and-drop agents, tasks, and tools on a canvas
  2. **One-Click Run**  -- Execute crews and watch results in real-time
  3. **Full Lifecycle**  -- Manage resources, monitor executions, track costs
- Two CTAs:
  - **"Get Started"** → Starts the guided tour (navigates to Studio)
  - **"Skip"** → Dismisses, sets localStorage flag, goes to Studio

### 5.2 Guided Tour (Studio walkthrough)

After clicking "Get Started", a step-by-step tooltip tour highlights key UI elements:

| Step | Target Element | Title | Description |
|------|---------------|-------|-------------|
| 1 | Palette sidebar | **Palette** | Drag agents, tasks, and tools from here onto the canvas. |
| 2 | Canvas area | **Canvas** | This is your workspace. Connect nodes to define your crew's workflow. |
| 3 | Crew name input | **Name Your Crew** | Give your crew a name  -- it becomes the resource identifier. |
| 4 | Save button | **Save** | Save your crew and all its resources to the server. |
| 5 | Run button | **Run** | Execute your crew. You'll see results in the Executions page. |
| 6 | Sidebar nav | **Navigation** | Use the sidebar to manage Resources, view Executions, configure Models, and browse Tools. |

Each step has:
- A highlighted target element (spotlight effect)
- A tooltip with title, description, and step counter (e.g., "2 of 6")
- "Next" / "Back" / "Skip tour" buttons
- Clicking outside the tooltip advances to the next step

**Element loading:** The tour waits for each target element to be present in the DOM before showing the step, with a 5-second timeout. If the target element doesn't appear within the timeout (e.g., React Flow canvas still initializing), the step is skipped with a console warning and the tour advances to the next step.

### 5.3 "Load Example" Enhancement

The existing "Load example crew" button on the empty canvas should be more prominent during onboarding. After the tour completes, if the canvas is still empty, show a pulsing highlight on the "Load example crew" button with a tooltip: "Try loading an example to see how crews work."

### 5.4 Sidebar "Help" Link

Add a small "?" icon or "Help" link at the bottom of the sidebar (above the version number) that:
- Opens a dropdown with:
  - "Restart tour" → Re-triggers the guided tour
  - "Documentation" → Opens docs/getting-started.md (or external docs URL)
  - "Keyboard shortcuts" → Shows a shortcuts cheat sheet dialog (also triggered by pressing `?`)

**Documentation hosting:** For MVP, the documentation link points to the GitHub repository's `docs/` directory. Post-MVP, documentation will be hosted on a dedicated site (GitHub Pages or similar) at `docs.blackbeard.sh`.

## 6. State Management

```typescript
// localStorage keys
const ONBOARDING_KEY = 'blackbeard_onboarding_completed'  // 'true' | null
const TOUR_KEY = 'blackbeard_tour_completed'               // 'true' | null
```

- **Welcome dialog**: Shown when `ONBOARDING_KEY` is not set
- **Guided tour**: Shown when user clicks "Get Started" or "Restart tour"
- **Completion**: Both keys set to `'true'` when respective flows complete
- **Reset**: "Restart tour" clears `TOUR_KEY` and re-triggers

## 7. Implementation Notes

### No external tour library
Build the tour with simple React components:
- A `TourOverlay` component that renders a semi-transparent backdrop with a "spotlight" cutout around the target element
- A `TourTooltip` component positioned relative to the target
- Use `getBoundingClientRect()` to position the spotlight and tooltip
- Store the current step in React state

### Responsive behavior
- On viewports < 768px, show a simplified welcome dialog without the tour (Studio isn't usable on mobile anyway)
- The tour only runs on desktop viewports

## 8. Acceptance Criteria

1. First-time visitor sees the Welcome Dialog before any other content
2. Clicking "Get Started" navigates to Studio and starts the 6-step tour
3. Clicking "Skip" dismisses the dialog and never shows it again
4. Each tour step highlights the correct UI element with a spotlight effect
5. Tour can be navigated forward, backward, and skipped at any step
6. Completing or skipping the tour sets localStorage flags
7. "Restart tour" in the sidebar Help menu re-triggers the tour
8. The welcome dialog and tour work correctly on page refresh (respects localStorage)
9. No backend API calls are made during onboarding
10. The tour does not break if the target element is not visible (graceful fallback)

## 9. Future Enhancements (Post-MVP)

- **Interactive tutorial**: Instead of just highlighting, guide the user to actually drag an agent, create a task, connect them, and run
- **Contextual tooltips**: Show tooltips on first interaction with specific features (e.g., first time opening PropertyPanel)
- **"What's new" dialog**: Show on version bumps with changelog highlights
- **Video walkthrough**: Embedded video in the welcome dialog
- **Checklist widget**: A persistent "Getting Started" checklist in the sidebar tracking: ✓ Created first agent, ✓ Built first crew, ✓ Ran first execution
