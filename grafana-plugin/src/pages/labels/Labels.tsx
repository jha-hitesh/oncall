import React, { FormEvent, useCallback, useEffect, useMemo, useState } from 'react';

import { css, cx } from '@emotion/css';
import { GrafanaTheme2 } from '@grafana/data';
import {
  Alert,
  Button,
  ConfirmModal,
  Field,
  Input,
  LoadingPlaceholder,
  Stack,
  Switch,
  Tab,
  TabContent,
  TabsBar,
  useStyles2,
} from '@grafana/ui';
import { UserActions, isUserActionAllowed } from 'helpers/authorization/authorization';
import { observer } from 'mobx-react';

import { HamburgerContextMenu } from 'components/HamburgerContextMenu/HamburgerContextMenu';
import { Text } from 'components/Text/Text';
import { GSelect } from 'containers/GSelect/GSelect';
import { LabelKeyWithStats } from 'models/label/label.types';
import { ApiSchemas } from 'network/oncall-api/api.types';
import { AppFeature } from 'state/features';
import { useStore } from 'state/useStore';

enum LabelsTab {
  Keys = 'keys',
  Values = 'values',
}

interface ValueRow {
  key: ApiSchemas['LabelKey'];
  value: ApiSchemas['LabelValue'];
}

interface ConfirmationState {
  title: string;
  body: string;
  confirmText: string;
  onConfirm: () => Promise<void>;
}

const normalizeHexColor = (value: string | undefined, fallbackColor = '#42f566') =>
  /^#[0-9A-Fa-f]{6}$/.test(value || '') ? value! : fallbackColor;

const getTagTextColor = (color: string) => {
  const normalized = normalizeHexColor(color).slice(1);
  const red = Number.parseInt(normalized.slice(0, 2), 16);
  const green = Number.parseInt(normalized.slice(2, 4), 16);
  const blue = Number.parseInt(normalized.slice(4, 6), 16);
  const brightness = (red * 299 + green * 587 + blue * 114) / 1000;

  return brightness > 160 ? '#111827' : '#ffffff';
};

const getTagSegmentStyle = (color: string, isLeading: boolean, isTrailing: boolean): React.CSSProperties => ({
  background: normalizeHexColor(color),
  color: getTagTextColor(color),
  borderRadius: isLeading ? '5px 0 0 5px' : isTrailing ? '0 5px 5px 0' : 0,
});

const ColorPickerField = ({
  className,
  fallbackColor,
  label,
  value,
  onChange,
}: {
  className?: string;
  fallbackColor: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
}) => {
  const normalizedValue = normalizeHexColor(value, fallbackColor);

  return (
    <label className={className}>
      <span>{label}</span>
      <input type="color" value={normalizedValue} onChange={(event) => onChange(event.currentTarget.value)} />
      <span>{normalizedValue}</span>
    </label>
  );
};

const SingleTag = ({ className, color, children }: { className?: string; color: string; children: React.ReactNode }) => (
  <span className={className} style={getTagSegmentStyle(color, true, true)}>
    {children}
  </span>
);

const PairTag = ({
  className,
  keyColor,
  keyName,
  valueColor,
  valueName,
}: {
  className?: string;
  keyColor: string;
  keyName: string;
  valueColor: string;
  valueName: string;
}) => (
  <span className={className}>
    <span style={getTagSegmentStyle(keyColor, true, false)}>{keyName}</span>
    <span style={getTagSegmentStyle(valueColor, false, true)}>{valueName}</span>
  </span>
);

