import React, { FC, useCallback, useEffect, useState } from 'react';

import { SelectableValue } from '@grafana/data';
import { css } from '@emotion/css';
import { Button, Drawer, Field, Input, LoadingPlaceholder, Select, Stack, TextArea, useStyles2 } from '@grafana/ui';
import { openWarningNotification } from 'helpers/helpers';
import { observer } from 'mobx-react';
import { Controller, FormProvider, useForm } from 'react-hook-form';
import { getUtilStyles } from 'styles/utils.styles';

import { AddResponders } from 'containers/AddResponders/AddResponders';
import { prepareForUpdate } from 'containers/AddResponders/AddResponders.helpers';
import { ColoredLabelTag } from 'components/ColoredLabelTag/ColoredLabelTag';
import { AlertReceiveChannelStore } from 'models/alert_receive_channel/alert_receive_channel';
import { DirectPagingTeamLabels } from 'models/direct_paging/direct_paging.helpers';
import { ApiSchemas } from 'network/oncall-api/api.types';
import { useStore } from 'state/useStore';

export type FormData = {
  message: string;
  detailed_description: string;
  dynamic_labels_map?: Record<string, string>;
};

interface ManualAlertGroupProps {
  onHide: () => void;
  onCreate: (id: ApiSchemas['AlertGroup']['pk']) => void;
  alertReceiveChannelStore: AlertReceiveChannelStore;
}

