import { parseAmount } from "./format";

export type FieldState = "" | "error" | "ok";

/** Classe CSS correspondant à l'état de validation d'un champ. */
export function fieldClass(state: FieldState): string {
  return state === "error" ? "field-error" : state === "ok" ? "field-ok" : "";
}

/**
 * Champ texte obligatoire : bordure rouge si vide, verte si rempli.
 * Neutre en lecture seule.
 */
export function textFieldState(value: string, readOnly: boolean, required = true): FieldState {
  if (readOnly) return "";
  if (!required) return "";
  return value.trim() !== "" ? "ok" : "error";
}

/**
 * Champ numérique optionnel : bordure rouge si la saisie est invalide,
 * verte si c'est un nombre valide, neutre si vide.
 */
export function numberFieldState(value: string, readOnly: boolean): FieldState {
  if (readOnly) return "";
  if (value.trim() === "") return "";
  return parseAmount(value) === null ? "error" : "ok";
}
