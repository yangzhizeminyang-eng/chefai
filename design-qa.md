# Login Visual QA

## Scope and Evidence

- Source visual: `C:/Temp/codex-clipboard-1be2c3ae-1e81-4cab-97c1-c9eeb239c0fb.png` (user-selected login direction, 1024 × 1024 px).
- Implementation: `web-stage1/src/views/LoginView.vue`, `web-stage1/index.html`.
- Preview: `http://127.0.0.1:5193/login`.
- Desktop comparison capture: `C:/Temp/chefai-login-match-1024.png` (1024 × 1024 px, CSS viewport 1024 × 1024, device scale factor 1).
- Mobile login capture: `C:/Temp/chefai-login-mobile-final.png` (390 × 1172 px full-page capture, CSS viewport 390 × 844, device scale factor 1).
- Mobile registration capture: `C:/Temp/chefai-register-mobile-final.png` (390 px wide full-page capture, CSS viewport 390 × 844, device scale factor 1).
- State: unauthenticated; login and registration tabs tested without submitting credentials.
- Full-view comparison: the 1024 × 1024 source and implementation were viewed together. The warm full-page surface, left form, right food-preparation scene, brand mark, and lower-right slogan retain the intended composition. The image's left-edge fade and outlined inputs are intentional updates requested after the source visual.
- Focused comparison: checked image crop/fade, form alignment and field treatment, and slogan legibility at desktop and mobile widths. No separate crop was needed.

## Results

- Typography: Chinese serif display text and existing sans-serif UI text keep a clear hierarchy; labels and helper text fit without clipping.
- Spacing and layout: no outer card, border, or shadow remains around the form/scene. At 1024 px the two-column composition fits; at 390 px the scene stacks above the form and the document has no horizontal overflow.
- Colors and tokens: the page uses the requested `#f5f0e8` countertop with dark green actions and readable local text tokens. Input fields retain a fine neutral outline.
- Imagery: the preparation image loads successfully. Desktop fades in from the left; on mobile the fade is vertical and applies to the image only, not the caption.
- Copy and behavior: the login/register labels, required-field validation, and existing authentication submit handlers remain intact. Login and registration tabs both render; empty login submission shows both required-field errors and remains on `/login`.
- Accessibility: axe-core reported 0 violations on login and registration states (42 passes). Its single incomplete contrast check is the slogan over a variable photograph; manual desktop and mobile review confirmed the dark text remains readable. The HTML declares `lang="zh-CN"`, and the auth route has one top-level main landmark.
- Console: no browser page errors; only normal Vite connection debug messages.
- Impeccable detector: no code anti-patterns reported for `LoginView.vue`. URL scanning was unavailable because its bundled scanner could not locate a local Chrome installation; browser rendering was independently verified with agent-browser.
- Automated checks: `npm test` passed (22 files, 250 tests); `npm run build` passed including `vue-tsc --build`. Vite emitted the existing warning that the main JS chunk exceeds 500 kB.

## Iteration History

1. Initial responsive screenshot showed the mobile visual container's vertical mask also faded the slogan. The mask was moved onto the image only; the regenerated mobile capture shows the slogan at full opacity and readable.
2. The detector flagged an unnecessary width transition on the tab indicator. The width animation was removed; the final detector run reported no code findings.
3. Initial accessibility scan found weak muted copy contrast and nested main landmarks. Page-local contrast tokens were darkened, the inner main wrapper became a neutral container, and `lang="zh-CN"` was added. Final axe runs report zero violations.

## Remaining Notes

- The final art direction intentionally differs from the selected source by blending the photo into the countertop, removing the card treatment, and using bordered input fields, per the user's latest direction.
- The detector's URL mode could not run without a locally installed Chrome binary; actual rendered checks were completed through the available browser automation runtime.

## Motion Pass (2026-10-18)

