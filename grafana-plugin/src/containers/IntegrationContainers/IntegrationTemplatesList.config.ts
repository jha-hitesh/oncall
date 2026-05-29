import { cloneDeep } from 'lodash-es'

import { MONACO_INPUT_HEIGHT_SMALL, MONACO_INPUT_HEIGHT_TALL } from 'pages/integration/IntegrationCommon.config';
import { AppFeature } from 'state/features';

import { TemplateBlock, commonTemplatesToRender } from './IntegrationCommonTemplatesList.config';

const additionalTemplatesToRender: TemplateBlock[] = [
  {
    name: 'Google Calendar',
    contents: [
      {
        name: 'google_calendar_title_template',
        label: 'Title',
        height: MONACO_INPUT_HEIGHT_SMALL,
      },
      {
        name: 'google_calendar_description_template',
        label: 'Description',
        height: MONACO_INPUT_HEIGHT_TALL,
      },
    ],
  },
  {
    name: 'MS Teams',
    contents: [
      {
        name: 'msteams_title_template',
        label: 'Title',
        height: MONACO_INPUT_HEIGHT_SMALL,
      },
      {
        name: 'msteams_message_template',
        label: 'Message',
        height: MONACO_INPUT_HEIGHT_TALL,
      },
      {
        name: 'msteams_image_url_template',
        label: 'Image',
        height: MONACO_INPUT_HEIGHT_SMALL,
      },
    ],
  },
  {
    name: 'Mattermost',
    contents: [
      {
        name: 'mattermost_title_template',
        label: 'Title',
        height: MONACO_INPUT_HEIGHT_SMALL,
      },
      {
        name: 'mattermost_message_template',
        label: 'Message',
        height: MONACO_INPUT_HEIGHT_TALL,
      },
      {
        name: 'mattermost_image_url_template',
        label: 'Image',
        height: MONACO_INPUT_HEIGHT_SMALL,
      },
    ],
  }
];

export const getTemplatesToRender = (features?: Record<string, boolean>) => {
  const templatesToRender = cloneDeep(commonTemplatesToRender).filter(
    (template) =>
      (template.name !== 'Telegram' || features?.[AppFeature.Telegram]) &&
      (template.name !== 'Email' || features?.[AppFeature.Email]) &&
      (template.name !== 'Mobile push notifications' || features?.[AppFeature.CloudConnection])
  );

  if (features?.[AppFeature.SlackChannelCreation]) {
    const slackTemplates = templatesToRender.find((template) => template.name === 'Slack');
    if (slackTemplates) {
      slackTemplates.contents.push(
        {
          name: 'slack_create_custom_channel_template',
          label: 'Create Custom Channel',
          height: MONACO_INPUT_HEIGHT_SMALL,
        },
        {
          name: 'slack_channel_payload_template',
          label: 'Channel Payload',
          height: MONACO_INPUT_HEIGHT_TALL,
        }
      );
    }
  }

  if (features?.[AppFeature.GoogleOauth2]) {
    templatesToRender.push(additionalTemplatesToRender[0]);
  }

  if (features?.[AppFeature.MsTeams]) {
    templatesToRender.push(additionalTemplatesToRender[1]);
  }
  if (features?.[AppFeature.Mattermost]) {
    templatesToRender.push(additionalTemplatesToRender[2]);
  }
  return templatesToRender;
};
