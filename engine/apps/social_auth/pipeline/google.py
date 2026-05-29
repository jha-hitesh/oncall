import logging
import typing

import requests
from django.conf import settings
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.http import HttpResponse
from rest_framework import status
from social_core.backends.base import BaseAuth

from apps.google.utils import user_granted_all_required_scopes
from apps.grafana_plugin.ui_url_builder import UIURLBuilder
from apps.social_auth.exceptions import GOOGLE_AUTH_MISSING_GRANTED_SCOPE_ERROR, GOOGLE_AUTH_MISSING_REFRESH_TOKEN_ERROR
from apps.social_auth.types import GoogleOauth2Response
from apps.user_management.models import Organization, User

logger = logging.getLogger(__name__)


def connect_user_to_google(
    strategy,
    response: GoogleOauth2Response,
    user: User,
    organization: Organization,
    *args,
    **kwargs,
):
    granted_scopes = response.get("scope", "")

    if not user_granted_all_required_scopes(granted_scopes):
        logger.warning(
            f"User {user.pk} did not grant all required scopes, redirecting w/ error message "
            f"granted_scopes={granted_scopes}"
        )

        strategy.session[REDIRECT_FIELD_NAME] = UIURLBuilder(organization).user_profile(
            f"?google_error={GOOGLE_AUTH_MISSING_GRANTED_SCOPE_ERROR}"
        )

        return HttpResponse(status=status.HTTP_400_BAD_REQUEST)

    # at this point everything is correct and we can persist the Google OAuth2 token + generate any other relevant
    # config for the user
    #
    # be sure to clear any pre-existing sessions, in case the user previously enecountered errors we want
    # to be sure to clear these so they do not see them again
    strategy.session.flush()

    try:
        user.save_google_oauth2_settings(response)
    except ValueError:
        logger.warning(f"User {user.pk} did not receive a Google refresh token, redirecting w/ error message")
        strategy.session[REDIRECT_FIELD_NAME] = UIURLBuilder(organization).user_profile(
            f"?google_error={GOOGLE_AUTH_MISSING_REFRESH_TOKEN_ERROR}"
        )
        return HttpResponse(status=status.HTTP_400_BAD_REQUEST)


def disconnect_user_google_oauth2_settings(backend: typing.Type[BaseAuth], user: User, *args, **kwargs):
    """
    Don't use `google_oauth2_user.access_token` when revoking token, use `refresh_token` instead. If we use
    the access token, we may get an HTTP 400 from Google because the token may be invalid or revoked.

    https://stackoverflow.com/a/18578660/3902555
    """
    user_pk = user.pk
    google_oauth2_user = user.google_oauth2_user

    logger.info(f"Disconnecting user {user_pk} from Google OAuth2")

    try:
        backend.revoke_token(google_oauth2_user.refresh_token, google_oauth2_user.google_user_id)
    except requests.exceptions.HTTPError as e:
        response = e.response

        logger.error(f"There was an HTTP error when trying to revoke Google OAuth2 token for user={user_pk}")

        if response.status_code == 400:
            error_details = response.json()
            error_code = error_details["error"]
            error_description = error_details["error_description"]

            logger.error(
                f"There was an HTTP 400 error when trying to revoke Google OAuth2 token for user={user_pk} "
                f"error_code={error_code} error_description={error_description}"
            )

            error_codes_to_ignore = ["invalid_token"]

            if error_code not in error_codes_to_ignore:
                raise e
            else:
                logger.info(f"Google OAuth2 token for user {user_pk} is already invalid or revoked, ignoring error")

    user.reset_google_oauth2_settings()

    logger.info(f"Successfully disconnected user {user.pk} from Google OAuth2")


def connect_organization_to_google(
    strategy,
    response: GoogleOauth2Response,
    user: User,
    organization: Organization,
    *args,
    **kwargs,
):
    granted_scopes = response.get("scope", "")

    if not user_granted_all_required_scopes(granted_scopes, settings.SOCIAL_AUTH_GOOGLE_OAUTH2_ORG_SCOPE):
        logger.warning(
            f"Organization {organization.pk} did not grant all required scopes, redirecting w/ error message "
            f"granted_scopes={granted_scopes}"
        )

        strategy.session[REDIRECT_FIELD_NAME] = UIURLBuilder(organization).settings(
            f"?tab=GoogleCalendar&google_error={GOOGLE_AUTH_MISSING_GRANTED_SCOPE_ERROR}"
        )

        return HttpResponse(status=status.HTTP_400_BAD_REQUEST)

    strategy.session.flush()

    try:
        organization.save_google_oauth2_organization_settings(response, connected_by=user)
    except ValueError:
        strategy.session[REDIRECT_FIELD_NAME] = UIURLBuilder(organization).settings(
            f"?tab=GoogleCalendar&google_error={GOOGLE_AUTH_MISSING_REFRESH_TOKEN_ERROR}"
        )
        return HttpResponse(status=status.HTTP_400_BAD_REQUEST)


def disconnect_organization_google_oauth2_settings(
    backend: typing.Type[BaseAuth], organization: Organization, *args, **kwargs
):
    google_oauth2_organization = organization.google_oauth2_organization

    logger.info(f"Disconnecting organization {organization.pk} from Google OAuth2")

    try:
        backend.revoke_token(google_oauth2_organization.refresh_token, google_oauth2_organization.google_user_id)
    except requests.exceptions.HTTPError as e:
        response = e.response

        if response.status_code == 400 and response.json().get("error") == "invalid_token":
            logger.info(f"Google OAuth2 token for organization {organization.pk} is already invalid or revoked")
        else:
            raise e

    organization.reset_google_oauth2_organization_settings()
