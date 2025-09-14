# TuneLinkr — Smart Music Redirector

TuneLinkr is a proof‑of‑concept service that automatically converts links to
Spotify, Apple Music, YouTube and other music platforms into links for your
preferred streaming service. It consists of a small FastAPI backend that
performs the link resolution, a simple settings page for choosing a default
service, and a browser extension that rewrites music links on any web page. The
goal is that when a friend sends you a Spotify link, it opens seamlessly in
Apple Music (or vice versa) without any extra work from either of you.

## Contents

- `backend/` – FastAPI application implementing the `/redirect` and
  `/set_preference` endpoints.
- `frontend/` – a simple HTML page where users can select their preferred
  service. Preferences are stored in `localStorage` and via a cookie.
- `extension/` – a cross‑browser web extension (manifest v3) that rewrites
  outgoing music links to go through the redirector. It includes a popup and
  options page for enabling/disabling the extension and selecting a preferred
  service.

## How it works

1. **Intercepting clicks** – The browser extension runs a content script on
   every page. It scans all `<a>` elements and, if the link points to
   `open.spotify.com`, `music.apple.com`, `music.youtube.com`, `youtube.com`
   or `youtu.be`, rewrites the `href` to a call to your redirector backend.

2. **Metadata extraction** – When the backend receives a request to
   `/redirect?url=…` it detects the source platform and extracts the track ID
   from the URL. For Spotify this is the string after `/track/` in the URL
   path. For Apple Music links, the track ID is read from the `i` query
   parameter if present. YouTube IDs are read from the `v` query parameter or
   from the path for `youtu.be` URLs.

3. **Resolving equivalents** – The backend uses the Spotify Web API and
   iTunes Search API to look up the track title and artist. The Spotify
   search endpoint accepts a `q` query and `type=track` and requires an
   OAuth token【61946773673493†L310-L343】, while the iTunes search endpoint is a simple
   GET request to `https://itunes.apple.com/search` with `term`, `entity=song`
   and `limit` parameters【625612402423661†L24-L68】. If a YouTube API key is provided,
   the YouTube Data API’s `search.list` method can be used with a `q` query
   and `type=video`【943975864609281†L385-L406】.

4. **Redirecting** – Once equivalent track IDs are found, the backend returns a
   `302` response pointing at the appropriate track on the user’s preferred
   service. If no match is found, it serves a fallback HTML page listing all
   known links so the user can choose manually.

## Getting started

### Backend

1. Navigate into the `backend/` directory and install dependencies:

   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. Set your environment variables. At minimum you should provide
   `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET` for the Spotify Web API.
   You can optionally set `YOUTUBE_API_KEY` to enable YouTube lookups. For
   example:

   ```bash
   export SPOTIFY_CLIENT_ID=your_client_id
   export SPOTIFY_CLIENT_SECRET=your_client_secret
   export YOUTUBE_API_KEY=your_youtube_api_key  # optional
   ```

3. Run the development server:

   ```bash
   uvicorn main:app --reload --port 8000
   ```

   The backend exposes two endpoints:

   - `GET /redirect?url=…&pref=…` – resolves a music link and returns a 302
     redirect to the equivalent on the preferred service, or a fallback
     HTML page when no match is found.
   - `GET /set_preference?pref=…` – sets the `music_pref` cookie so that
     subsequent `/redirect` requests honour the user’s preference.

### Frontend settings page

Serve the `frontend/settings.html` file from any static host (for example
`http-server` or your favourite static site service). When a user selects
their preferred service the page stores it in `localStorage` and calls
`/set_preference` to persist it on the server.

### Browser extension (Chrome/Edge/Firefox)

1. Open your browser’s extension management page and enable *Developer mode*
   (in Chrome navigate to `chrome://extensions`).
2. Click *Load unpacked* and select the `extension/` directory.
3. Click the TuneLinkr icon in the toolbar, enable the extension and choose
   your preferred service from the options page. You can also toggle the
   extension on and off.

The content script will start rewriting music links on every page. When you
click a Spotify, Apple Music or YouTube link it will be routed through
`/redirect` and opened on your preferred platform. If you haven’t yet set a
preference, the link simply opens as normal.

### Safari (iOS 15+ and macOS)

Safari uses the same WebExtensions API as Chrome but requires packaging the
extension into an Xcode project. Apple provides a command‑line converter that
takes your existing extension and generates the necessary wrapper. As noted
by Evil Martians, you can run the following command in Terminal to convert
the extension:

```bash
xcrun safari-web-extension-converter /path/to/tunelinkr/extension
```

The converter reads your `manifest.json` and outputs an Xcode project. You
can then open the project in Xcode, select the iOS or macOS target and build
the app. This step is described in Apple’s documentation on converting web
extensions and in blog posts such as Evil Martians’ “How to quickly convert
Chrome extensions to Safari”. When run the converter displays options for
naming the generated app and warns about unsupported manifest keys【964890059113133†L254-L264】. After
building the project, install the resulting app on your iPhone via Xcode,
enable the extension under *Settings → Safari → Extensions* and toggle it on.

### Example links

For local testing you can use the following links. Replace `localhost:8000`
with your deployment hostname when deploying:

* Spotify → Apple Music (pref=apple):
  ``http://localhost:8000/redirect?url=https://open.spotify.com/track/7ouMYWpwJ422jRcDASZB7P&pref=apple``
* Apple Music → Spotify (pref=spotify):
  ``http://localhost:8000/redirect?url=https://music.apple.com/us/album/shape-of-you/1193701079?i=1193701356&pref=spotify``

If no match is found on the target platform you will see a fallback page
listing the known links for that track and an option to choose manually.

### Deploying

The FastAPI backend can be deployed to any platform that supports Python.
Services such as Vercel, Render or Fly.io can run an ASGI application
directly. When deploying you should set the environment variables for your
Spotify and optional YouTube credentials. The browser extension should be
configured to point at your deployment base URL instead of `http://localhost:8000`.
You can either hard‑code the deployment URL in `extension/content.js` or
expose it via `chrome.storage` so users can change it in the options page.

### iOS Shortcut (optional)

For users who prefer not to install a Safari extension, you can create a
Shortcut that rewrites any tapped music link to go through the redirector.
The Shortcut uses the *Get Details of URLs* action to capture the link,
constructs `https://your-backend/redirect?url=` plus the encoded original
link, and opens it in Safari. After creating the Shortcut you can add it
to the share sheet for URLs.

## Notes & limitations

- The Spotify and YouTube APIs impose rate limits and require valid API keys
  or tokens. For personal use the free tiers should be sufficient, but
  heavy usage may require caching results or a commercial licence.
- Some tracks may not be available on all services. The fallback page
  allows users to choose an available platform when automatic resolution
  fails.
- Safari’s WebExtensions runtime has limitations: certain Chrome APIs like
  `browser.identity` or `browser.webRequest` are unsupported【964890059113133†L317-L334】. Our
  extension only uses `storage` and `scripting`, which are supported on Safari.

Enjoy sharing music links without worrying about which app your friends use!