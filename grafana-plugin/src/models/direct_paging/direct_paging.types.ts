export type ManualAlertGroupPayload = {
  message?: string;
  detailed_description?: string;
  team: string | null;
  users: Array<{ id: string; important: boolean }>;
  dynamic_labels_map?: Record<string, string>;
};
