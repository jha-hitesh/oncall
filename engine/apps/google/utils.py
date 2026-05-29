import datetime

from apps.google import constants


def user_granted_all_required_scopes(user_granted_scopes: str, required_scopes=None) -> bool:
    """
    `user_granted_scopes` should be a space-separated string of scopes
    """
    granted_scopes = user_granted_scopes.split(" ")
    scopes_to_check = required_scopes if required_scopes is not None else constants.REQUIRED_OAUTH_SCOPES
    return all(scope in granted_scopes for scope in scopes_to_check)


def datetime_strftime(dt: datetime.datetime) -> str:
    return dt.strftime(constants.GOOGLE_CALENDAR_EVENT_DATETIME_FORMAT)


def datetime_strptime(dt: str) -> datetime.datetime:
    return datetime.datetime.strptime(dt, constants.GOOGLE_CALENDAR_EVENT_DATETIME_FORMAT)
