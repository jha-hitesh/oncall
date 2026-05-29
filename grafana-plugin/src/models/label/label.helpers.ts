import { ApiSchemas } from 'network/oncall-api/api.types';

export interface SplitGroupsResult {
  name: string;
  id: string;
  expanded: boolean;
  options: Array<ApiSchemas['LabelKey']> | Array<ApiSchemas['LabelValue']>;
}

export const splitToGroups = <T extends ApiSchemas['LabelKey'] | ApiSchemas['LabelValue']>(labels: T[] = []) => {
  return labels.reduce<SplitGroupsResult[]>(
    (memo, option) => {
      const group = memo.find(({ name }) => name === (option.prescribed ? 'System' : 'User added'));
      group?.options.push(option as ApiSchemas['LabelKey'] & ApiSchemas['LabelValue']);

      return memo;
    },
    [
      { name: 'System', id: 'system', expanded: true, options: [] },
      { name: 'User added', id: 'user_added', expanded: true, options: [] },
    ] as SplitGroupsResult[]
  );
};
