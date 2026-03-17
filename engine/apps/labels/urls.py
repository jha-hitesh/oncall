from django.urls import re_path

from .views import LabelsViewSet

app_name = "labels"

urlpatterns = [
    re_path(r"^labels/keys/?$", LabelsViewSet.as_view({"get": "get_keys"}), name="get_keys"),
    re_path(
        r"^labels/id/(?P<key_id>[\w\-]+)/?$",
        LabelsViewSet.as_view({"get": "get_key", "put": "rename_key", "delete": "delete_key"}),
        name="get_update_key",
    ),
    re_path(
        r"^labels/name/(?P<key_name>[\w\-]+)/?$",
        LabelsViewSet.as_view({"get": "get_key_by_name"}),
        name="get_key_by_name",
    ),
    re_path(r"^labels/id/(?P<key_id>[\w\-]+)/values/?$", LabelsViewSet.as_view({"post": "add_value"}), name="add_value"),
    re_path(
        r"^labels/id/(?P<key_id>[\w\-]+)/values/(?P<value_id>[\w\-]+)/?$",
        LabelsViewSet.as_view({"get": "get_value", "put": "rename_value", "delete": "delete_value"}),
        name="get_update_value",
    ),
    re_path(r"^labels/?$", LabelsViewSet.as_view({"post": "create_label"}), name="create_label"),
]
