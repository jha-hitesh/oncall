export type OutgoingTabDrawerKey = 'webhookDetails' | 'newOutgoingWebhook';

export const TriggerDetailsQueryStringKey = {
  ActiveTab: 'activeEventTriggerDrawerTab',
  WebhookId: 'webhookId',
};

export const TriggerDetailsTab = {
  Settings: 'Settings',
  LastEvent: 'Last event',
} as const;
export type TriggerDetailsTab = (typeof TriggerDetailsTab)[keyof typeof TriggerDetailsTab];

export interface OutgoingTabFormValues {
  // Backend fields
  trigger_type: string;
  is_webhook_enabled?: boolean;
  url: string;
  http_method: string;
  data?: string;
  trigger_template?: string;
  add_response_to_timeline?: boolean;
  response_template?: string;

  // For UI only
  triggerTemplateToogle?: boolean;
}
