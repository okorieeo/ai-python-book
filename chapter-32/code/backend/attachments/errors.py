class MediaRejected(Exception):
    """The file is not acceptable. Permanent: retrying the same file can never help.

    `code` is a short machine-readable reason that is safe to show to the app. `message` is for people.
    """

    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code
        self.message = message or code


class ProviderUnavailable(Exception):
    """A speech or vision provider failed in a way that may pass (timeout, 429, 5xx). Retry later."""


class ProviderConfigError(Exception):
    """Our configuration is wrong (bad key, unknown model). Not the user's problem; alert the developers."""
