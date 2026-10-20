---
name: game-testing
description: How to test video games — types and engines (Unity, Unreal, Godot, web/HTML5, mobile, console, PC), functional (mechanics and rules, progression and saving, quests, game states, physics and collisions, camera, keyboard/mouse/gamepad/touch controls), compatibility (resolutions and aspect ratios, FPS/refresh, platforms and devices, controllers), performance (stable FPS, load times, memory/leaks, stuttering, GPU/CPU usage, battery on mobile), saving and persistence (save/load, corruption, cloud saves, migration between versions), multiplayer and networking (synchronization, latency/lag, disconnect and reconnect, matchmaking, server authority and anti-cheat, rollback), economy and monetization (in-app purchases, in-game currency, loot boxes, balance, ads), audio and localization, UI/UX and accessibility (key remapping, subtitles, color blindness), stability/soak and crash testing, build verification/smoke per platform, and game-specific techniques (exploratory, world boundaries, sequence breaks, speedrun/soft-lock); how to automate (engine frameworks, bots, Playwright for HTML5, Appium for mobile) and questions for the studio. Used by the game-tester.
---

# Video game testing

A game has much of what any software has (functional, performance, compatibility), plus its own things: **physics, game states, progression, multiplayer and "breaking" the world** in creative ways. Exploratory testing weighs a lot. For the AI part (LLM-driven NPCs) see `ai-testing`; for the online backend, the API skills and `async-testing`.

## 1. Context

- **Engine and platform**: Unity, Unreal, Godot, HTML5/web, mobile (iOS/Android), console, PC. It defines how you automate and what to look at.
- **Genre**: mechanics and edge cases change a lot (an RPG vs. a shooter vs. a puzzle game).

## 2. Functional (mechanics and rules)

- **Mechanics**: every game rule works (damage, score, cooldowns, inventory, crafting); edge cases (zero health, full inventory, max level).
- **Progression and quests**: quests complete and unlock what they should; no **soft-locks** (getting stuck with no way to progress) or sequence breaks (doing things in a different order).
- **Game states**: menu → playing → pause → game over → restart; clean transitions.
- **Physics and collisions**: the player doesn't go through walls or fall out of the world; correct collisions; map **boundaries**.
- **Controls**: keyboard+mouse, gamepad and touch; they respond well and can be remapped.

## 3. Saving and persistence

- **Save/Load**: saving and loading restores the exact state; autosave; a **corrupted** save doesn't crash the game (the error is handled).
- **Cloud saves** and sync across devices; save **migration** between game versions.

## 4. Compatibility and performance

- **Resolutions and aspect ratios** (including ultrawide), FPS/refresh; UI that doesn't get cut off or overlap.
- **Performance**: **stable FPS** in heavy scenes, **load times**, **memory/leaks** (long sessions), **stuttering**, GPU/CPU usage, **battery/heat** on mobile. For backend load, `performance-mapper`.
- **Platforms/devices** and **controllers** in the target matrix.

## 5. Multiplayer and networking

- **Synchronization** between players (everyone sees the same thing), **latency/lag** and its compensation (rollback/prediction), **disconnect and reconnect** without breaking the match, **matchmaking**.
- **Server authority and anti-cheat**: the client doesn't decide critical things (health, items, position) without server validation; cheating attempts are rejected.

## 6. Economy and monetization

- **In-app purchases** (store sandbox), **in-game currency**, **loot boxes** (declared odds), **balance** (not broken or unintentionally pay-to-win), rewarded **ads**.
- A purchase grants what was paid for exactly once and can be restored ("restore purchases").

## 7. Audio, localization and accessibility

- **Audio**: music, effects and voices play and mix well; no dropouts.
- **Localization**: translated texts, no overflows or visible keys (see `translation-analyst`).
- **Accessibility**: key remapping, subtitles, color-blind modes, UI scaling.

## 8. Stability and build verification

- **Smoke/BVT per platform**: the build starts, enters a match, saves and exits without crashing.
- **Soak**: leave the game running for hours (memory leaks, degradation).
- **Crash**: report with steps, logs and, if available, the crash dump.

## 9. Game-specific techniques

- **Exploratory** (the most valuable): try to **break the world** —go through geometry, leave the map, perform actions in an odd order, interrupt cutscenes, spam inputs—; **speedrun** to detect sequence breaks; impossible states.

## 10. Automating

- Engine frameworks (**Unity Test Framework**, **Unreal Automation**, **GAutomator**), **bots** that play, **Playwright** for **HTML5** games, **Appium** for mobile. Much of game testing is **manual exploratory**; automate the repetitive parts (smoke, mechanics regression, network load).

## 11. Typical game bugs

- **Soft-lock**: the player gets stuck with no way to progress or go back.
- Going through walls / falling out of the world; broken collisions.
- A corrupted save that crashes, or progress lost after an update.
- FPS that plummets in one scene; a memory leak in long sessions.
- Desync in multiplayer; the client decides something critical (cheat).
- An in-app purchase that doesn't grant the item or grants it twice.
- UI cut off at a certain aspect ratio; text overflowing in another language.
- A sequence break when doing quests in a different order.

## 12. Typical questions for the studio

When it isn't written down, they are `MI-XX`:

- Which engine and which target platforms/devices?
- Which mechanics and progression are critical? Is there a level/quest design?
- Is it single-player or multiplayer? Server authority and anti-cheat?
- Are there in-app purchases, loot boxes or ads? Declared odds?
- What target FPS/load times? A QA build per platform?
- Local saves, cloud saves, and migration between versions?