export const LabelsPage = observer(() => {
  const styles = useStyles2(getStyles);
  const { hasFeature, labelKeyDefaultColor, labelValueDefaultColor, labelsStore, setPageTitle } = useStore();

  const canManageLabels = isUserActionAllowed(UserActions.OnCallAdmin);

  const [activeTab, setActiveTab] = useState<LabelsTab>(LabelsTab.Keys);
  const [keySearch, setKeySearch] = useState('');
  const [valueSearch, setValueSearch] = useState('');
  const [newKeyName, setNewKeyName] = useState('');
  const [newKeyColorCode, setNewKeyColorCode] = useState(labelKeyDefaultColor);
  const [newKeyIsManaged, setNewKeyIsManaged] = useState(false);
  const [newValueName, setNewValueName] = useState('');
  const [newValueColorCode, setNewValueColorCode] = useState(labelValueDefaultColor);
  const [editingKeyId, setEditingKeyId] = useState<string>();
  const [editingKeyName, setEditingKeyName] = useState('');
  const [editingKeyColorCode, setEditingKeyColorCode] = useState(labelKeyDefaultColor);
  const [editingKeyIsManaged, setEditingKeyIsManaged] = useState(false);
  const [editingValueId, setEditingValueId] = useState<string>();
  const [editingValueName, setEditingValueName] = useState('');
  const [editingValueColorCode, setEditingValueColorCode] = useState(labelValueDefaultColor);
  const [selectedValueKeyIds, setSelectedValueKeyIds] = useState<string[]>([]);
  const [keys, setKeys] = useState<LabelKeyWithStats[]>([]);
  const [valueOptions, setValueOptions] = useState<Array<{ key: ApiSchemas['LabelKey']; values: Array<ApiSchemas['LabelValue']> }>>(
    []
  );
  const [isKeysLoading, setIsKeysLoading] = useState(true);
  const [isValuesLoading, setIsValuesLoading] = useState(false);
  const [confirmation, setConfirmation] = useState<ConfirmationState>();

  const loadKeys = useCallback(async () => {
    setIsKeysLoading(true);

    try {
      const items = await labelsStore.loadKeys();
      setKeys(items);
    } finally {
      setIsKeysLoading(false);
    }
  }, [labelsStore]);

  const keyItems = useMemo(
    () =>
      keys.reduce<Record<string, LabelKeyWithStats>>((result, item) => {
        result[item.id] = item;
        return result;
      }, {}),
    [keys]
  );

  const filteredKeys = useMemo(() => {
    const normalizedSearch = keySearch.trim().toLowerCase();

    return keys.filter((key) => key.name.toLowerCase().includes(normalizedSearch));
  }, [keySearch, keys]);

  const selectedValueKeys = useMemo(
    () => selectedValueKeyIds.map((keyId) => keyItems[keyId]).filter(Boolean),
    [keyItems, selectedValueKeyIds]
  );

  const addValueKey = selectedValueKeyIds.length === 1 ? keyItems[selectedValueKeyIds[0]] : undefined;

  const filteredValueRows = useMemo(() => {
    const normalizedSearch = valueSearch.trim().toLowerCase();

    return valueOptions.flatMap((option) =>
      option.values
        .filter((value) => value.name.toLowerCase().includes(normalizedSearch))
        .map((value) => ({ key: option.key, value }))
    );
  }, [valueOptions, valueSearch]);

  const loadValues = useCallback(async () => {
    const ids = selectedValueKeyIds.length ? selectedValueKeyIds : keys.map((key) => key.id);

    if (!ids.length) {
      setValueOptions([]);
      return;
    }

    setIsValuesLoading(true);

    try {
      const items = await Promise.all(ids.map((keyId) => labelsStore.loadValuesForKey(keyId)));
      setValueOptions(items);
    } finally {
      setIsValuesLoading(false);
    }
  }, [keys, labelsStore, selectedValueKeyIds]);

  useEffect(() => {
    setPageTitle('Labels');

    return () => {
      setPageTitle('');
    };
  }, [setPageTitle]);

  useEffect(() => {
    if (!hasFeature(AppFeature.Labels)) {
      setIsKeysLoading(false);
      return;
    }

    loadKeys();
  }, [hasFeature, loadKeys]);

  useEffect(() => {
    setSelectedValueKeyIds((currentIds) => currentIds.filter((id) => Boolean(keyItems[id])));
  }, [keyItems]);

  useEffect(() => {
    if (!hasFeature(AppFeature.Labels)) {
      return;
    }

    loadValues();
  }, [hasFeature, loadValues]);

  useEffect(() => {
    setNewKeyColorCode(labelKeyDefaultColor);
  }, [labelKeyDefaultColor]);

  useEffect(() => {
    setNewValueColorCode(labelValueDefaultColor);
  }, [labelValueDefaultColor]);

  const resetEditingState = () => {
    setEditingKeyId(undefined);
    setEditingKeyName('');
    setEditingKeyColorCode(labelKeyDefaultColor);
    setEditingKeyIsManaged(false);
    setEditingValueId(undefined);
    setEditingValueName('');
    setEditingValueColorCode(labelValueDefaultColor);
  };

  const onCreateKey = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    const trimmedName = newKeyName.trim();
    if (!trimmedName) {
      return;
    }

    await labelsStore.createKey(trimmedName, newKeyIsManaged, normalizeHexColor(newKeyColorCode, labelKeyDefaultColor));
    setNewKeyName('');
    setNewKeyColorCode(labelKeyDefaultColor);
    setNewKeyIsManaged(false);
    await loadKeys();
  };

  const onCreateValue = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (!addValueKey) {
      return;
    }

    const trimmedName = newValueName.trim();
    if (!trimmedName) {
      return;
    }

    await labelsStore.createValue(addValueKey.id, trimmedName, normalizeHexColor(newValueColorCode, labelValueDefaultColor));
    setNewValueName('');
    setNewValueColorCode(labelValueDefaultColor);
    await loadKeys();
  };

  const onRenameKey = async (keyId: string) => {
    const trimmedName = editingKeyName.trim();
    if (!trimmedName) {
      return;
    }

    await labelsStore.updateKey(
      keyId,
      trimmedName,
      editingKeyIsManaged,
      normalizeHexColor(editingKeyColorCode, labelKeyDefaultColor)
    );
    resetEditingState();
    await loadKeys();
  };

  const onRenameValue = async (keyId: string, valueId: string) => {
    const trimmedName = editingValueName.trim();
    if (!trimmedName) {
      return;
    }

    await labelsStore.updateKeyValue(
      keyId,
      valueId,
      trimmedName,
      normalizeHexColor(editingValueColorCode, labelValueDefaultColor)
    );
    resetEditingState();
    await loadKeys();
  };

  const openDeleteKeyModal = (key: LabelKeyWithStats) => {
    setConfirmation({
      title: 'Delete key',
      body: `Delete "${key.name}" and all of its values? This also removes existing associations using this key.`,
      confirmText: 'Delete key',
      onConfirm: async () => {
        await labelsStore.deleteKey(key.id);
        setKeys((currentKeys) => currentKeys.filter((currentKey) => currentKey.id !== key.id));
        setValueOptions((currentOptions) => currentOptions.filter((option) => option.key.id !== key.id));
        setSelectedValueKeyIds((currentIds) => currentIds.filter((id) => id !== key.id));
        resetEditingState();
        await loadKeys();
      },
    });
  };

  const openDeleteValueModal = (row: ValueRow) => {
    setConfirmation({
      title: 'Delete value',
      body: `Delete "${row.value.name}" from "${row.key.name}"? This also removes existing associations using this value.`,
      confirmText: 'Delete value',
      onConfirm: async () => {
        await labelsStore.deleteKeyValue(row.key.id, row.value.id);
        resetEditingState();
        await loadKeys();
      },
    });
  };

  const startKeyEdit = (key: LabelKeyWithStats) => {
    setEditingValueId(undefined);
    setEditingValueName('');
    setEditingValueColorCode(labelValueDefaultColor);
    setEditingKeyId(key.id);
    setEditingKeyName(key.name);
    setEditingKeyColorCode(normalizeHexColor(key.color_code, labelKeyDefaultColor));
    setEditingKeyIsManaged(Boolean(key.is_managed_label));
  };

  const startValueEdit = (row: ValueRow) => {
    setEditingKeyId(undefined);
    setEditingKeyName('');
    setEditingKeyColorCode(labelKeyDefaultColor);
    setEditingValueId(row.value.id);
    setEditingValueName(row.value.name);
    setEditingValueColorCode(normalizeHexColor(row.value.color_code, labelValueDefaultColor));
  };

  const onKeyRowClick = (key: LabelKeyWithStats) => {
    resetEditingState();
    setSelectedValueKeyIds([key.id]);
    setActiveTab(LabelsTab.Values);
  };

  if (!hasFeature(AppFeature.Labels)) {
    return (
      <div className={styles.page}>
        <Alert title="Labels are not enabled for this organization." severity="info" />
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <Text type="secondary">Manage label keys and values for the OnCall plugin.</Text>
      </div>

      <div className={styles.surface}>
        <TabsBar>
          <Tab label="Keys" active={activeTab === LabelsTab.Keys} onChangeTab={() => setActiveTab(LabelsTab.Keys)} />
          <Tab
            label="Values"
            active={activeTab === LabelsTab.Values}
            onChangeTab={() => setActiveTab(LabelsTab.Values)}
          />
        </TabsBar>

        <TabContent className={styles.tabContent}>
          {activeTab === LabelsTab.Keys && (
            <section className={styles.section}>
              <Stack justifyContent="space-between" alignItems="center">
                <div>
                  <Text.Title level={5}>Keys</Text.Title>
                  <Text type="secondary">{filteredKeys.length} matching keys</Text>
                </div>
              </Stack>

              <div className={styles.toolbar}>
                <Input
                  value={keySearch}
                  onChange={(event) => setKeySearch(event.currentTarget.value)}
                  placeholder="Search keys by name"
                />
              </div>

              {canManageLabels && (
                <form className={styles.keyForm} onSubmit={onCreateKey}>
                  <Input
                    value={newKeyName}
                    onChange={(event) => setNewKeyName(event.currentTarget.value)}
                    placeholder="Add key"
                  />
                  <ColorPickerField
                    className={styles.colorPickerField}
                    label="Color"
                    fallbackColor={labelKeyDefaultColor}
                    value={newKeyColorCode}
                    onChange={setNewKeyColorCode}
                  />
                  <Field className={styles.switchField} label="Managed">
                    <Switch value={newKeyIsManaged} onChange={() => setNewKeyIsManaged((current) => !current)} />
                  </Field>
                  <Button type="submit" variant="primary">
                    Add key
                  </Button>
                </form>
              )}

              <div className={cx(styles.table, styles.keyTable)}>
                <div className={cx(styles.headerRow, styles.keyRowLayout)}>
                  <span>Key</span>
                  <span>Managed</span>
                  <span>Values</span>
                  <span className={styles.menuColumn} />
                </div>

                {isKeysLoading ? (
                  <div className={styles.loadingState}>
                    <LoadingPlaceholder text="Loading keys..." />
                  </div>
                ) : filteredKeys.length ? (
                  filteredKeys.map((key) => {
                    const isEditing = editingKeyId === key.id;
                    const valuesCount = key.values_count || 0;

                    return (
                      <div key={key.id} className={cx(styles.bodyRow, styles.keyRowLayout)}>
                        {isEditing ? (
                          <>
                            <div className={styles.editCell}>
                              <Input
                                value={editingKeyName}
                                onChange={(event) => setEditingKeyName(event.currentTarget.value)}
                                placeholder="Key name"
                              />
                              <ColorPickerField
                                className={styles.colorPickerField}
                                label="Color"
                                fallbackColor={labelKeyDefaultColor}
                                value={editingKeyColorCode}
                                onChange={setEditingKeyColorCode}
                              />
                            </div>
                            <div className={styles.switchCell}>
                              <Switch
                                value={editingKeyIsManaged}
                                onChange={() => setEditingKeyIsManaged((current) => !current)}
                              />
                            </div>
                            <span className={styles.countCell}>{valuesCount}</span>
                            <div className={styles.rowActions}>
                              <Button size="sm" variant="secondary" onClick={() => onRenameKey(key.id)}>
                                Save
                              </Button>
                              <Button size="sm" variant="secondary" fill="outline" onClick={resetEditingState}>
                                Cancel
                              </Button>
                            </div>
                          </>
                        ) : (
                          <>
                            <button type="button" className={styles.linkCell} onClick={() => onKeyRowClick(key)}>
                              <SingleTag className={styles.singleTag} color={key.color_code}>
                                {key.name}
                              </SingleTag>
                            </button>
                            <span className={styles.secondaryText}>
                              {key.is_managed_label ? 'Managed' : 'Not managed'}
                            </span>
                            <span className={styles.countCell}>{valuesCount}</span>
                            <div className={styles.rowMenu}>
                              {canManageLabels && !key.prescribed && (
                                <HamburgerContextMenu
                                  items={[
                                    { label: 'Edit', onClick: () => startKeyEdit(key) },
                                    'divider',
                                    { label: 'Delete', onClick: () => openDeleteKeyModal(key) },
                                  ]}
                                />
                              )}
                            </div>
                          </>
                        )}
                      </div>
                    );
                  })
                ) : (
                  <div className={styles.emptyTableState}>
                    <Text type="secondary">No label keys found.</Text>
                  </div>
                )}
              </div>
            </section>
          )}

          {activeTab === LabelsTab.Values && (
            <section className={styles.section}>
              <Stack justifyContent="space-between" alignItems="center">
                <div>
                  <Text.Title level={5}>Values</Text.Title>
                  <Text type="secondary">{filteredValueRows.length} matching values</Text>
                </div>
              </Stack>

              <div className={styles.filters}>
                <Input
                  value={valueSearch}
                  onChange={(event) => setValueSearch(event.currentTarget.value)}
                  placeholder="Search values by name"
                />
                <GSelect
                  items={keyItems}
                  fetchItemsFn={async () => keys}
                  fetchItemFn={async (id: string) => keyItems[id]}
                  getSearchResult={(query?: string) =>
                    keys.filter((key) => key.name.toLowerCase().includes((query || '').toLowerCase()))
                  }
                  onChange={(value) => setSelectedValueKeyIds(Array.isArray(value) ? value : [])}
                  placeholder="Filter by keys"
                  displayField="name"
                  value={selectedValueKeyIds}
                  isMulti
                />
              </div>

              {canManageLabels && (
                <>
                  <form className={styles.inlineForm} onSubmit={onCreateValue}>
                    <Input
                      value={newValueName}
                      onChange={(event) => setNewValueName(event.currentTarget.value)}
                      placeholder={addValueKey ? `Add value to ${addValueKey.name}` : 'Select exactly one key to add a value'}
                      disabled={!addValueKey}
                    />
                    <ColorPickerField
                      className={styles.colorPickerField}
                      label="Color"
                      fallbackColor={labelValueDefaultColor}
                      value={newValueColorCode}
                      onChange={setNewValueColorCode}
                    />
                    <Button type="submit" variant="primary" disabled={!addValueKey}>
                      Add value
                    </Button>
                  </form>
                  {!addValueKey && (
                    <Text type="secondary">Select exactly one key in the filter to create a value.</Text>
                  )}
                </>
              )}

              {selectedValueKeys.length > 0 && (
                <Text type="secondary">
                  Filtering by: {selectedValueKeys.map((key) => key.name).join(', ')}
                </Text>
              )}

              <div className={styles.table}>
                <div className={cx(styles.headerRow, styles.valueRowLayout)}>
                  <span>Value</span>
                  <span className={styles.menuColumn} />
                </div>

                {isValuesLoading ? (
                  <div className={styles.loadingState}>
                    <LoadingPlaceholder text="Loading values..." />
                  </div>
                ) : filteredValueRows.length ? (
                  filteredValueRows.map((row) => {
                    const isEditing = editingValueId === row.value.id;

                    return (
                      <div key={row.value.id} className={cx(styles.bodyRow, styles.valueRowLayout)}>
                        {isEditing ? (
                          <>
                            <div className={styles.editCell}>
                              <Input
                                value={editingValueName}
                                onChange={(event) => setEditingValueName(event.currentTarget.value)}
                                placeholder="Value name"
                              />
                              <ColorPickerField
                                className={styles.colorPickerField}
                                label="Color"
                                fallbackColor={labelValueDefaultColor}
                                value={editingValueColorCode}
                                onChange={setEditingValueColorCode}
                              />
                            </div>
                            <div className={styles.rowActions}>
                              <Button size="sm" variant="secondary" onClick={() => onRenameValue(row.key.id, row.value.id)}>
                                Save
                              </Button>
                              <Button size="sm" variant="secondary" fill="outline" onClick={resetEditingState}>
                                Cancel
                              </Button>
                            </div>
                          </>
                        ) : (
                          <>
                            <PairTag
                              className={styles.pairTag}
                              keyColor={row.key.color_code}
                              keyName={row.key.name}
                              valueColor={row.value.color_code}
                              valueName={row.value.name}
                            />
                            <div className={styles.rowMenu}>
                              {canManageLabels && !row.value.prescribed && !row.key.prescribed && (
                                <HamburgerContextMenu
                                  items={[
                                    { label: 'Edit', onClick: () => startValueEdit(row) },
                                    'divider',
                                    { label: 'Delete', onClick: () => openDeleteValueModal(row) },
                                  ]}
                                />
                              )}
                            </div>
                          </>
                        )}
                      </div>
                    );
                  })
                ) : (
                  <div className={styles.emptyTableState}>
                    <Text type="secondary">No values match the current search and key filters.</Text>
                  </div>
                )}
              </div>
            </section>
          )}
        </TabContent>
      </div>

      {confirmation && (
        <ConfirmModal
          isOpen
          title={confirmation.title}
          body={confirmation.body}
          confirmText={confirmation.confirmText}
          dismissText="Cancel"
          onDismiss={() => setConfirmation(undefined)}
          onConfirm={async () => {
            await confirmation.onConfirm();
            setConfirmation(undefined);
          }}
        />
      )}
    </div>
  );
});