export const ManualAlertGroup: FC<ManualAlertGroupProps> = observer(({ onCreate, onHide }) => {
  const { directPagingStore, labelsStore } = useStore();
  const { selectedTeamResponder, selectedUserResponders } = directPagingStore;
  const [teamLabels, setTeamLabels] = useState<DirectPagingTeamLabels>({
    integrationLabels: [],
    alertGroupStaticLabels: [],
    dynamicLabels: [],
  });
  const [dynamicLabelOptions, setDynamicLabelOptions] = useState<Record<string, Array<SelectableValue<string>>>>({});
  const [selectedDynamicLabels, setSelectedDynamicLabels] = useState<Record<string, string>>({});
  const [teamLabelsLoading, setTeamLabelsLoading] = useState(false);

  const onHideDrawer = useCallback(() => {
    directPagingStore.resetSelectedUsers();
    directPagingStore.resetSelectedTeam();
    onHide();
  }, [onHide]);

  const formMethods = useForm<FormData>({
    mode: 'onChange',
    defaultValues: { message: '', detailed_description: '' },
  });

  const {
    handleSubmit,
    control,
    formState: { errors },
  } = formMethods;

  useEffect(() => {
    let isMounted = true;

    if (!selectedTeamResponder) {
      setTeamLabels({ integrationLabels: [], alertGroupStaticLabels: [], dynamicLabels: [] });
      setDynamicLabelOptions({});
      setSelectedDynamicLabels({});
      setTeamLabelsLoading(false);
      return undefined;
    }

    const loadTeamLabels = async () => {
      setTeamLabelsLoading(true);
      setSelectedDynamicLabels({});

      try {
        const nextTeamLabels = await directPagingStore.fetchTeamDirectPagingLabels(selectedTeamResponder.id);
        if (!isMounted || !nextTeamLabels) {
          return;
        }

        const optionEntries = await Promise.all(
          nextTeamLabels.dynamicLabels.map(async (label) => {
            const { values } = await labelsStore.loadValuesForKey(label.id);
            return [
              label.id,
              values.map((value) => ({
                label: value.name,
                value: value.name,
              })),
            ] as const;
          })
        );

        if (!isMounted) {
          return;
        }

        setTeamLabels(nextTeamLabels);
        setDynamicLabelOptions(Object.fromEntries(optionEntries));
      } catch {
        if (isMounted) {
          setTeamLabels({ integrationLabels: [], alertGroupStaticLabels: [], dynamicLabels: [] });
          setDynamicLabelOptions({});
        }
      } finally {
        if (isMounted) {
          setTeamLabelsLoading(false);
        }
      }
    };

    loadTeamLabels();

    return () => {
      isMounted = false;
    };
  }, [directPagingStore, labelsStore, selectedTeamResponder]);

  const hasPendingDynamicLabelSelections =
    selectedTeamResponder !== null &&
    teamLabels.dynamicLabels.some((label) => !selectedDynamicLabels[label.name]);
  const formIsSubmittable =
    (selectedTeamResponder !== null || selectedUserResponders.length > 0) &&
    !teamLabelsLoading &&
    !hasPendingDynamicLabelSelections;

  // TODO: add a loading state while we're waiting to hear back from the API when submitting
  // const [directPagingLoading, setdirectPagingLoading] = useState<boolean>();

  const onSubmit = async (data: FormData) => {
    const transformedData = prepareForUpdate(selectedUserResponders, selectedTeamResponder, {
      ...data,
      dynamic_labels_map: selectedDynamicLabels,
    });
    const resp = await directPagingStore.createManualAlertRule(transformedData);

    if (!resp) {
      openWarningNotification('There was an issue creating the alert group, please try again');
      return;
    }

    directPagingStore.resetSelectedUsers();
    directPagingStore.resetSelectedTeam();

    onCreate(resp.alert_group_id);
    onHide();
  };

  const utilStyles = useStyles2(getUtilStyles);
  const styles = useStyles2(getStyles);

  return (
    <Drawer scrollableContent title="New escalation" onClose={onHideDrawer} closeOnMaskClick={false} width="70%">
      <Stack direction="column">
        <FormProvider {...formMethods}>
          <form id="Manual Alert Group" onSubmit={handleSubmit(onSubmit)} className={utilStyles.width100}>
            <Controller
              name="message"
              control={control}
              rules={{
                required: 'Message is required',
                maxLength: {
                  value: 50,
                  message: 'What is going on? cannot exceed 50 characters',
                },
              }}
              render={({ field }) => (
                <Field
                  label="What is going on? (Max 50 Characters)"
                  invalid={Boolean(errors.message)}
                  error={errors.message?.message}
                >
                  <Input {...field} maxLength={50} />
                </Field>
              )}
            />

            <Controller
              name="detailed_description"
              control={control}
              render={({ field }) => (
                <Field
                  label="Detailed Description (Optional)"
                  invalid={Boolean(errors.detailed_description)}
                  error={errors.detailed_description?.message}
                >
                  <TextArea name="detailed_description" rows={6} {...field} />
                </Field>
              )}
            />

            <AddResponders mode="create" />

            {selectedTeamResponder && (
              <div className={styles.teamLabels}>
                {teamLabelsLoading ? (
                  <LoadingPlaceholder text="Loading direct paging labels..." />
                ) : (
                  <>
                    {teamLabels.integrationLabels.length > 0 && (
                      <Field label="Integration labels">
                        <div className={styles.labelList}>
                          {teamLabels.integrationLabels.map((label) => (
                            <ColoredLabelTag
                              key={`integration-label-${label.key.id}-${label.value.id}`}
                              label={label.key}
                              value={label.value}
                            />
                          ))}
                        </div>
                      </Field>
                    )}

                    {teamLabels.alertGroupStaticLabels.length > 0 && (
                      <Field label="Alert group static labels">
                        <div className={styles.labelList}>
                          {teamLabels.alertGroupStaticLabels.map((label) => (
                            <ColoredLabelTag
                              key={`static-label-${label.key.id}-${label.value.id}`}
                              label={label.key}
                              value={label.value}
                            />
                          ))}
                        </div>
                      </Field>
                    )}

                    {teamLabels.dynamicLabels.map((label) => (
                      <Field key={label.id} label={label.name}>
                        <Select
                          options={dynamicLabelOptions[label.id] || []}
                          value={
                            selectedDynamicLabels[label.name]
                              ? {
                                  label: selectedDynamicLabels[label.name],
                                  value: selectedDynamicLabels[label.name],
                                }
                              : null
                          }
                          placeholder={`Select ${label.name}`}
                          onChange={(option) => {
                            setSelectedDynamicLabels((current) => {
                              if (!option?.value) {
                                const next = { ...current };
                                delete next[label.name];
                                return next;
                              }

                              return {
                                ...current,
                                [label.name]: option.value,
                              };
                            });
                          }}
                        />
                      </Field>
                    ))}
                  </>
                )}
              </div>
            )}

            <div className={styles.buttons}>
              <Stack justifyContent="flex-end">
                <Button variant="secondary" onClick={onHideDrawer}>
                  Cancel
                </Button>
                <Button type="submit" disabled={!formIsSubmittable}>
                  Create
                </Button>
              </Stack>
            </div>
          </form>
        </FormProvider>
      </Stack>
    </Drawer>
  );
});

const getStyles = () => {
  return {
    buttons: css`
      padding-top: 12px;
    `,
    teamLabels: css`
      padding-top: 12px;
    `,
    labelList: css`
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    `,
  };
};
