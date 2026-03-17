import React from 'react';

import { css } from '@emotion/css';
import { Alert, Button, Stack, useStyles2 } from '@grafana/ui';
import { UserActions } from 'helpers/authorization/authorization';
import { LocationHelper } from 'helpers/LocationHelper';
import { useQueryParams } from 'helpers/hooks';
import { onCallApi } from 'network/oncall-api/http-client';

import { Text } from 'components/Text/Text';
import { WithConfirm } from 'components/WithConfirm/WithConfirm';
import { StackSize } from 'helpers/consts';
import { LegacyNavHeading } from 'navbar/LegacyNavHeading';
import { useStore } from 'state/useStore';
import { WithPermissionControlTooltip } from 'containers/WithPermissionControl/WithPermissionControlTooltip';

enum GoogleError {
  MISSING_GRANTED_SCOPE = 'missing_granted_scope',
  MISSING_REFRESH_TOKEN = 'missing_refresh_token',
}

function getGoogleErrorMessage(googleError: GoogleError) {
  if (googleError === GoogleError.MISSING_GRANTED_SCOPE) {
    return 'Google Calendar could not be connected because the required Calendar permissions were not granted.';
  }

  if (googleError === GoogleError.MISSING_REFRESH_TOKEN) {
    return 'Google Calendar could not be connected because Google did not return a refresh token.';
  }

  return 'Google Calendar could not be connected.';
}

export const GoogleCalendarSettings = () => {
  const styles = useStyles2(getStyles);
  const queryParams = useQueryParams();
  const { organizationStore } = useStore();
  const organization = organizationStore.currentOrganization;

  const googleError = queryParams.get('google_error') as GoogleError | null;

  const handleConnect = async () => {
    const { data } = await onCallApi().GET('/login/{backend}', { params: { path: { backend: 'google-oauth2-org' } } });
    window.location = data;
  };

  const handleDisconnect = async () => {
    await onCallApi().GET('/disconnect/{backend}', { params: { path: { backend: 'google-oauth2-org' } } });
    await organizationStore.loadCurrentOrganization();
  };

  const handleDismissError = () => {
    LocationHelper.update({ google_error: undefined }, 'partial');
  };

  return (
    <div>
      <LegacyNavHeading>
        <Text.Title level={3} className={styles.title}>
          Google Calendar
        </Text.Title>
      </LegacyNavHeading>

      {googleError && (
        <Alert title="Google integration error" severity="error" onRemove={handleDismissError} className={styles.alert}>
          {getGoogleErrorMessage(googleError)}
        </Alert>
      )}

      <div className={styles.card}>
        <Stack direction="column" gap={StackSize.lg}>
          <Text.Title level={4}>Organization Google account</Text.Title>
          <Text type="secondary">
            Connect a Google account once for this OnCall organization. This admin-managed connection is used for
            creating Google Calendar events and Meet links. It does not change the existing per-user Google Calendar
            settings under profile pages.
          </Text>

          {organization?.has_google_oauth2_organization_connected ? (
            <>
              <Text>
                Connected account: <strong>{organization.google_oauth2_organization_email || 'Google account connected'}</strong>
              </Text>
              <WithPermissionControlTooltip userAction={UserActions.OtherSettingsWrite}>
                <WithConfirm title="Disconnect the organization Google account?" confirmText="Disconnect">
                  <Button variant="destructive" onClick={handleDisconnect}>
                    Disconnect
                  </Button>
                </WithConfirm>
              </WithPermissionControlTooltip>
            </>
          ) : (
            <WithPermissionControlTooltip userAction={UserActions.OtherSettingsWrite}>
              <Button variant="primary" onClick={handleConnect}>
                Connect Google account
              </Button>
            </WithPermissionControlTooltip>
          )}
        </Stack>
      </div>
    </div>
  );
};

const getStyles = () => ({
  title: css`
    margin-bottom: 20px;
  `,
  card: css`
    max-width: 720px;
  `,
  alert: css`
    margin-bottom: 16px;
  `,
});
