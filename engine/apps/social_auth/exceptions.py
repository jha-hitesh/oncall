class InstallMultiRegionSlackException(Exception):
    pass


class UserLoginOAuth2MattermostException(Exception):
    pass


GOOGLE_AUTH_MISSING_GRANTED_SCOPE_ERROR = "missing_granted_scope"
GOOGLE_AUTH_MISSING_REFRESH_TOKEN_ERROR = "missing_refresh_token"
MATTERMOST_AUTH_FETCH_USER_ERROR = "failed_to_fetch_user"
