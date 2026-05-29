from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.permissions import RBACPermission
from apps.api.serializers.google_calendar import (
    GoogleCalendarEventCreateResponseSerializer,
    GoogleCalendarEventCreateSerializer,
)
from apps.auth_token.auth import PluginAuthentication
from apps.google.client import (
    GoogleCalendarAPIClient,
    GoogleCalendarGenericHTTPError,
    GoogleCalendarRefreshError,
    GoogleCalendarUnauthorizedHTTPError,
)


class CurrentOrganizationGoogleCalendarEventView(APIView):
    authentication_classes = (PluginAuthentication,)
    permission_classes = (IsAuthenticated, RBACPermission)
    rbac_permissions = {
        "post": [RBACPermission.Permissions.OTHER_SETTINGS_WRITE],
    }

    @extend_schema(
        request=GoogleCalendarEventCreateSerializer,
        responses={
            status.HTTP_201_CREATED: GoogleCalendarEventCreateResponseSerializer,
        },
    )
    def post(self, request):
        organization = request.auth.organization

        if not organization.has_google_oauth2_organization_connected:
            return Response(
                {"detail": "Google Calendar is not connected for this organization."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = GoogleCalendarEventCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        google_organization = organization.google_oauth2_organization
        client = GoogleCalendarAPIClient(google_organization.access_token, google_organization.refresh_token)

        try:
            event = client.create_event(**serializer.validated_data)
        except GoogleCalendarUnauthorizedHTTPError:
            return Response(
                {"detail": "Google Calendar connection is missing required permissions. Reconnect Google Calendar."},
                status=status.HTTP_403_FORBIDDEN,
            )
        except GoogleCalendarRefreshError:
            organization.reset_google_oauth2_organization_settings()
            return Response(
                {"detail": "Google Calendar connection expired. Reconnect Google Calendar."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except GoogleCalendarGenericHTTPError:
            return Response(
                {"detail": "Failed to create Google Calendar event."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        response_data = {
            "id": event["id"],
            "html_link": event.get("htmlLink"),
            "hangout_link": event.get("hangoutLink"),
        }
        return Response(response_data, status=status.HTTP_201_CREATED)
