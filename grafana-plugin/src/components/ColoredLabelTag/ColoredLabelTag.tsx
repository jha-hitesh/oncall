import React, { FC } from 'react';

import { css, cx } from '@emotion/css';
import { GrafanaTheme2 } from '@grafana/data';
import { useStyles2 } from '@grafana/ui';
import { getLabelCss } from 'styles/utils.styles';

import { ApiSchemas } from 'network/oncall-api/api.types';

type ColoredLabelPart = {
  name: string;
  color_code?: string;
};

type LabelWithOptionalColors = {
  key: ColoredLabelPart & { id: string };
  value: ColoredLabelPart & { id: string };
};

interface ColoredLabelTagProps {
  label: ColoredLabelPart;
  value: ColoredLabelPart;
  className?: string;
}

export const ColoredLabelTag: FC<ColoredLabelTagProps> = ({ label, value, className }) => {
  const styles = useStyles2(getStyles);

  return (
    <span className={cx(styles.root, className)}>
      <span className={cx(styles.part, styles.label, label.color_code && getHexLabelCss(label.color_code))}>
        {label.name}
      </span>
      <span className={cx(styles.part, styles.value, value.color_code && getHexLabelCss(value.color_code))}>
        {value.name}
      </span>
    </span>
  );
};

export const toColoredLabelParts = (label: ApiSchemas['LabelPair'] | LabelWithOptionalColors) => ({
  label: { name: label.key.name, color_code: (label.key as ColoredLabelPart).color_code },
  value: { name: label.value.name, color_code: (label.value as ColoredLabelPart).color_code },
});

const getHexLabelCss = (colorCode: string) => css`
  border: none;
  background-color: ${colorCode}40;
  color: #ffffff;
`;

const getStyles = (theme: GrafanaTheme2) => ({
  root: css`
    display: inline-flex;
    align-items: center;
    max-width: 100%;
  `,

  part: css`
    display: inline-block;
    max-width: 180px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    padding: 4px 8px;
    font-size: 12px;
    line-height: 16px;
  `,

  label: css`
    ${getLabelCss('blue', theme)};
    border-radius: 4px 0 0 4px;
  `,

  value: css`
    ${getLabelCss('purple', theme)};
    border-radius: 0 4px 4px 0;
  `,
});