- Scope: login/register view plus authenticated-route content transition only; other pages and loading states remain unchanged in this step.
- Preview: `http://127.0.0.1:5194/login` (5193 was already occupied and was left running).
- Desktop interaction evidence: `C:/Temp/chefai-login-motion-desktop.png`, 1440 × 960 CSS px, device scale factor 1. The screenshot shows the registration state after switching tabs; the title remains present without replaying its entrance.
- Desktop checks: title animation duration computed to `0.4s`; pointer movement produced image translation of approximately +5.72px and -5.70px on X, within the ±6px bound. Pointer leave resets the offset. CSS mask fade is 200px.
- Mobile check: 390 × 844 CSS px; no horizontal overflow. Pointer parallax is disabled by the width/coarse-pointer guards. Reduced-motion emulation confirmed title animation `none` and image transform `none`.
- Authenticated-route transition: `.route-content` Transition is nested only inside the non-authenticated app-shell branch; `/login` is rendered by the separate auth branch and does not receive route transition classes. This code-path boundary was verified; authenticated navigation was not exercised in the browser because no test account was available.
- Login/register interaction: registration tab displays all four fields and remains on `/login`; the entrance animation does not replay on tab switch.
- Browser accessibility: 0 axe violations (42 passes); the photo-caption contrast check remains an incomplete manual check as previously noted. No browser page errors.
- Validation after the motion changes: `npm run type-check`, `npm test` (22 files, 250 tests), and `npm run build` passed. The existing >500KB main-chunk advisory remains.
- Motion detector: Impeccable code scan reported no anti-patterns; its URL mode remains unavailable on this host because it cannot locate a local Chrome installation.

final result: passed

## Full-Bleed Login Layout Pass (2026-10-18)

- Scope: desktop login composition and registration helper spacing. Authentication behavior, motion behavior, and the existing mobile stacked layout were preserved.
- Preview: `http://127.0.0.1:5195/login`.
- Captures: `C:/Temp/chefai-login-refined-desktop.png` (1262 × 568), `C:/Temp/chefai-register-refined-desktop.png` (1440 × 960), and `C:/Temp/chefai-register-refined-mobile.png` (390 px wide).
- Desktop login: visual spans y=0 to viewport bottom and its right edge equals viewport right edge; its 100dvh height is maintained. The form panel center is y=284 at a 568 px viewport and y=480 at a 960 px viewport. No document overflow was present at either desktop size.
- Desktop registration: registration tab renders all four fields. The inherited-data hint uses a 16 px top gap and 1.7 line-height; privacy copy follows with 20 px separation. Form panel center aligns to viewport center and the full registration content fits within the 960 px viewport.
- Mobile: 390 × 844 CSS px retains the topbar, stacked image, then form layout. The page scrolls vertically to fit its content (924 px total) and has no horizontal overflow. The image remains a bounded 343 px-high region rather than filling the viewport.
- Reduced motion: emulated `prefers-reduced-motion`; title animation is `none`, image transform is `none`, and image transition is `0s`.
- Browser checks: registration and login states render; axe reports 0 violations (42 passes). One existing incomplete contrast check remains for the photo caption because its background is variable imagery. No browser page errors.
- Mechanical scan: Impeccable detector reported no findings for `src/views/LoginView.vue`.
- Automated checks: `npm run type-check`, `npm test` (22 files, 250 tests), and `npm run build` passed. The existing >500KB main-chunk advisory remains.

## Disclaimer Gate Visual Continuity Pass (2026-10-18)

- Scope: first-login full-screen disclaimer gate styling only. Disclaimer copy, required checkbox, consent API call, and local fallback behavior were preserved.
- Preview: `http://127.0.0.1:5196/` with an isolated synthetic login state; no real account storage was changed.
- Captures: `C:/Temp/chefai-disclaimer-desktop.png` (1262 × 568) and `C:/Temp/chefai-disclaimer-mobile.png` (390 × 844).
- Visuals: fullscreen surface uses the login page's `#f5f0e8` countertop and `#24483a` action color; heading uses the same dark green ink; clause panel is warm cream with a low-contrast warm shadow; existing prep-scene asset appears as a subdued top-right detail. Checkbox has a custom green checked state and visible focus styling; disabled/active button states remain distinct with a 10 px radius and restrained hover lift.
- Responsive: desktop and mobile dialogs fill their viewport without horizontal overflow; clause text wraps naturally at 390 px.
- Flow: button is disabled before agreement. In an isolated browser session, checking the box enabled it; clicking entered the existing consent action, stored `disclaimer_agreed_v1=1`, and released the modal body lock.
- Accessibility/browser: the gate has no axe findings; page-level axe results include existing findings from the underlying home content (home text contrast and landmark structure). No page errors were reported. The gate heading is supplied to Element Plus as its dialog title.
- Mechanical scan: Impeccable detector reported no findings for `src/components/DisclaimerGate.vue`.
- Automated checks: `npm run type-check`, `npm test`, and `npm run build` passed; existing main-chunk size advisory remains.

