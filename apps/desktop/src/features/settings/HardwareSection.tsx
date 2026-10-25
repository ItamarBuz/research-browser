import { useTranslation } from "react-i18next";

import type { GpuInfo, HardwareProfile } from "../../shared/api/engine";
import { formatBytes } from "../../shared/format";

const MB = 1024 ** 2;
const OS_NAMES: Record<string, string> = { Darwin: "macOS", Windows: "Windows", Linux: "Linux" };

function GpuLine({ gpu }: { gpu: GpuInfo }) {
  const { t, i18n } = useTranslation();
  const memory = gpu.unified_memory
    ? t("settings.hardware.gpuUnified")
    : formatBytes(gpu.memory_mb * MB, i18n.language);
  return (
    <li>
      <bdi>{gpu.name}</bdi> · {memory} · <bdi>{gpu.backend.toUpperCase()}</bdi>
    </li>
  );
}

export function HardwareSection({ hardware }: { hardware: HardwareProfile }) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;

  return (
    <section className="settings-section" aria-labelledby="hardware-heading">
      <h2 id="hardware-heading">{t("settings.hardware.title")}</h2>
      <dl className="facts">
        <dt>{t("settings.hardware.os")}</dt>
        <dd>
          <bdi>
            {OS_NAMES[hardware.os] ?? hardware.os} ({hardware.arch})
          </bdi>
        </dd>

        <dt>{t("settings.hardware.cpu")}</dt>
        <dd>
          {t("settings.hardware.cores", {
            physical: hardware.cpu_physical_cores,
            logical: hardware.cpu_logical_cores,
          })}
        </dd>

        <dt>{t("settings.hardware.memory")}</dt>
        <dd>
          {t("settings.hardware.memoryValue", {
            total: formatBytes(hardware.total_ram_mb * MB, lang),
            available: formatBytes(hardware.available_ram_mb * MB, lang),
          })}
        </dd>

        <dt>{t("settings.hardware.gpu")}</dt>
        <dd>
          {hardware.gpus.length === 0 ? (
            t("settings.hardware.noGpu")
          ) : (
            <ul className="plain-list">
              {hardware.gpus.map((gpu, index) => (
                <GpuLine key={`${gpu.name}-${String(index)}`} gpu={gpu} />
              ))}
            </ul>
          )}
        </dd>
      </dl>
    </section>
  );
}
