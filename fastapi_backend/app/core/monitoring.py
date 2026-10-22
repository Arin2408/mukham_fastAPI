import os

import sentry_sdk

from app.core.config import settings


def init_sentry() -> None:
    """
    Sends unexpected server errors (500s) to Sentry, with the failing line.
    Off unless SENTRY_DSN is set.

    Personal data stays here: no request bodies (face images, passwords),
    no IP addresses or signed-in user, and the default scrubber removes
    Authorization headers, cookies and token or password fields.
    """
    if not settings.sentry_dsn:
        return

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment,
        # Render sets this to the deployed commit, so an error shows which
        # version it came from.
        release=os.environ.get("RENDER_GIT_COMMIT"),
        send_default_pii=False,
        max_request_body_size="never",
        # Errors only: no performance tracing, which uses up the free plan.
        traces_sample_rate=0,
    )
