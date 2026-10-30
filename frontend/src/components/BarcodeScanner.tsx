import { useEffect, useRef, useState } from "react";
import { Html5Qrcode } from "html5-qrcode";
import { Icon } from "./Icon";
import { Modal } from "./Modal";

interface BarcodeScannerProps {
  isOpen: boolean;
  onClose: () => void;
  onScan: (barcode: string) => void;
}

export function BarcodeScanner({ isOpen, onClose, onScan }: BarcodeScannerProps) {
  const [isScanning, setIsScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scannerRef = useRef<Html5Qrcode | null>(null);
  const readerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) {
      stopScanning();
      return;
    }

    startScanning();

    return () => {
      stopScanning();
    };
  }, [isOpen]);

  const startScanning = async () => {
    if (!readerRef.current || isScanning) return;

    try {
      setError(null);
      setIsScanning(true);

      const scanner = new Html5Qrcode("barcode-reader");
      scannerRef.current = scanner;

      await scanner.start(
        { facingMode: "environment" },
        {
          fps: 10,
          qrbox: { width: 250, height: 250 },
          aspectRatio: 1.0,
        },
        (decodedText) => {
          onScan(decodedText);
          stopScanning();
          onClose();
        },
        () => {
          // Erreur de scan ignorée (scan continu)
        }
      );
    } catch (err) {
      console.error("Erreur de démarrage du scanner:", err);
      setError("Impossible d'accéder à la caméra. Vérifiez les permissions.");
      setIsScanning(false);
    }
  };

  const stopScanning = async () => {
    if (scannerRef.current && isScanning) {
      try {
        await scannerRef.current.stop();
        scannerRef.current.clear();
        scannerRef.current = null;
      } catch (err) {
        console.error("Erreur d'arrêt du scanner:", err);
      }
      setIsScanning(false);
    }
  };

  const handleClose = () => {
    stopScanning();
    onClose();
  };

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title="Scanner un code-barre">
      <div className="barcode-scanner-modal">
        <div className="scanner-instructions">
          <Icon name="search" size={20} />
          <p>Placez le code-barre dans le cadre pour le scanner automatiquement</p>
        </div>

        <div id="barcode-reader" ref={readerRef} className="barcode-reader" />

        {error && (
          <div className="scanner-error">
            <Icon name="alert" size={16} />
            <span>{error}</span>
          </div>
        )}

        <div className="scanner-actions">
          <button type="button" className="button button-secondary" onClick={handleClose}>
            Annuler
          </button>
        </div>
      </div>
    </Modal>
  );
}
