import type { CapabilityLanguage } from "../lib/types";

interface LanguageMultiSelectProps {
  languages: CapabilityLanguage[];
  selected: string[];
  onChange: (codes: string[]) => void;
}

export function LanguageMultiSelect({ languages, selected, onChange }: LanguageMultiSelectProps) {
  const toggle = (code: string, disabled: boolean) => {
    if (disabled) return;
    onChange(selected.includes(code) ? selected.filter((c) => c !== code) : [...selected, code]);
  };

  return (
    <div className="grid grid-cols-2 gap-2">
      {languages.map((lang) => {
        const isSelected = selected.includes(lang.code);
        const disabled = !lang.tts_available;
        return (
          <button
            key={lang.code}
            type="button"
            disabled={disabled}
            onClick={() => toggle(lang.code, disabled)}
            className="flex items-center justify-between rounded-md px-3 py-2 text-left text-label transition-colors"
            style={{
              border: `1px solid ${isSelected ? "var(--accent)" : "var(--border-strong)"}`,
              background: isSelected ? "var(--bg-hover)" : "var(--bg-panel)",
              opacity: disabled ? 0.5 : 1,
              cursor: disabled ? "not-allowed" : "pointer",
            }}
          >
            <span>{lang.display_name}</span>
            {disabled && (
              <span className="text-meta" style={{ color: "var(--text-muted)" }}>
                translate only
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
