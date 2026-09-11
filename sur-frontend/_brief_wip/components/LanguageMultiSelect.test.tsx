import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { LanguageMultiSelect } from "./LanguageMultiSelect";
import type { CapabilityLanguage } from "../lib/types";

const NARROW: CapabilityLanguage[] = [
  { code: "hi", display_name: "Hindi", flores_code: "hin_Deva", tts_available: true },
  { code: "te", display_name: "Telugu", flores_code: "tel_Telu", tts_available: true },
  { code: "kok", display_name: "Konkani", flores_code: "gom_Deva", tts_available: false },
];

describe("LanguageMultiSelect (production component)", () => {
  it("renders only the languages it was given, and nothing else", () => {
    render(<LanguageMultiSelect languages={NARROW} selected={[]} onChange={vi.fn()} />);

    for (const lang of NARROW) {
      expect(screen.getByText(lang.display_name)).toBeInTheDocument();
    }
    // The exact regression: a hardcoded language list must not leak in even
    // though this component was never told about these codes.
    for (const name of ["Tamil", "Kannada", "Malayalam", "Bengali", "Marathi", "Gujarati", "Punjabi", "Odia", "Assamese", "Urdu"]) {
      expect(screen.queryByText(name)).toBeNull();
    }
  });

  it("disables a translate-only language and cannot be toggled into selection", () => {
    const onChange = vi.fn();
    render(<LanguageMultiSelect languages={NARROW} selected={[]} onChange={onChange} />);

    const konkani = screen.getByRole("button", { name: /Konkani/ });
    expect(konkani).toBeDisabled();
    expect(screen.getByText("translate only")).toBeInTheDocument();

    konkani.click();
    expect(onChange).not.toHaveBeenCalled();
  });
});
