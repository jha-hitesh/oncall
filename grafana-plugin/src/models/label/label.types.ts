import { ApiSchemas } from 'network/oncall-api/api.types';

export interface LabelKeyValue {
  key: ApiSchemas['LabelKey'];
  value: ApiSchemas['LabelValue'];
}

export type LabelKeyWithStats = ApiSchemas['LabelKey'] & {
  values_count?: number;
};

export type LabelsErrors = Array<{ key?: { id: string[]; name: string[] }; value?: { id: string[]; name: string[] } }>;
