import { getTemplatesForEdit } from 'components/AlertTemplates/AlertTemplatesForm.config';
import { AppFeature } from 'state/features';

import { getTemplatesToRender } from './IntegrationTemplatesList.config';

describe('getTemplatesToRender', () => {
  it('hides telegram templates when telegram feature is disabled', () => {
    const templates = getTemplatesToRender({});

    expect(templates.find((template) => template.name === 'Telegram')).toBeUndefined();
  });

  it('shows telegram templates when telegram feature is enabled', () => {
    const templates = getTemplatesToRender({ [AppFeature.Telegram]: true });

    expect(templates.find((template) => template.name === 'Telegram')).toBeDefined();
  });

  it('hides mobile push templates when cloud connection is disabled', () => {
    const templates = getTemplatesToRender({});

    expect(templates.find((template) => template.name === 'Mobile push notifications')).toBeUndefined();
  });

  it('shows mobile push templates when cloud connection is enabled', () => {
    const templates = getTemplatesToRender({ [AppFeature.CloudConnection]: true });

    expect(templates.find((template) => template.name === 'Mobile push notifications')).toBeDefined();
  });
});

describe('getTemplatesForEdit', () => {
  it('removes telegram template editors when telegram feature is disabled', () => {
    const templates = getTemplatesForEdit({});

    expect(templates.telegram_title_template).toBeUndefined();
    expect(templates.telegram_message_template).toBeUndefined();
    expect(templates.telegram_image_url_template).toBeUndefined();
  });

  it('keeps telegram template editors when telegram feature is enabled', () => {
    const templates = getTemplatesForEdit({ [AppFeature.Telegram]: true });

    expect(templates.telegram_title_template).toBeDefined();
    expect(templates.telegram_message_template).toBeDefined();
    expect(templates.telegram_image_url_template).toBeDefined();
  });

  it('removes mobile push template editors when cloud connection is disabled', () => {
    const templates = getTemplatesForEdit({});

    expect(templates.mobile_app_title_template).toBeUndefined();
    expect(templates.mobile_app_message_template).toBeUndefined();
  });

  it('keeps mobile push template editors when cloud connection is enabled', () => {
    const templates = getTemplatesForEdit({ [AppFeature.CloudConnection]: true });

    expect(templates.mobile_app_title_template).toBeDefined();
    expect(templates.mobile_app_message_template).toBeDefined();
  });
});
