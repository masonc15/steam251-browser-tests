# Steam251 browser tests

Version 0.1.1. Public tests of https://steam251.com. This repository contains no application source or credentials.

## Browser checks

Run `npm ci`, `npx playwright install chromium`, then `npm test` on Linux (for example Nuada). The tests cover four public routes at desktop and mobile sizes, network font independence, text measurements during initial loading, horizontal overflow, ranking navigation, early-access filtering, and the comparison frame.

Mobile Chromium is not iPhone Safari. Frame callbacks are observations, not proof that every intermediate frame was displayed. Use the simulator recording to inspect the visible loading sequence.

## iPhone Safari

The manually started `iPhone Safari evidence` workflow uses a standard GitHub macOS runner. It starts an available iPhone simulator with `simctl`, operates Safari with `idb` HID/accessibility, and records route loads. No Appium, xcautomation, or XCTest is used. No local Mac or physical phone is contacted.

A successful workflow means evidence collection completed; it is not an automatic visual pass. Read the result JSON and inspect the images/video. The workflow records a failure if Safari does not expose the expected page content. Screenshots and video are retained for one day. There is no schedule. GitHub standard runner time is free for public repositories; storage is still subject to account allowances.

The real-device check uses the provider's free TestMu sessions and requires an authenticated provider account. It is separate from the simulator run.
