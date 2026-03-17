import { filterAlertReceiveChannelOptions } from './IntegrationFormContainer.helpers';

describe('filterAlertReceiveChannelOptions', () => {
  test('keeps direct paging in the create-integration options', () => {
    const options = [
      {
        value: 'direct_paging',
        display_name: 'Direct paging',
      },
      {
        value: 'webhook',
        display_name: 'Webhook',
      },
      {
        value: 'legacy_alertmanager',
        display_name: 'Legacy Alertmanager',
      },
      {
        value: 'grafana_alerting',
        display_name: 'Grafana Alerting',
      },
    ] as any;

    expect(filterAlertReceiveChannelOptions(options, '', true, true)).toEqual([
      {
        value: 'direct_paging',
        display_name: 'Direct paging',
      },
      {
        value: 'webhook',
        display_name: 'Webhook',
      },
      {
        value: 'grafana_alerting',
        display_name: 'Grafana Alerting',
      },
    ]);
  });

  test('still excludes grafana alerting when unified alerting is disabled', () => {
    const options = [
      {
        value: 'grafana_alerting',
        display_name: 'Grafana Alerting',
      },
      {
        value: 'direct_paging',
        display_name: 'Direct paging',
      },
    ] as any;

    expect(filterAlertReceiveChannelOptions(options, '', false, true)).toEqual([
      {
        value: 'direct_paging',
        display_name: 'Direct paging',
      },
    ]);
  });

  test('excludes direct paging when direct paging creation feature is disabled', () => {
    const options = [
      {
        value: 'direct_paging',
        display_name: 'Direct paging',
      },
      {
        value: 'webhook',
        display_name: 'Webhook',
      },
    ] as any;

    expect(filterAlertReceiveChannelOptions(options, '', true, false)).toEqual([
      {
        value: 'webhook',
        display_name: 'Webhook',
      },
    ]);
  });
});
