import { useState } from "react";

import { Select } from "@/components/ui/select";

interface SelectProps {
  selectedSetting: string;
  onSettingChange: (value: string) => void;
  onCustomPromptChange?: (value: string) => void;
  error?: string | null;
}

export const PromptSelect: React.FC<SelectProps> = ({ 
  onSettingChange,
  selectedSetting,
  onCustomPromptChange,
  error 
}) => {
  const [customPrompt, setCustomPrompt] = useState("");

  return (
    <div className="flex flex-col gap-2">
      <h3 className="text-sm font-bold">Choose a Scenario</h3>
      <Select
        onChange={(e) => {
          onSettingChange(e.target.value);
        }}
        value={selectedSetting || "default"}
        icon={null}
      >
        <option value="default">Select a Scenario</option>
        <option value="corporate">Impersonation of Executive</option>
        <option value="it_support">IT Support Scam</option>
        <option value="finance_fraud">Finance Fraud</option>
        <option value="engineering_breach">Engineering Breach</option>
        <option value="security_alert">Security Alert</option>
        <option value="custom">Create Your Own Custom Scenario</option>
      </Select>

      {selectedSetting === "custom" && (
        <div className="mt-2">
          <textarea
            placeholder="Write your custom scenario here..."
            value={customPrompt}
            onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => {
              setCustomPrompt(e.target.value);
              onCustomPromptChange?.(e.target.value);
            }}
            className="min-h-[100px] w-full rounded-md border border-primary-200 bg-transparent px-3 py-2 text-sm"
          />
          {error && (
            <p className="text-xs text-red-500 mt-1">{error}</p>
          )}
        </div>
      )}
    </div>
  );
};