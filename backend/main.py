"""
Smart Music Redirector backend

This FastAPI application exposes a single endpoint (`/redirect`) that accepts a URL
from one music streaming service and attempts to resolve the equivalent track
on the user's preferred platform. It uses the Spotify Web API, the iTunes
Search API and optionally the YouTube Data API to look up metadata and find
matching tracks on other services. If a match is found the request is redirected
to the preferred service with a 302 status code. If no match is found a simple
HTML page is returned with buttons linking to all available platforms.

Environment variables used:

* ``SPOTIFY_CLIENT_ID`` and ``SPOTIFY_CLIENT_SECRET`` – credentials for the
  Spotify API. These are required if you want to resolve or search Spotify
  tracks. See the Spotify developer documentation for instructions on how to
  obtain these credentials. The Spotify search endpoint requires an OAuth
  token, which we obtain via the client‑credentials flow.
* ``YOUTUBE_API_KEY`` – API key for the YouTube Data API (optional). If
  provided the service will attempt to search for a track on YouTube.

The iTunes Search API does not require authentication. According to Apple's
documentation, the search endpoint is simply a GET request to
``https://itunes.apple.com/search?parameterkeyvalue``, where parameters like
``term``, ``country`` and ``entity`` control what is returned【625612402423661†L24-L68】. The
``term`` parameter holds the URL‑encoded search string, while ``entity`` can
be set to ``song`` to return song results【625612402423661†L64-L86】. Apple states that
the search API returns JSON and notes that you should limit the number of
results for faster responses【625612402423661†L134-L142】.

The Spotify search endpoint is documented as ``GET /search``. It requires
OAuth 2.0 authentication and accepts a ``q`` query parameter containing the
search text and a ``type`` parameter specifying which resources to search
(e.g. ``track``). Spotify warns that the call requires an access token and
allows filters such as ``artist``, ``album`` and ``year``【61946773673493†L310-L343】.

The YouTube Data API's ``search.list`` method can be used to find videos.
The ``q`` parameter holds the search term and you can limit results to
videos by setting ``type=video``. Google notes that the ``q`` parameter
supports Boolean operators and that results can be filtered by region and
language【943975864609281†L385-L406】. Use of the YouTube API is optional and
controlled via the ``YOUTUBE_API_KEY`` environment variable.

To run the development server locally:

    uvicorn main:app --reload --port 8000
"""

from __future__ import annotations

import os
import re
import json
from typing import Optional, Tuple, Dict, Any, List 
from urllib.parse import urlparse, unquote, parse_qs, quote_plus
from dotenv import load_dotenv

load_dotenv()

import requests
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import RedirectResponse, HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Smart Music Redirector")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for frontend
if os.path.exists("frontend"):
    app.mount("/static", StaticFiles(directory="frontend"), name="static")

# Health check endpoint for Railway
@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "smartmusicredirector"}

# Serve frontend files
@app.get("/")
async def serve_frontend():
    if os.path.exists("frontend/index.html"):
        return FileResponse("frontend/index.html")
    elif os.path.exists("test_links.html"):
        return FileResponse("test_links.html")
    else:
        return {"message": "Smart Music Redirector API is running", "docs": "/docs"}

