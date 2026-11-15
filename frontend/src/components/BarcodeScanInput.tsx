import { useEffect, useRef, useState } from "react";
import { Icon } from "./Icon";

interface BarcodeScanInputProps {
  onScan: (barcode: string) => void | Promise<void>;
  busy?: boolean;
  autoFocus?: boolean;
  placeholder?: string;
  label?: string;
}

export function BarcodeScanInput({
  onScan,
  busy = false,
  autoFocus = true,
  placeholder = "Scannez le code-barres avec la douchette…",
  label = "Scanner un code-barres",
}: BarcodeScanInputProps) {
  const [value, setValue] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (autoFocus) inputRef.current?.focus();
  }, [autoFocus]);

  const submit = async () => {
    const barcode = (inputRef.current?.value ?? value).trim();
    if (!barcode || busy) return;
    setValue("");
    if (inputRef.current) inputRef.current.value = "";
    await onScan(barcode);
    inputRef.current?.focus();
  };

  return (
    <form
      className="search-row compact barcode-scan-row"
      onSubmit={(event) => {
        event.preventDefault();
        void submit();
      }}
    >
      <div className="search-input">
        <Icon name="barcode" size={18} />
        <input
          ref={inputRef}
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Tab") {
              event.preventDefault();
              void submit();
            }
          }}
          placeholder={placeholder}
          aria-label={label}
          autoComplete="off"
          disabled={busy}
        />
      </div>
      <button type="submit" className="button button-sm" disabled={busy || !value.trim()}>
        {busy ? <span className="spinner small" /> : <Icon name="barcode" size={15} />} Scanner
      </button>
    </form>
  );
}
