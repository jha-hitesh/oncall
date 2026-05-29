import { SlackChannel } from 'models/slack_channel/slack_channel.types';

export interface Organization {
  pk: string;
  banner: {
    title: string;
    body: string;
  };
  telegram_configuration: {
    channel_chat_id: string;
    channel_name: string;
    discussion_group_chat_id: string;
    discussion_group_name: string;
  };
  name: string;
  stack_slug: string;
  slack_team_identity: {
    cached_name: string;
    needs_reinstall: boolean;
  };
  slack_channel: SlackChannel | null;
  rbac_enabled: boolean;
  grafana_incident_enabled: boolean;
  grafana_irm_enabled: boolean;
  schedule_management_require_admin: boolean;
  direct_paging_prefer_important_policy: boolean;
  is_resolution_note_required: boolean;
  env_status: {
    telegram_configured: boolean;
    phone_provider: {
      configured: boolean;
      test_call: boolean;
      test_sms: boolean;
      verification_call: boolean;
      verification_sms: boolean;
    };
    mattermost_configured: boolean;
  };
  has_google_oauth2_organization_connected: boolean;
  google_oauth2_organization_email: string | null;
}