const getStyles = (theme: GrafanaTheme2) => ({
  page: css`
    display: flex;
    flex-direction: column;
    gap: ${theme.spacing(3)};
    padding-bottom: ${theme.spacing(3)};
  `,
  header: css`
    display: flex;
    flex-direction: column;
    gap: ${theme.spacing(1)};
  `,
  surface: css`
    border: 1px solid ${theme.colors.border.medium};
    border-radius: ${theme.shape.radius.default};
    background: ${theme.colors.background.primary};
    overflow: hidden;
  `,
  tabContent: css`
    margin-top: 0;
  `,
  section: css`
    display: flex;
    flex-direction: column;
    gap: ${theme.spacing(2)};
    padding: ${theme.spacing(3)};
  `,
  toolbar: css`
    display: grid;
    grid-template-columns: minmax(0, 360px);
    gap: ${theme.spacing(2)};
  `,
  filters: css`
    display: grid;
    grid-template-columns: minmax(0, 360px) minmax(220px, 320px);
    gap: ${theme.spacing(2)};

    @media (max-width: 900px) {
      grid-template-columns: 1fr;
    }
  `,
  inlineForm: css`
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto auto;
    gap: ${theme.spacing(1)};
    align-items: end;

    @media (max-width: 900px) {
      grid-template-columns: 1fr;
    }
  `,
  keyForm: css`
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto auto auto;
    gap: ${theme.spacing(1)};
    align-items: end;

    @media (max-width: 1100px) {
      grid-template-columns: 1fr;
    }
  `,
  table: css`
    border: 1px solid ${theme.colors.border.weak};
    border-radius: ${theme.shape.radius.default};
    overflow: hidden;
  `,
  keyTable: css`
    min-height: 320px;
  `,
  headerRow: css`
    display: grid;
    gap: ${theme.spacing(2)};
    align-items: center;
    padding: ${theme.spacing(1.5)} ${theme.spacing(2)};
    background: ${theme.colors.background.secondary};
    color: ${theme.colors.text.secondary};
    font-weight: ${theme.typography.fontWeightMedium};
  `,
  bodyRow: css`
    display: grid;
    gap: ${theme.spacing(2)};
    align-items: center;
    padding: ${theme.spacing(1.5)} ${theme.spacing(2)};
    border-top: 1px solid ${theme.colors.border.weak};
    min-height: 72px;
  `,
  keyRowLayout: css`
    grid-template-columns: minmax(0, 1fr) 120px 120px auto;

    @media (max-width: 1100px) {
      grid-template-columns: 1fr;
    }
  `,
  valueRowLayout: css`
    grid-template-columns: minmax(0, 1fr) auto;

    @media (max-width: 1100px) {
      grid-template-columns: 1fr;
    }
  `,
  linkCell: css`
    display: flex;
    align-items: center;
    min-width: 0;
    padding: 0;
    border: 0;
    background: transparent;
    cursor: pointer;
    text-align: left;

    &:hover {
      opacity: 0.92;
    }
  `,
  editCell: css`
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: ${theme.spacing(1)};
    align-items: center;

    @media (max-width: 700px) {
      grid-template-columns: 1fr;
    }
  `,
  colorPickerField: css`
    display: inline-flex;
    align-items: center;
    gap: ${theme.spacing(1)};
    min-height: 32px;
    padding: 0 ${theme.spacing(1.25)};
    border: 1px solid ${theme.colors.border.medium};
    border-radius: ${theme.shape.radius.default};
    background: ${theme.colors.background.secondary};
    color: ${theme.colors.text.secondary};
    font-size: ${theme.typography.bodySmall.fontSize};
    white-space: nowrap;

    input {
      width: 28px;
      height: 28px;
      padding: 0;
      border: 0;
      background: transparent;
      cursor: pointer;
    }

    span:last-child {
      font-family: ${theme.typography.fontFamilyMonospace};
      color: ${theme.colors.text.primary};
    }
  `,
  singleTag: css`
    display: inline-flex;
    align-items: center;
    min-width: 0;
    max-width: 100%;
    padding: ${theme.spacing(0.5)} ${theme.spacing(1.25)};
    border: 1px solid rgba(255, 255, 255, 0.08);
    font-family: ${theme.typography.fontFamilyMonospace};
    font-size: ${theme.typography.body.fontSize};
    font-weight: ${theme.typography.fontWeightMedium};
    line-height: 1.15;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  `,
  pairTag: css`
    display: inline-flex;
    align-items: stretch;
    max-width: 100%;
    border-radius: 5px;
    overflow: hidden;
    font-family: ${theme.typography.fontFamilyMonospace};
    font-size: ${theme.typography.body.fontSize};
    font-weight: ${theme.typography.fontWeightMedium};

    > span {
      min-width: 0;
      padding: ${theme.spacing(0.5)} ${theme.spacing(1.25)};
      border-top: 1px solid rgba(255, 255, 255, 0.08);
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
      line-height: 1.15;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    > span:first-child {
      border-left: 1px solid rgba(255, 255, 255, 0.08);
      border-right: 1px solid rgba(255, 255, 255, 0.1);
    }

    > span:last-child {
      border-right: 1px solid rgba(255, 255, 255, 0.08);
    }
  `,
  secondaryText: css`
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: ${theme.colors.text.secondary};
  `,
  switchCell: css`
    display: flex;
    align-items: center;
  `,
  switchField: css`
    margin-bottom: 0;
  `,
  countCell: css`
    color: ${theme.colors.text.secondary};
  `,
  rowMenu: css`
    display: flex;
    justify-content: flex-end;
  `,
  rowActions: css`
    display: flex;
    justify-content: flex-end;
    gap: ${theme.spacing(1)};

    @media (max-width: 900px) {
      flex-wrap: wrap;
    }
  `,
  menuColumn: css`
    width: 48px;
  `,
  loadingState: css`
    padding: ${theme.spacing(3)};
  `,
  emptyTableState: css`
    padding: ${theme.spacing(4)};
    text-align: center;
  `,
});
