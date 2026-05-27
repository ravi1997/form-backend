# Skill: Agent Browser Auditing

Use Vercel's `agent-browser` (Rust CLI + Playwright Persisted Daemon) to perform visual, UX, flow, and integration auditing of the RIDP web platform.

## 🚀 Why agent-browser?
Unlike traditional DOM scrapers or Playwright tools that dump massive HTML files into the context (exploding token usage), `agent-browser` focuses on:
1. **Interactive Snapshot + Accessibility Refs**: Exposes clean, token-efficient trees mapping tags to actions (e.g. `@e1`, `@e2`).
2. **Speed & Session Persistence**: Leverages a background browser daemon that stays active between sequential steps to eliminate setup/startup overhead.
3. **Safety & Determinism**: Focuses directly on layout and accessibility elements to prevent fragile CSS/Xpath selector breakage.

## 🛠️ Global Execution Setup
Verify that `agent-browser` CLI and Chrome are configured on the system:
```bash
npx agent-browser --help
```

If Chromium shared library errors occur on Linux hosts, run:
```bash
npx agent-browser install --with-deps
```

## 📋 Standard Auditing Tasks

### 1. View & Interact with the Frontend
Launch the interactive browser session targeting the local server (typically `http://localhost:8051` or `http://localhost:3000` depending on dev runs):
```bash
npx agent-browser navigate "http://localhost:8051"
```

Perform basic interactions like clicks or inputs based on the target accessibility references:
```bash
# Click a target element reference
npx agent-browser click "@e12"

# Input text into a target form element
npx agent-browser type "@e5" "Admin Credentials"
```

### 2. Capture Screens for Aesthetic Evaluation
To perform pixel-perfect visual evaluations (colors, glassmorphism card designs, margins, layout shifts):
```bash
npx agent-browser screenshot "/home/ravi/workspace/docker/apps/form-backend/logs/audit-viewport.png"
```

---

## 🎭 Personas for Auditing

When executing an audit, always look at changes through two perspectives:

### 🌟 1. Gen Z / Zen Gen Product Designer (UX/Aesthetic Critic)
*   **Accents & Harmony**: Look for cohesive, tailored colors (like our Indigo `#6366F1` accents) rather than plain browser defaults.
*   **Transitions**: Evaluate visual micro-animations (e.g. adding rule rows in filter builders, loading node results, chips closing).
*   **Layout & Glassmorphic Designs**: Inspect card overlays, margins, grid structures, and responsive padding.

### 🛡️ 2. Veteran Systems Architect (20+ Years QA Specialist)
*   **Exception Boundaries**: Verify system tolerance under weird inputs (e.g. division by zero in Analysis nodes, escaping inputs inside query filter dialog inputs).
*   **State & Reactivity**: Ensure Riverpod providers trigger accurate background queries, network transactions execute debounced autosaves safely, and browser refreshes preserve states.
*   **Access Barriers**: Check that unauthenticated routes are appropriately blocked, and that session-level cookies carry `X-CSRF-TOKEN-ACCESS` configurations.
