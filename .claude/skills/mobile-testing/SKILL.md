---
name: mobile-testing
description: How to test mobile applications (Android and iOS) — types (native, hybrid, web/PWA), environments and devices (emulator/simulator vs. real, device farms, capability profiles), installation and distribution (APK/AAB, IPA, Play Internal Testing, TestFlight, signing), system permissions (grant, deny, revoke on the fly, runtime permissions), interruptions (call, notification, alarm, low battery, screen lock), connectivity (offline, slow network, wifi↔cellular switch, reconnection and retries), deep links and universal/app links, push notifications (permission, foreground/background/killed, push deep link), app lifecycle (background, return, kill and relaunch, rotation), screen sizes and densities, gestures and the back button, keyboard, storage and data (cache, migrations, clear data), performance (startup, memory, battery, jank/ANR), mobile security (insecure storage, certificate pinning, excessive permissions, OWASP MASVS), accessibility (TalkBack/VoiceOver, font size), OS version compatibility, store readiness, smoke and regression, how to automate with Appium (MCP), typical bugs and questions for the PO. Used by the mobile-tester and the mobile-mapper.
---

# Mobile application testing (Android and iOS)

A mobile app lives on a device with a **lifecycle, permissions, interruptions and variable connectivity** that a website doesn't have. The first thing is to know the **type** (native, hybrid or web/PWA) and the **platforms and OS versions** to support. It complements `design-techniques` and, for automation, `k0lmena-automation` (Appium).

## 1. Environments and devices

- **Emulator/simulator vs. real**: the emulator works for most things; a **real** device is essential for camera, biometrics, push, performance, battery and fine gestures.
- **Device matrix**: cover by **OS version** (an old supported one, a current one), **size/density** (small, large, tablet/foldable) and tier (high-end/low-end). Pairwise if you can't cover everything (`design-techniques`).
- **Device farms** (BrowserStack, Sauce Labs, Firebase Test Lab) to widen the matrix without your own hardware.

## 2. App type

- **Native** (Kotlin/Java, Swift): OS controls; automated by accessibility id / resource-id.
- **Hybrid** (React Native, Flutter, Ionic/Capacitor, Cordova): mixes native + webview; inside the webview it's automated like web.
- **Web/PWA**: tested like mobile web (see `ecommerce-testing`/web), plus installation as a PWA, offline and splash.

## 3. Installation and distribution

