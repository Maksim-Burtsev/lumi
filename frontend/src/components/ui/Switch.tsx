import { haptic } from '../../telegram/webapp';

interface SwitchProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  'aria-label'?: string;
}

export function Switch({ checked, onChange, disabled = false, 'aria-label': ariaLabel }: SwitchProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={ariaLabel}
      disabled={disabled}
      onClick={() => {
        haptic('light');
        onChange(!checked);
      }}
      className={`relative h-[28px] w-[48px] shrink-0 rounded-full p-[3px] transition-colors duration-200 after:absolute after:-inset-2 after:content-[''] disabled:opacity-50 ${
        checked ? 'bg-accent' : 'bg-[var(--switch-off)]'
      }`}
    >
      <span
        className={`block h-[22px] w-[22px] rounded-full bg-[var(--switch-knob)] shadow-[0_1px_3px_var(--switch-shadow)] transition-transform duration-200 ${
          checked ? 'translate-x-[20px]' : 'translate-x-0'
        }`}
      />
    </button>
  );
}
