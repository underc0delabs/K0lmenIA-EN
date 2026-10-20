# Apps under test

Put the `.apk` (Android) or `.ipa`/`.app` (iOS) of the app under test here and set its name in `MOBILE_APP` in the k0lmenIA root `.env`.

The binaries **are not versioned** (they are in `.gitignore`): each person copies their own app.

For BrowserStack you don't need the local file: upload the app to BrowserStack and put the `bs://...` it returns in `BROWSERSTACK_APP`.
