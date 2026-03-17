---
title: Configure labels
menuTitle: Configure labels
description: How to configure labels for Grafana OnCall integrations and alert groups.
weight: 200
keywords:
  - OnCall
  - Integrations
  - Alert routing
  - Labels
  - Static
  - Dynamic labels
  - Multi-label extraction
labels:
  products:
    - cloud
canonical: https://grafana.com/docs/oncall/latest/configure/integrations/labels
aliases:
  - /docs/grafana-cloud/alerting-and-irm/oncall/configure/integrations/labels
  - ../integrations/ # /docs/oncall/<ONCALL_VERSION>/configure/integrations/labels
---
# Configure labels

{{< admonition type="note" >}}
This feature is available exclusively on Grafana Cloud.
{{< /admonition >}}

Labels are a powerful feature in Grafana OnCall that can help categorize and organize your integrations and alert groups.
This guide walks through how to manage reusable label keys and values, assign labels to integrations, filter resources by labels,
and use labels in alert group mapping.

## Manage label keys and values

Use the **Labels** page to create and maintain reusable label keys and values for your organization.

From this page you can:

- create label keys and values before they are used by an integration
- mark a key as a managed label
- assign colors to keys and values for easier scanning in the UI
- rename or delete existing keys and values
- review how many values are defined for a key

You can manage keys in the **Keys** tab and individual values in the **Values** tab.

{{< admonition type="note" >}}
Access to the **Labels** page is controlled by RBAC permissions. Users typically need label read access to view labels,
label write access to update keys and values, and label create access to create new keys.
{{< /admonition >}}

## Integrations and labels

Labels can be assigned to integrations to help manage and filter them based on specific criteria.
You may find it useful to organize integrations based on service, region, or any other custom attribute.

To assign labels to an integration:

1. Go to the **Integrations** tab and select an integration from the list.
2. Click the **three dots** next to the integration name and select **Integration settings**.
3. Click **Add** button in the **Integration labels** section. You can remove a label using the X button next to the key-value pair.
4. Define a key and value pair for the label, either by selecting from an existing list or typing new ones in the fields. Press enter/return to accept.
5. Click **Save** when finished.

To filter integrations by labels:

1. Go to the **Integrations** tab.
2. Locate the **Search or filter results…** dropdown and select **Label**.
3. Start typing to find suggestions and select the key-value pair you’d like to filter by.

Labels are automatically assigned to each alert group based on the labels assigned to the integration.
Static integration labels use the exact key/value pair configured on the integration.

## Alert Group labels

Alert Group labels offer more granular control. With alert group labeling, you can:

- Assign static labels to alert groups.
- Filter alert groups by labels.
- Customize the Alert Group table.
- Pass labels in Webhooks.
- Use predefined label values or Jinja-based dynamic values.

### Assign labels to Alert Groups

Alert Group labeling can be configured for each integration. To find the Alert Group labeling settings:

1. Navigate to the **Integrations** tab.
2. Select an integration from the list of enabled integrations.
3. Click the three dots next to the integration name.
4. Choose **Integration settings**. You can configure alert group labels mapping in the **Mapping** section.

A maximum of 15 labels can be assigned to an alert group. If there are more than 15 labels, only the first 15 will be assigned.

### Dynamic labels

Dynamic labels allow you to assign labels to alert groups using values extracted from the incoming payload.
The key remains fixed, while the value can either be rendered from a Jinja template or chosen from an existing
label value when a workflow supports predefined dynamic selections.

Dynamic labels are attached to the alert group, not to the integration itself.

1. In the **Integration settings** tab, navigate to **Dynamic Labels**.
2. Press the **Add Label** button.

#### Add dynamic labels

1. Choose or create a key from the dropdown list.
2. Enter a template to parse the value for the given key from the alert payload.

You can also keep using existing static key/value pairs in the same mapping section.
This is useful when some labels should always be applied, while others should be derived from the payload.

To illustrate the Dynamic Labeling feature, let's consider an example where a dynamic label is created with a `severity` key
and a template to parse values for that key:

```jinja2
{{ payload.get("severity) }}
```

Created dynamic label:
<img src="/static/img/oncall/dynamic-label-example.png" width="700px">

Two alerts were received and grouped to two different alert groups:

Alert 1:

```json
{
  "title": "critical alert",
  "severity": "critical"
}
```

Alert 2:

```json
{
  "title": "warning alert",
  "severity": "warning"
}
```

As a result:

- The first alert group will have a label: `severity: critical`.
- The second alert group will have a label: `severity: warning`.

### Multi-label extraction template

This feature enables users to extract and modify multiple labels from the alert payload using a single template.
It supports dynamic values and dynamic keys, with the template expected to result in a valid JSON object.

Consider the following example demonstrating the extraction of labels from a Grafana Alerting payload:

Incoming payload:

```json
{
  ...
  "commonLabels": {
    "job": "node",
    "severity": "critical",
    "alertname": "InstanceDown"
  },
  ...
}
```

Template to parse it:

```jinja2
{{ payload.commonLabels | tojson }}
```

As a result `job`, `severity` and `alertname` labels will be assigned to the alert group:

<img src="/static/img/oncall/mutli-label-extraction-result.png" width="700px">

An advanced example showcases the extraction of labels from various fields of the alert payload, utilizing the Grafana Alerting payload:

```jinja2
{%- set labels = {} -%}
{# add several labels #}
{%- set labels = dict(labels, **payload.commonLabels) -%}
{# add one label #}
{%- set labels = dict(labels, **{"status": payload.status}) -%}
{# add label not from payload #}
{%- set labels = dict(labels, **{"service": "oncall"}) -%}
{# dump labels dict to json string, so OnCall can parse it #}
{{ labels | tojson }}
```

### Alert group table customization

The Alert Group table can be customized to suit individual preferences.
You can select and manage the columns displayed in the table, and add custom columns based on labels.
This customization is user-specific, allowing each user to personalize their view.

#### Manage default columns

By default, the Columns dropdown provides a list of predefined columns that users can enable or disable based on their preferences.

To manage default columns use the toggler next to each column name to enable or disable its visibility in the table.

#### Add custom columns

Users with admin permissions have the ability to add custom columns based on labels. Follow these steps to add a custom column:

1. Press the Add button in the Columns dropdown. A modal will appear.
2. In the modal, begin typing the name of the labels key you want to create a column for.
3. Select the desired label from the options presented and press the Add button.
4. The new custom column, titled with the label's key, will now be available as an option in the Column Settings for all users.

### Label behavior

**Assignment limits:**
OnCall allows the assignment of up to 15 labels to an alert group.
If there are more than 15 labels to be assigned, only the first 15 labels (sorted alphabetically)
from the first alert in the group will be assigned.

**Label persistence:**
Once a label is assigned to an alert group, it remains unchanged, even if the label is edited.
This approach considers the label as historical data.

**Deletion behavior:**
Deleting a label key or value removes it from future selection and also removes existing associations that reference that
deleted key or value.