class SpotifyAPI:
    """Helper class to interact with the Spotify Web API."""

    TOKEN_URL = "https://accounts.spotify.com/api/token"
    SEARCH_URL = "https://api.spotify.com/v1/search"
    TRACK_URL = "https://api.spotify.com/v1/tracks/{id}"

    def __init__(self, client_id: Optional[str], client_secret: Optional[str]) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self._token: Optional[str] = None

    def _get_access_token(self) -> Optional[str]:
        if self._token:
            return self._token
        if not (self.client_id and self.client_secret):
            return None
        try:
            auth_response = requests.post(
                self.TOKEN_URL,
                data={"grant_type": "client_credentials"},
                auth=(self.client_id, self.client_secret),
                timeout=10,
            )
            auth_response.raise_for_status()
            token = auth_response.json().get("access_token")
            self._token = token
            return token
        except Exception:
            return None

    def get_track(self, track_id: str) -> Optional[Dict[str, Any]]:
        token = self._get_access_token()
        if not token:
            return None
        headers = {"Authorization": f"Bearer {token}"}
        try:
            resp = requests.get(self.TRACK_URL.format(id=track_id), headers=headers, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return None

    def search_track(self, title: str, artist: str, market: Optional[str] = None) -> List[Dict[str, str]]:
        token = self._get_access_token()
        if not token:
            return []
        headers = {"Authorization": f"Bearer {token}"}

        def do_search(params: Dict[str, Any]) -> List[Dict[str, str]]:
            try:
                resp = requests.get(self.SEARCH_URL, headers=headers, params=params, timeout=10)
                try:
                    print(f"[spotify.request_url] {resp.url}")
                except Exception:
                    pass
                resp.raise_for_status()
                data = resp.json()
                tracks = data.get("tracks", {}).get("items", [])
                return [
                    {
                        "title": t.get("name", ""),
                        "artist": (t.get("artists") or [{}])[0].get("name", ""),
                        "url": (t.get("external_urls") or {}).get("spotify", ""),
                        "duration_ms": t.get("duration_ms"),
                        "album": (t.get("album") or {}).get("name", ""),
                        "track_number": t.get("track_number")
                    }
                    for t in tracks
                ]
            except Exception:
                return []

        # Strict, fielded query first
        query_parts = []
        if title:
            query_parts.append(f'track:"{title}"')
        if artist:
            query_parts.append(f'artist:"{artist}"')
        query = ' '.join(query_parts)
        params: Dict[str, Any] = {"q": query, "type": "track", "limit": 5}
        if market:
            params["market"] = market
        print(f"[spotify.query] strict params={params}")
        results = do_search(params)
        if results:
            return results

        # Fallback 1: unfielded query with title and artist
        loose_q = " ".join([p for p in [title, artist] if p])
        if loose_q:
            params2: Dict[str, Any] = {"q": loose_q, "type": "track", "limit": 5}
            if market:
                params2["market"] = market
            print(f"[spotify.query] loose params={params2}")
            results = do_search(params2)
            if results:
                return results

        # Fallback 2: title only
        if title:
            params3: Dict[str, Any] = {"q": title, "type": "track", "limit": 5}
            if market:
                params3["market"] = market
            print(f"[spotify.query] title_only params={params3}")
            results = do_search(params3)
            if results:
                return results

        return []


class ITunesAPI:
    """Helper class to query the iTunes Search API."""

    SEARCH_URL = "https://itunes.apple.com/search"
    LOOKUP_URL = "https://itunes.apple.com/lookup"

    def search_track(self, title: str, artist: str, country: str = "US") -> List[Dict[str, str]]:
        query = f"{title} {artist}"
        params = {"term": query, "media": "music", "entity": "musicTrack", "limit": 5, "country": country}
        print(f"[itunes.query] params={params}")
        try:
            response = requests.get(self.SEARCH_URL, params=params, timeout=10)
            try:
                print(f"[itunes.request_url] {response.url}")
            except Exception:
                pass
            if response.status_code != 200:
                return []
            data = response.json()
            results = []
            for result in data.get("results", []):
                results.append({
                    "title": result.get("trackName", ""),
                    "artist": result.get("artistName", ""),
                    "url": result.get("trackViewUrl", ""),
                    "duration_ms": result.get("trackTimeMillis"),
                    "album": result.get("collectionName", ""),
                    "track_number": result.get("trackNumber")
                })
            return results
        except Exception:
            return []

    def lookup_track(self, track_id: str) -> Optional[Dict[str, Any]]:
        params = {"id": track_id}
        try:
            resp = requests.get(self.LOOKUP_URL, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])
            if results:
                return results[0]
        except Exception:
            pass
        return None


