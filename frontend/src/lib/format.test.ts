import { describe, expect, it } from "vitest";
import {
  buildQuery,
  confidenceTone,
  formatDateFR,
  formatMoney,
  isLocked,
  isProcessing,
  parseAmount,
  statusLabel,
  truncate,
} from "./format";

describe("parseAmount", () => {
  it("accepte les formats français", () => {
    expect(parseAmount("1 234,50")).toBe(1234.5);
    expect(parseAmount("1\u00a0234,50")).toBe(1234.5);
    expect(parseAmount("19")).toBe(19);
    expect(parseAmount("12.5")).toBe(12.5);
  });

  it("rejette les valeurs non numériques", () => {
    expect(parseAmount("")).toBeNull();
    expect(parseAmount("abc")).toBeNull();
    expect(parseAmount("1.2.3")).toBeNull();
    expect(parseAmount("12,3,4")).toBeNull();
  });

  it("gère un nombre", () => {
    expect(parseAmount(42.25)).toBe(42.25);
    expect(parseAmount(Number.NaN)).toBeNull();
  });
});

describe("formatMoney", () => {
  it("affiche deux décimales et la devise", () => {
    const text = formatMoney(22569.54, "DZD");
    expect(text).toContain("569,54");
    expect(text).toContain("DA");
  });

  it("affiche un tiret pour une valeur absente", () => {
    expect(formatMoney(null)).toBe("—");
    expect(formatMoney("invalide")).toBe("—");
  });
});

describe("formatDateFR", () => {
  it("convertit une date ISO", () => {
    expect(formatDateFR("2026-10-24")).toBe("24/10/2026");
  });

  it("conserve une valeur inattendue", () => {
    expect(formatDateFR("octobre 2026")).toBe("octobre 2026");
    expect(formatDateFR(null)).toBe("—");
  });
});

describe("statuts et confiance", () => {
  it("traduit les statuts", () => {
    expect(statusLabel("A_VERIFIER")).toBe("À vérifier");
    expect(statusLabel("INCONNU")).toBe("INCONNU");
  });

  it("classe la confiance", () => {
    expect(confidenceTone(0.95)).toBe("high");
    expect(confidenceTone(0.7)).toBe("medium");
    expect(confidenceTone(0.2)).toBe("low");
    expect(confidenceTone(null)).toBe("none");
  });

  it("identifie les états de traitement", () => {
    expect(isProcessing("IMPORTEE")).toBe(true);
    expect(isProcessing("EXTRACTION")).toBe(true);
    expect(isProcessing("VALIDEE")).toBe(false);
    expect(isLocked("VALIDEE")).toBe(true);
    expect(isLocked("EXPORTEE")).toBe(true);
    expect(isLocked("A_VERIFIER")).toBe(false);
  });
});

describe("helpers", () => {
  it("construit une query string sans valeurs vides", () => {
    expect(buildQuery({ q: "test", page: 2, vide: null, absent: undefined })).toBe("?q=test&page=2");
    expect(buildQuery({})).toBe("");
  });

  it("tronque proprement", () => {
    expect(truncate("abcdef", 5)).toBe("abcd…");
    expect(truncate("abc", 5)).toBe("abc");
  });
});
