import { ApiSchemas } from 'network/oncall-api/api.types';

export function filterAlertReceiveChannelOptions(
  alertReceiveChannelOptions: Array<ApiSchemas['AlertReceiveChannelIntegrationOptions']>,
  filterValue: string,
  unifiedAlertingEnabled: boolean,
  allowDirectPagingCreation: boolean
): Array<ApiSchemas['AlertReceiveChannelIntegrationOptions']> {
  return alertReceiveChannelOptions.filter((option: ApiSchemas['AlertReceiveChannelIntegrationOptions']) => {
    if (option.value === 'grafana_alerting' && !unifiedAlertingEnabled) {
      return false;
    }

    if (option.value === 'direct_paging' && !allowDirectPagingCreation) {
      return false;
    }

    return (
      option.display_name.toLowerCase().includes(filterValue.toLowerCase()) &&
      !option.value.toLowerCase().startsWith('legacy_')
    );
  });
}