class YouTubeAPI:
    """Optional helper to query the YouTube Data API for music videos."""

    SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"

    def __init__(self, api_key: Optional[str]) -> None:
        self.api_key = api_key

    def search_track(self, title: str, artist: str, max_results: int = 5) -> List[Dict[str, str]]:
        if not self.api_key:
            return []
        query = f"{title} {artist}"
        params = {
            "key": self.api_key,
            "part": "snippet",
            "q": query,
            "type": "video",
            "maxResults": max_results,
            "videoCategoryId": "10",
        }
        try:
            resp = requests.get(self.SEARCH_URL, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            items = data.get("items", [])
            results = []
            for item in items:
                video_id = item["id"].get("videoId")
                if video_id:
                    results.append({
                        "title": item["snippet"]["title"],
                        "artist": item["snippet"]["channelTitle"],
                        "url": f"https://www.youtube.com/watch?v={video_id}"
                    })
            return results
        except Exception:
            return []


def detect_platform(url: str) -> Optional[str]:
    """Detect the music platform from the hostname."""
    try:
        parsed = urlparse(url)
    except Exception:
        return None
    host = parsed.netloc.lower()
    if "spotify" in host:
        return "spotify"
    if "music.apple.com" in host or "itunes.apple.com" in host:
        return "apple"
    if "youtube.com" in host or "youtu.be" in host:
        return "youtube"
    return None


def extract_spotify_metadata(path: str) -> Optional[str]:
    """Extract the Spotify track ID from the path and return it."""
    # Example Spotify track URL: /track/12345
    match = re.match(r"/.*?/track/([A-Za-z0-9]{10,})", path)
    if match:
        track_id = match.group(1)
        return track_id
    # Another common format: /track/ID
    parts = [p for p in path.split('/') if p]
    if parts and parts[0] == "track" and len(parts) > 1:
        return parts[1]
    return None


def extract_apple_metadata(path: str, query: str) -> Optional[str]:
    """Extract the Apple Music track ID from the URL.

    Apple Music URLs may look like:
    https://music.apple.com/us/album/album-name/albumId?i=songId
    We extract the `i` query parameter if present; otherwise return None.
    """
    qs = parse_qs(query)
    if "i" in qs:
        return qs["i"][0]
    # Sometimes the track ID is the last segment of the path
    parts = [p for p in path.split('/') if p]
    if parts and parts[-1].isdigit():
        return parts[-1]
    return None


def extract_youtube_metadata(path: str, query: str) -> Optional[str]:
    """Extract YouTube video ID from the URL.

    Handles both youtube.com/watch?v=ID and youtu.be/ID formats.
    """
    qs = parse_qs(query)
    if "v" in qs:
        return qs["v"][0]
    parts = [p for p in path.split('/') if p]
    if parts:
        return parts[-1]
    return None


def get_track_metadata(platform: str, track_id: Optional[str], spotify_api: SpotifyAPI, itunes_api: ITunesAPI, youtube_api: YouTubeAPI) -> Tuple[Optional[str], Optional[str], Dict[str, str]]:
    """Retrieve track title and artist along with known platform URLs.

    Returns a tuple of (title, artist, links) where links is a dict mapping
    platform identifiers to canonical track URLs. If metadata could not be
    resolved, title and artist may be None.
    """
    title = None
    artist = None
    links: Dict[str, str] = {}
    if platform == "spotify" and track_id:
        data = spotify_api.get_track(track_id)
        if data:
            title = data.get("name")
            artist = data.get("artists", [{}])[0].get("name")
            links["spotify"] = f"https://open.spotify.com/track/{track_id}"
    elif platform == "apple" and track_id:
        data = itunes_api.lookup_track(track_id)
        if data:
            title = data.get("trackName")
            artist = data.get("artistName")
            # Prefer the canonical URL returned by the API when available
            track_url = data.get("trackViewUrl")
            if track_url:
                links["apple"] = track_url
            else:
                links["apple"] = f"https://music.apple.com/us/album/{track_id}?i={track_id}"
    elif platform == "youtube" and track_id:
        # Without making an API call we can't reliably get metadata for YouTube
        # so we treat the title/artist as unknown but record the link
        links["youtube"] = f"https://www.youtube.com/watch?v={track_id}"
    return title, artist, links


def normalize_string(s: str) -> str:
    """Normalize a string by lowercasing, stripping punctuation, and collapsing whitespace.

    Parenthetical text (e.g., "(Live)", "(Remastered)") is preserved so version/edition
    qualifiers remain part of the tokens.
    """
    if not isinstance(s, str):
        return ''
    s = s.lower()
    s = re.sub(r'[^\w\s]', '', s)  # remove punctuation
    s = re.sub(r'\s+', ' ', s).strip()  # remove extra spaces
    return s

def create_token_set(title: str = "", artist: str = "", album: str = "") -> set:
    """Create a normalized token set from title, artist, and album metadata.
    
    Args:
        title: Song title
        artist: Artist name  
        album: Album name
        
    Returns:
        Set of normalized, deduplicated tokens
    """
    # Stop words to remove
    stop_words = {
        "feat", "featuring", "ft", "ft.", "vs", "vs.", "with", "and", "&", "x"
    }
    
    # Combine all metadata fields
    combined = f"{title or ''} {artist or ''} {album or ''}".strip()
    
    if not combined:
        return set()
    
    # Remove parentheses and brackets (but keep content inside)
    combined = re.sub(r'[()[\]]', '', combined)
    
    # Apply existing normalization (lowercase, remove punctuation)
    normalized = normalize_string(combined)
    
    # Split into tokens
    tokens = normalized.split()
    
    # Remove stop words and empty tokens
    filtered_tokens = [token for token in tokens if token and token not in stop_words]
    
    # Deduplicate while preserving order, then convert to set
    unique_tokens = list(dict.fromkeys(filtered_tokens))
    
    return set(unique_tokens)

def subset_similarity(source_tokens: set, candidate_tokens: set, min_candidate_tokens: int = 2) -> float:
    """Calculate subset-based similarity as percentage of candidate tokens found in source.
    
    Returns the ratio of candidate tokens that exist in source tokens.
    Only penalizes for candidate tokens that don't match source, not for missing source tokens.
    
    Args:
        source_tokens: Tokens from the source track
        candidate_tokens: Tokens from the candidate track  
        min_candidate_tokens: Minimum number of tokens candidate must have
        
    Returns:
        Float between 0.0 and 1.0 representing percentage of candidate tokens found in source
    """
    if not candidate_tokens:
        return 0.0
    
    # Require minimum number of tokens to avoid matching on just one word
    if len(candidate_tokens) < min_candidate_tokens:
        return 0.0
    
    # Calculate how many candidate tokens are found in source
    matching_tokens = len(candidate_tokens.intersection(source_tokens))
    total_candidate_tokens = len(candidate_tokens)
    
    return matching_tokens / total_candidate_tokens

def jaccard_similarity(set1: set, set2: set) -> float:
    """Compute the Jaccard similarity between two sets."""
    intersection = set1 & set2
    union = set1 | set2
    return len(intersection) / len(union)

def find_equivalent_links(title: str, artist: str, spotify_api, itunes_api, yt_api, source_duration_ms: Optional[int] = None, source_album: Optional[str] = None, source_track_number: Optional[int] = None):
    # Create token sets for source metadata
    source_exact_tokens = create_token_set(title, artist, source_album)
    source_alt_tokens = create_token_set(title, artist)  # No album for alternatives
    
    print(f"[debug] source exact tokens: {source_exact_tokens}")
    print(f"[debug] source alternative tokens: {source_alt_tokens}")

    links = {}
    alternatives = {}

    def process_results(service_name: str, results: List[Dict[str, str]], links_dict: Dict[str, str], alt_dict: Dict[str, List]):
        exact_candidates = []
        alt_candidates = []
        
        for track in results:
            track_title = track.get('title', '')
            track_artist = track.get('artist', '')
            track_album = track.get('album', '')
            track_duration = track.get('duration_ms')
            track_number = track.get('track_number')
            
            # Create token sets for candidate track
            candidate_exact_tokens = create_token_set(track_title, track_artist, track_album)
            candidate_alt_tokens = create_token_set(track_title, track_artist)
            
            # Calculate similarities
            exact_similarity = subset_similarity(source_exact_tokens, candidate_exact_tokens)
            alt_similarity = subset_similarity(source_alt_tokens, candidate_alt_tokens)
            
            # Check track number match first (needed for duration tolerance calculation)
            track_number_match = False
            if source_track_number and track_number:
                track_number_match = source_track_number == track_number
            
            # Check duration tolerance with different thresholds for exact vs alternative matches
            exact_duration_ok = True
            alt_duration_ok = True
            duration_diff = 0
            if source_duration_ms and track_duration:
                duration_diff = abs(source_duration_ms - track_duration)
                
                # Dynamic duration tolerance based on track number match
                exact_duration_tolerance = 5000 if track_number_match else 1000  # 5s if track numbers match, 1s otherwise
                exact_duration_ok = duration_diff <= exact_duration_tolerance
                alt_duration_ok = duration_diff <= 10000   # ±10s for alternatives (unchanged)
                
            print(f"[debug] {service_name} candidate: '{track_title}' by '{track_artist}' from '{track_album}'")
            print(f"[debug]   exact tokens: {candidate_exact_tokens}")
            print(f"[debug]   alt tokens: {candidate_alt_tokens}")
            print(f"[debug]   exact similarity: {exact_similarity:.3f}, alt similarity: {alt_similarity:.3f}")
            print(f"[debug]   duration tolerance: {exact_duration_tolerance}ms (track numbers {'match' if track_number_match else 'do not match'})")
            print(f"[debug]   exact duration ok: {exact_duration_ok}, alt duration ok: {alt_duration_ok} (diff: {duration_diff}ms)")
            print(f"[debug]   track number match: {track_number_match} (source: {source_track_number}, candidate: {track_number})")
            
            # Determine exact match threshold based on track number match
            exact_threshold = 0.4 if track_number_match else 0.75
            print(f"[debug]   using exact threshold: {exact_threshold} (track numbers {'match' if track_number_match else 'do not match'})")
            
            # Check for exact match (dynamic threshold based on track number match)
            if exact_similarity >= exact_threshold and exact_duration_ok:
                print(f"[debug]   -> exact match candidate!")
                exact_candidates.append({
                    "track": track,
                    "similarity": exact_similarity,
                    "duration_diff": duration_diff,
                    "album_match": track_album.lower() == (source_album or '').lower() if source_album else False,
                    "missing_data_penalty": 0.05 if not track_album or track_album.strip() == '' else 0,
                    "track_number_match": track_number_match
                })
                continue
                
            # Check for alternative match (0.75 threshold on title+artist only)
            if alt_similarity >= 0.5 and alt_duration_ok:
                print(f"[debug]   -> alternative match candidate!")
                # Check for version indicators and missing data penalties
                version_penalty = 0
                missing_data_penalty = 0
                
                # Check if candidate has version words but source doesn't
                version_words = ['live', 'remix', 'cover', 'acoustic', 'demo']
                title_lower = track_title.lower()
                source_title_lower = title.lower()
                
                candidate_has_version = any(word in title_lower for word in version_words)
                source_has_version = any(word in source_title_lower for word in version_words)
                
                # Only apply penalty if candidate has version words but source doesn't
                if candidate_has_version and not source_has_version:
                    version_penalty = 0.1
                
                # Penalty for missing album data
                if not track_album or track_album.strip() == '':
                    missing_data_penalty = 0.05
                
                total_penalty = version_penalty + missing_data_penalty
                
                alt_candidates.append({
                    "track": track,
                    "similarity": alt_similarity,
                    "duration_diff": duration_diff,
                    "version_penalty": version_penalty,
                    "missing_data_penalty": missing_data_penalty,
                    "total_penalty": total_penalty,
                    "service": service_name
                })
            else:
                reason = []
                if exact_similarity < 0.75 and alt_similarity < 0.75:
                    reason.append("similarity below threshold")
                if not exact_duration_ok and not alt_duration_ok:
                    reason.append("duration mismatch")
                print(f"[debug]   -> no match ({', '.join(reason)})")
        
        # Rank and select best exact match
        if exact_candidates:
            # Sort by: similarity (desc), album match (desc), track number match (desc), missing data penalty (asc), duration accuracy (asc)
            best_exact = max(exact_candidates, key=lambda x: (
                x["similarity"],
                x["album_match"],
                x["track_number_match"],  # 3rd priority
                -x["missing_data_penalty"],  # Negative for ascending order
                -x["duration_diff"]          # Negative for ascending order (last priority)
            ))
            links_dict[service_name] = best_exact["track"].get('url')
            print(f"[debug] Selected best exact match: similarity={best_exact['similarity']:.3f}, duration_diff={best_exact['duration_diff']}ms, track_number_match={best_exact['track_number_match']}")
        
        # Rank and store alternatives
        if alt_candidates:
            # Sort by: similarity (desc), total penalty (asc), duration accuracy (asc)
            alt_candidates.sort(key=lambda x: (
                -x["similarity"],     # Negative for descending order
                x["total_penalty"],
                x["duration_diff"]    # Last priority
            ))
            
            # Convert to the format expected by alternatives dict
            alt_items = []
            for candidate in alt_candidates:
                track = candidate["track"]
                alt_items.append({
                    "title": track.get('title', ''),
                    "artist": track.get('artist', ''),
                    "album": track.get('album', ''),
                    "url": track.get('url', ''),
                    "durationMs": track.get('duration_ms'),
                    "service": service_name
                })
            alt_dict[service_name] = alt_items
            print(f"[debug] Ranked {len(alt_items)} alternatives for {service_name}")
    
    # Process Spotify results
    spotify_results = spotify_api.search_track(title, artist)
    print("Spotify results:", len(spotify_results) if spotify_results else 0, "tracks")
    process_results('spotify', spotify_results, links, alternatives)

    # Process Apple Music results
    apple_results = itunes_api.search_track(title, artist)
    print("Apple results:", len(apple_results) if apple_results else 0, "tracks")
    process_results('apple', apple_results, links, alternatives)

    # Process YouTube results
    yt_results = yt_api.search_track(title, artist)
    print("YouTube results:", len(yt_results) if yt_results else 0, "tracks")
    process_results('youtube', yt_results, links, alternatives)

    return links, alternatives


def get_preference(request: Request, pref_param: Optional[str]) -> Optional[str]:
    """Determine the user's preferred platform.

    Order of precedence:
    1. explicit ``pref`` query parameter
    2. ``music_pref`` cookie
    3. None (no preference)
    """
    if pref_param:
        return pref_param.lower()
    cookie = request.cookies.get("music_pref")
    if cookie:
        return cookie.lower()
    return None


def build_fallback_html(title: str, artist: str, links: dict, user_pref: str = '', alternatives: Optional[dict] = None):
    alternatives = alternatives or {}
    html = f"""
    <html>
    <head><title>Couldn't find a match</title></head>
    <body style="font-family:sans-serif;padding:2em;">
      <h1>Couldn't automatically find a match</h1>
      <p>We couldn't find an equivalent link for <strong>{title}</strong> by <strong>{artist}</strong> on the requested service.</p>
    """

    if alternatives:
        html += "<h2>We did find similar songs:</h2><ul>"
        for service, items in alternatives.items():
            for item in items:
                if isinstance(item, dict):
                    t = item.get('title', 'Unknown title')
                    ar = item.get('artist', 'Unknown artist')
                    al = item.get('album', '')
                    url = item.get('url', '#')
                    label = f"{service.title()}: {t} — {ar}"
                    if al:
                        label += f" — {al}"
                    html += f'<li><a href="{url}" target="_blank">{label}</a></li>'
                else:
                    # Backward compat if any entries are plain URLs
                    url = str(item)
                    html += f'<li><a href="{url}" target="_blank">{service.title()} result</a></li>'
        html += "</ul>"

    html += "<p>Please select your preferred platform:</p><ul>"
    for service in ['spotify', 'apple', 'youtube']:
        if service in links:
            html += f'<li><a href="{links[service]}" target="_blank">{service.title()}</a></li>'
    html += "</ul></body></html>"

    return html


@app.get("/redirect", response_class=HTMLResponse)
async def redirect_handler(request: Request, url: str, pref: Optional[str] = None) -> Response:
    """Main redirect endpoint.

    :param url: The original music streaming URL to convert.
    :param pref: Optional query parameter to override the preferred platform.
    """
    if not url:
        raise HTTPException(status_code=400, detail="Missing 'url' parameter")

    # Determine user preference from query param or cookie
    user_pref = get_preference(request, pref)
    # Initialize API helpers
    spotify_api = SpotifyAPI(os.getenv("SPOTIFY_CLIENT_ID"), os.getenv("SPOTIFY_CLIENT_SECRET"))
    itunes_api = ITunesAPI()
    yt_api = YouTubeAPI(os.getenv("YOUTUBE_API_KEY"))

    # Parse the provided URL
    parsed = urlparse(url)
    platform = detect_platform(url)
    if not platform:
        # Unknown platform, just redirect to original
        return RedirectResponse(url=url, status_code=302)

    track_id = None
    # Extract platform-specific track identifiers
    if platform == "spotify":
        track_id = extract_spotify_metadata(parsed.path)
    elif platform == "apple":
        track_id = extract_apple_metadata(parsed.path, parsed.query)
    elif platform == "youtube":
        track_id = extract_youtube_metadata(parsed.path, parsed.query)

    # Get metadata and known links for the original track
    title, artist, links = get_track_metadata(platform, track_id, spotify_api, itunes_api, yt_api)
    links[platform] = url

    # Determine source duration (ms) and album when possible for filtering/strict exact matching
    source_duration_ms: Optional[int] = None
    source_album: Optional[str] = None
    source_track_number: Optional[int] = None
    try:
        if platform == "spotify" and track_id:
            sdata = SpotifyAPI(os.getenv("SPOTIFY_CLIENT_ID"), os.getenv("SPOTIFY_CLIENT_SECRET")).get_track(track_id)
            if sdata:
                source_duration_ms = sdata.get("duration_ms")
                source_album = (sdata.get("album") or {}).get("name")
                source_track_number = sdata.get("track_number")
        elif platform == "apple" and track_id:
            adata = ITunesAPI().lookup_track(track_id)
            if adata:
                source_duration_ms = adata.get("trackTimeMillis")
                source_album = adata.get("collectionName")
                source_track_number = adata.get("trackNumber")
        # For YouTube we don't fetch duration here (would require videos.list)
    except Exception:
        source_duration_ms = None

    # Debug: include album in the source metadata log
    print(f"[debug] source metadata -> title='{title}', artist='{artist}', album='{source_album}', duration_ms='{source_duration_ms}', track_number='{source_track_number}'")

    # If user has a preferred service and it's different from the original
    if user_pref and user_pref != platform:
        # Attempt to find a link for the preferred service
        print("Links dict:", links)
        target_url = links.get(user_pref)

        if not target_url and title and artist:
            # Search for equivalents across services (returns both matches and alternatives)
            equivalent_links, alt_matches = find_equivalent_links(title, artist, spotify_api, itunes_api, yt_api, source_duration_ms, source_album, source_track_number)
            print(f"[debug] equivalent_links: {equivalent_links}")
            print(f"[debug] alt_matches services: {list(alt_matches.keys())}")
            print(f"[debug] user_pref: {user_pref}")
            links.update({k: v for k, v in equivalent_links.items() if k not in links})
            # Keep alternatives limited to the preferred provider for display,
            # but pass as a dict to the fallback HTML and print a short summary
            alternatives = {user_pref: alt_matches.get(user_pref, [])}
            target_url = links.get(user_pref)
            print(f"[debug] target_url for pref '{user_pref}': {target_url}")

        if target_url:
            # Set the preference cookie on the response
            response = RedirectResponse(url=target_url, status_code=302)
            response.set_cookie("music_pref", user_pref, max_age=30*24*3600)
            return response

        # If no match found for preferred service, fall back to page with alt options
        html = build_fallback_html(title, artist, links, user_pref, alternatives)
        return HTMLResponse(content=html, status_code=200)

    # No preference provided or same platform – redirect to original URL
    response = RedirectResponse(url=url, status_code=302)
    if user_pref:
        response.set_cookie("music_pref", user_pref, max_age=30*24*3600)
    return response


@app.get("/set_preference")
async def set_preference(pref: str) -> Response:
    """Endpoint to persist the user's preferred music service in a cookie.

    This endpoint can be called from the frontend when the user selects a
    preferred service. It returns a simple JSON response and sets the
    ``music_pref`` cookie on the client for 30 days.
    """
    if not pref:
        raise HTTPException(status_code=400, detail="Missing 'pref' parameter")
    response = Response(content=json.dumps({"status": "ok", "pref": pref}), media_type="application/json")
    response.set_cookie("music_pref", pref.lower(), max_age=30*24*3600)
    return response