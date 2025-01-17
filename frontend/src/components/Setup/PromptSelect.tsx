import { Select } from "@/components/ui/select";

interface SelectProps {
  selectedSetting: string;
  onSettingChange: (value: string) => void;
}

export const PromptSelect: React.FC<SelectProps> = ({ 
  onSettingChange,
  selectedSetting 
}) => {
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
      </Select>
    </div>
  );
};