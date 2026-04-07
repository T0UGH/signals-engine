"""X HTTP client for timeline API.

Parameterized: queryId and operationName are passed per-call, so a single
client instance can serve multiple X GraphQL endpoints (HomeTimeline,
HomeLatestTimeline, etc.) without needing separate client subclasses.
"""

import httpx

from .auth import XAuth, auth_to_cookie_header
from .errors import AuthError, RateLimitError, TransportError, SourceUnavailableError

# Default queryId for the home timeline (fallback; callers should pass their own)
DEFAULT_HOME_QUERY_ID = "c-CzHF1LboFilMpsx4ZCrQ"

# GraphQL FEATURES — kept in sync with opencli's FEATURES object
GRAPHQL_FEATURES = {
    "rweb_video_screen_enabled": False,
    "profile_label_improvements_pcf_label_in_post_enabled": True,
    "rweb_tipjar_consumption_enabled": True,
    "verified_phone_label_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "premium_content_api_read_enabled": False,
    "communities_web_enable_tweet_community_results_fetch": True,
    "c9s_tweet_anatomy_moderator_badge_enabled": True,
    "responsive_web_grok_analyze_button_fetch_trends_enabled": False,
    "responsive_web_grok_analyze_post_followups_enabled": True,
    "responsive_web_jetfuel_frame": False,
    "responsive_web_grok_share_attachment_enabled": True,
    "articles_preview_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": True,
    "tweet_awards_web_tipping_enabled": False,
    "responsive_web_grok_show_grok_translated_post": False,
    "responsive_web_grok_analysis_button_from_backend": False,
    "creator_subscriptions_quote_tweet_preview_enabled": False,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": True,
    "responsive_web_grok_image_annotation_enabled": True,
    "responsive_web_enhance_cards_enabled": False,
}


class XClient:
    """Low-level X GraphQL API client.

    Wraps httpx and handles request construction, auth headers,
    and HTTP-level error classification.

    The queryId and operationName are passed per-call (not hardcoded), so
    one client instance can query any X GraphQL timeline endpoint.
    """

    BASE_URL = "https://x.com"

    def __init__(self, auth: XAuth, timeout: int = 30):
        self.auth = auth
        self.timeout = timeout

    def _build_url(
        self,
        query_id: str,
        operation_name: str,
        count: int,
        cursor: str | None = None,
        extra_variables: dict | None = None,
    ) -> str:
        """Build the GraphQL URL with variables and features query params."""
        import json
        import urllib.parse

        variables: dict = {
            "count": count,
            "includePromotedContent": False,
        }
        if cursor:
            variables["cursor"] = cursor
        if extra_variables:
            variables.update(extra_variables)

        params = {
            "variables": json.dumps(variables),
            "features": json.dumps(GRAPHQL_FEATURES),
        }
        query = urllib.parse.urlencode(params)
        graphql_path = f"/i/api/graphql/{query_id}/{operation_name}"
        return f"{self.BASE_URL}{graphql_path}?{query}"

    def _headers(self) -> dict[str, str]:
        """Build request headers from auth state."""
        cookie_str = auth_to_cookie_header(self.auth)
        return {
            "Authorization": f"Bearer {self.auth.bearer_token}",
            "X-Csrf-Token": self.auth.cookies.get("ct0", ""),
            "X-Twitter-Auth-Type": "OAuth2Session",
            "X-Twitter-Active-User": "yes",
            "Cookie": cookie_str,
            "Accept": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        }

    def fetch_timeline_raw(
        self,
        query_id: str,
        operation_name: str,
        count: int = 40,
        cursor: str | None = None,
        extra_variables: dict | None = None,
    ) -> dict:
        """Fetch one page of raw timeline JSON.

        Args:
            query_id: X GraphQL queryId (e.g. "c-CzHF1LboFilMpsx4ZCrQ").
            operation_name: GraphQL operation name (e.g. "HomeTimeline").
            count: number of tweets to request per page.
            cursor: pagination cursor (None for first page).
            extra_variables: additional GraphQL variables merged into the request.

        Returns:
            Raw X API JSON dict

        Raises:
            AuthError: 401 Unauthorized
            RateLimitError: 429 Too Many Requests
            TransportError: network-level failures
            SourceUnavailableError: 5xx or unexpected HTTP status
        """
        url = self._build_url(query_id, operation_name, count, cursor, extra_variables)
        headers = self._headers()

        try:
            # Disable HTTP/2 — X.com's HTTP/2 support is unstable and causes
            # intermittent SSL/EOF errors. HTTP/1.1 is reliable.
            transport = httpx.HTTPTransport(retries=1)
            client = httpx.Client(transport=transport, timeout=self.timeout)
            try:
                response = client.get(url, headers=headers)
            finally:
                client.close()
        except httpx.TimeoutException as e:
            raise TransportError(f"Request timed out after {self.timeout}s: {e}") from e
        except httpx.ConnectError as e:
            raise TransportError(f"Connection failed: {e}") from e
        except httpx.RequestError as e:
            raise TransportError(f"Request failed: {e}") from e

        if response.status_code == 401:
            raise AuthError(
                "HTTP 401 Unauthorized — cookies may be expired or invalid. "
                "Refresh your cookies at x.com and export a fresh cookie file."
            )
        if response.status_code == 429:
            raise RateLimitError(
                "HTTP 429 Too Many Requests — X is rate-limiting this client. "
                "Wait before retrying."
            )
        if response.status_code >= 500:
            raise SourceUnavailableError(
                f"X server error: HTTP {response.status_code}. "
                f"Temporarily unavailable."
            )

        return response.json()
