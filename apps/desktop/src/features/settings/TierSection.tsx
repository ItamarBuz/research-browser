import { useState } from "react";
import { useTranslation } from "react-i18next";

import type { Tier, TierDecision, TierReason } from "../../shared/api/engine";
import { formatGigabytes } from "../../shared/format";

const TIERS: readonly Tier[] = ["lite", "standard", "pro"];
const AUTO = "auto";
type Choice = Tier | typeof AUTO;

function ReasonText({ reason }: { reason: TierReason }) {
  const { t, i18n } = useTranslation();
  const value = reason.value_gb == null ? "" : formatGigabytes(reason.value_gb, i18n.language);
  return <li>{t(`settings.tier.reasons.${reason.code}`, { value })}</li>;
}

interface TierSectionProps {
  decision: TierDecision;
  onChange: (tier: Tier | null) => Promise<void>;
}

export function TierSection({ decision, onChange }: TierSectionProps) {
  const { t } = useTranslation();
  const [saving, setSaving] = useState(false);
  const lockedByEnv = decision.override_source === "env";
  const selected: Choice = decision.override_source === "user" ? decision.effective : AUTO;

  async function choose(choice: Choice) {
    setSaving(true);
    try {
      await onChange(choice === AUTO ? null : choice);
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="settings-section" aria-labelledby="tier-heading">
      <h2 id="tier-heading">{t("settings.tier.title")}</h2>

      <div className="tier-summary">
        <span className={`tier-badge tier-badge--${decision.effective}`}>
          {t(`settings.tier.names.${decision.effective}`)}
        </span>
        <p>{t(`settings.tier.descriptions.${decision.effective}`)}</p>
      </div>
      <ul className="plain-list muted">
        {decision.reasons.map((reason) => (
          <ReasonText key={reason.code} reason={reason} />
        ))}
      </ul>

      <fieldset className="tier-choice" disabled={lockedByEnv || saving}>
        <legend>{t("settings.tier.chooseLegend")}</legend>
        <label>
          <input
            type="radio"
            name="tier"
            value={AUTO}
            checked={selected === AUTO}
            onChange={() => void choose(AUTO)}
          />
          {t("settings.tier.automatic", {
            tier: t(`settings.tier.names.${decision.detected}`),
          })}
        </label>
        {TIERS.map((tier) => (
          <label key={tier}>
            <input
              type="radio"
              name="tier"
              value={tier}
              checked={selected === tier}
              onChange={() => void choose(tier)}
            />
            {t(`settings.tier.names.${tier}`)}
          </label>
        ))}
      </fieldset>
      {lockedByEnv && <p className="muted">{t("settings.tier.lockedByEnv")}</p>}
    </section>
  );
}