- **Android**: APK/**AAB**, signing, `minSdk`/`targetSdk`, installation via Play Internal Testing or `adb install`; update keeping data; uninstall.
- **iOS**: IPA, provisioning profiles, **TestFlight**; no *expired provisioning*.
- First launch (onboarding), update from one version to another (data migration), and an unsupported **downgrade** announced without losing data.

## 4. System permissions

- **Runtime** permissions (camera, location, notifications, files, contacts): **grant, deny, "only this time", and revoke from Settings with the app open**. The app must not crash if denied: it degrades or explains.
- **Excessive** permissions (asks for more than it uses) = a security/privacy finding.

## 5. Interruptions and lifecycle

- **Interruptions**: incoming call, notification, alarm, **low battery**, screen lock, split-screen. When returning, the app resumes its state without losing form data.
- **Lifecycle**: send to **background** and return, **kill** the app and relaunch (restores the expected session/state), **rotation** (doesn't lose data or rebuild the screen badly).
- **Gestures and the back button** (Android): back doesn't abruptly exit the app losing data; on iOS, the swipe back.

## 6. Connectivity

- **Offline**: clear message, action queue and **retry/sync** when the network comes back; nothing entered is lost.
- **Slow/unstable network** and **wifi↔cellular switch** in the middle of an operation (e.g. a purchase): timeouts, idempotent retries, no double submission.
- **Airplane mode** and back.

## 7. Deep links and push

- **Deep links / universal (iOS) / app links (Android)**: open the right screen with the app closed, in the background and open; an invalid link doesn't crash.
- **Push**: request permission (mandatory on iOS), receive in **foreground, background and with the app closed**; tapping the notification goes to the right destination (deep link); respects opt-out.

## 8. Screens, keyboard and data

- **Sizes/densities and large system font**: no cut-off texts or hidden buttons; **notch/safe areas** and edge gestures.
- **Keyboard**: right type (numeric, email), doesn't cover the field or the button, scrolls to focus, "next/done".
- **Data**: cache and "clear data"/"clear cache" leave the app consistent; database migration on update; nothing sensitive in logs.

## 9. Smoke test

Fast and blocking, on a QA device/emulator:

1. Installs and opens without crashing; onboarding/splash ok.
2. Login (if applicable) with a test user.
3. One core action in scope works.
4. Background → return keeps the state; rotating doesn't break anything.
5. No errors/ANR in logcat (Android) or the console (iOS).

## 10. Regression

- After **a new build**: extended smoke + the main flow + whatever the change touches, on at least one Android and one iOS from the matrix. Automated with `mobile-mapper` (Appium) and then `npm test`, with no tokens.
- Check **backward compatibility** of local data (an old database after updating).

## 11. Performance

- **Startup** (cold/warm), **memory** and **battery**, **jank** (dropped frames, scrolling) and **ANR** (Android) / watchdog (iOS); APK/IPA size.
- Network operations on a **slow network** (see §6). For backend load, `performance-guide` + `performance-mapper`.

## 12. Mobile security

Scanning/exploitation is done by `security-analyst`/`web-pentester` (backend) and the OWASP **MASVS** baseline; specific to the mobile client:

- **Insecure storage**: tokens/credentials/PII in plain text (SharedPreferences, plist, unencrypted SQLite, logs); use Keystore/Keychain.
- **Network**: TLS and, if applicable, **certificate pinning**; no `TrustAll`.
- **Minimal permissions**, no unnecessarily exported components/activities (Android), unvalidated deep links.
- Secrets embedded in the APK/IPA (API keys) — a finding (they show up when decompiling).

## 13. Accessibility

- **TalkBack (Android)/VoiceOver (iOS)**: every control with an accessible label; logical focus and order; whatever has no label can't be automated well either.
- **Large system font** and contrast; touch targets of sufficient size.

## 14. Store readiness

- Metadata, screenshots, icon, privacy policy and declared permissions; it doesn't violate Apple/Google guidelines (e.g. mandatory login without "Sign in with Apple" when required).

## 15. Automating with Appium (mobile-mapper)

- Locate by **accessibility id** / resource-id / predicate; avoid brittle XPath and coordinates.
- Use the **appium** connector (enable it with `npm run connector`); capabilities per platform (Android `uiautomator2`, iOS `xcuitest`).
- Wait for the element to exist; handle the system **permission dialogs** at the start of the scenario (autogrant or accept them explicitly).
- Leave a clean state between scenarios (logout, clear data if needed).
- For the **webview** of a hybrid app, switch context NATIVE_APP ↔ WEBVIEW.

## 16. Typical mobile bugs

- Crash when **denying a permission** or revoking it with the app open.
- Form state lost when **rotating** or returning from background.
- Offline without handling: blank screen or lost data; double submission on reconnect.
- A deep link or push that doesn't open the right screen with the app closed.
- Text cut off with a **large font** or on a small screen; a button hidden by the keyboard.
- Token/PII stored in plain text or in logcat.
- ANR/jank in long lists; slow startup.
- Data migration that breaks when updating versions.
- A permission requested that the app doesn't use.

## 17. Typical questions for the PO (mobile)

When it isn't written down, they are `MI-XX`:

- Android, iOS or both? Which minimum OS versions and which priority devices?
- Native, hybrid (RN/Flutter/…) or web/PWA?
- How is it distributed for testing (Play Internal, TestFlight, direct APK)?
- Which permissions does it use and what for? What's the expected behavior if they're denied?
- Are there push notifications and deep links? What should each one open?
- What happens offline in the key flows?
- Does the testing include performance, security (MASVS) and accessibility, or only functional?