## Refresh First-Paint Routing Pass (2026-10-18)

- Root cause evidence: 60 fps recording of a hard refresh on the first-login gate showed the authenticated home shell and home content becoming visible beneath the Element Plus dialog's default fade/translate entrance. Login route rendering also depended on `route.name` before Vue Router completed its initial navigation.
- Fix: app mount now awaits `router.isReady()`, so initial route resolution and auth-guard redirects complete before any shell is rendered. The mandatory disclaimer gate uses an immediate transition, so it cannot reveal the underlying app during entry. A minimal warm background is declared in `index.html` to cover pre-CSS paint.
- Repro/fix captures: `C:/Temp/chefai-refresh-before.contact-sheet.png`, `C:/Temp/chefai-refresh-after.contact-sheet.png`, `C:/Temp/chefai-login-refresh-after.contact-sheet.png`.
- Browser checks: on authenticated-but-unconsented state, hard refresh remains at `/`, showing only the disclaimer after app startup; the home shell is no longer visible through a fading overlay. Hard refresh on `/login` shows the auth layout, not the app shell. Direct unauthenticated `/inventory` navigation resolves to `/login?redirect=/inventory` before app content appears. The auth shell remains separate and has no route transition.
- Test: `src/utils/__tests__/routerBoot.spec.ts` verifies the app mount callback stays pending until the initial router readiness promise resolves. The test was observed failing before implementation and passing afterward.
- Browser console: only normal Vite connection diagnostics; no application errors.
- Active project server: repeated the authenticated/unconsented hard-refresh check against `http://localhost:5173/` (the existing Vite process listens on IPv6 localhost). The page remains on the full-screen disclaimer with no visible home shell beneath it; screenshot: `C:/Temp/chefai-live-refresh-5173.png`.

## Route Content Recovery Pass (2026-10-18)

- Reproduction: in an isolated browser session, navigate to `/select`, then `/inventory`. Before the fix, Vue warned that `SelectIngredientView` had a non-element fragment root inside `<Transition>`; after navigation, the URL changed to `/inventory` while `.app-main` had zero children and only an empty comment node. A hard refresh rendered the page again.
- Root cause: `SelectIngredientView` renders the page and fixed action bar as a fragment. The app's `out-in` route transition was attached directly to route components, so fragment-root pages could not participate in the transition lifecycle reliably.
- Fix: `RouteContentView.vue` places every authenticated route component inside a single animatable element before applying the existing 200 ms transition. Auth routes remain outside this wrapper; reduced-motion behavior is unchanged.
- Regression test: `src/components/__tests__/RouteContentView.spec.ts` server-renders a fragment-root route and verifies both roots stay inside the transition wrapper.
- Browser verification on the existing `http://localhost:5173`: `/select` → `/inventory` → `/profile` → `/me` → `/trace`; each target rendered non-empty content and exactly one wrapper under `.app-main`. Hard refresh on `/trace` retained the route content. No Vue Transition root warnings or page errors were reported.

## Login Microinteraction Pass (2026-10-18)

- Scope: desktop food-photo hover details, login button hover copy, and the visual caption entrance. Existing login/register behavior and the selected warm kitchen composition are unchanged.
- Desktop capture: `C:/Temp/chefai-login-micro-desktop.png` (1440 × 960); local ingredient image detail capture: `C:/Temp/chefai-login-micro-scallion.png`.
- Mobile capture: `C:/Temp/chefai-login-micro-mobile.png` (390 × 844); no horizontal overflow, and decorative hover zones are hidden.
- Interaction: transparent desktop-only hover zones activate clipped copies aligned over salt, scallion, and chili regions; each sway is capped at 3 px and lasts 220 ms. The login label crossfades to “开饭咯” over 1 s while its accessible name remains “登录并继续”. The two-line caption reveals in 500 ms total and remains visible if the animation script does not start.
- Reduced motion: emulation confirmed the title entrance and parallax are off, the caption is immediately visible, local photo-motion overlays are hidden, and the copy transition is reduced to an effectively instant state change.
- Browser/a11y: login and registration states render; desktop and mobile layouts fit; axe reports 0 violations (32 passes). The photo caption remains an incomplete contrast check because its background is variable imagery. No page errors were reported.
- Impeccable detector: no findings for `web-stage1/src/views/LoginView.vue`.
- Automated checks: `npm test` passed (24 files, 252 tests); `npm run build` passed including type-check. The existing main JS chunk >500 kB warning remains.
