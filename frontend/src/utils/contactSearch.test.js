import { describe, expect, it } from "vitest";
import { contactMatchesSearch, filterContactsBySearch, foldString } from "./contactSearch";

describe("foldString", () => {
  it("retire les accents et passe en minuscules", () => {
    expect(foldString("Élodie ÇA")).toBe("elodie ca");
  });

  it("renvoie une chaîne vide pour des valeurs falsy", () => {
    expect(foldString(null)).toBe("");
    expect(foldString(undefined)).toBe("");
    expect(foldString("")).toBe("");
  });
});

describe("contactMatchesSearch", () => {
  const contact = {
    display_name: "Jean-Luc Picard",
    whatsapp_name: "Jean Picard",
    whatsapp_number: "+33612345678",
  };

  it("matche par nom, insensible à la casse et aux accents", () => {
    expect(contactMatchesSearch(contact, "picard")).toBe(true);
    expect(contactMatchesSearch(contact, "PICARD")).toBe(true);
    expect(contactMatchesSearch(contact, "jean luc")).toBe(true);
  });

  it("matche par fragment de numéro", () => {
    expect(contactMatchesSearch(contact, "612345")).toBe(true);
    expect(contactMatchesSearch(contact, "678")).toBe(true);
  });

  it("ne matche pas une recherche inconnue", () => {
    expect(contactMatchesSearch(contact, "bonjourxyz")).toBe(false);
  });

  it("renvoie true sur recherche vide", () => {
    expect(contactMatchesSearch(contact, "")).toBe(true);
    expect(contactMatchesSearch(contact, "   ")).toBe(true);
  });
});

describe("filterContactsBySearch", () => {
  const contacts = [
    { display_name: "Alice Martin", whatsapp_number: "+33611111111" },
    { display_name: "Bob Dupont", whatsapp_number: "+33622222222" },
  ];

  it("filtre la liste correctement", () => {
    expect(filterContactsBySearch(contacts, "alice")).toHaveLength(1);
    expect(filterContactsBySearch(contacts, "33622")).toHaveLength(1);
    expect(filterContactsBySearch(contacts, "")).toHaveLength(2);
  });
});
