import { DataSourceRef } from '@grafana/schema';

export interface InsightsConfig {
  allowDatasourceSelection: boolean;
  datasource: DataSourceRef;
  stack: string;
}
