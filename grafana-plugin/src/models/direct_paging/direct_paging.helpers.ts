import { ApiSchemas } from 'network/oncall-api/api.types';

export type DirectPagingAlertGroupStaticLabel =
  NonNullable<ApiSchemas['AlertReceiveChannel']['alert_group_labels']>['custom'][number];
export type DirectPagingDynamicLabel = DirectPagingAlertGroupStaticLabel['key'];
export type DirectPagingIntegrationLabel = NonNullable<ApiSchemas['AlertReceiveChannel']['labels']>[number];

export type DirectPagingTeamLabels = {
  integrationLabels: DirectPagingIntegrationLabel[];
  alertGroupStaticLabels: DirectPagingAlertGroupStaticLabel[];
  dynamicLabels: DirectPagingDynamicLabel[];
};

export const getDirectPagingTeamLabels = (
  integration?: ApiSchemas['AlertReceiveChannel']
): DirectPagingTeamLabels => {
  const customLabels = integration?.alert_group_labels?.custom || [];

  return {
    integrationLabels: integration?.labels || [],
    alertGroupStaticLabels: customLabels.filter((label) => label.value.id !== null),
    dynamicLabels: customLabels.filter((label) => label.value.id === null).map((label) => label.key),
  };
};
