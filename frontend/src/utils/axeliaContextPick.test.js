import { describe, expect, it } from "vitest";
import {
  AXELIA_ACCOUNT_SCOPE_ALL,
  pickConversationRowForAccountContext,
  resolveInitialAxeliaAccountContext,
} from "./axeliaContextPick";

describe("pickConversationRowForAccountContext", () => {
  it("retourne la ligne dont account_context correspond au compte", () => {
    const rows = [
      { id: "a", account_context: AXELIA_ACCOUNT_SCOPE_ALL },
      { id: "b", account_context: "uuid-coop" },
    ];
    expect(pickConversationRowForAccountContext(rows, "uuid-coop")).toEqual(
      rows[1],
    );
    expect(pickConversationRowForAccountContext(rows, AXELIA_ACCOUNT_SCOPE_ALL)).toEqual(
      rows[0],
    );
  });

  it("ne retourne pas une ligne au mauvais contexte", () => {
    const rows = [{ id: "x", account_context: AXELIA_ACCOUNT_SCOPE_ALL }];
    expect(
      pickConversationRowForAccountContext(rows, "uuid-coop"),
    ).toBeNull();
  });

  it("traite account_context absent comme tous les comptes", () => {
    const rows = [{ id: "z" }];
    expect(
      pickConversationRowForAccountContext(rows, AXELIA_ACCOUNT_SCOPE_ALL)?.id,
    ).toBe("z");
  });
});

describe("resolveInitialAxeliaAccountContext", () => {
  const one = [{ id: "acc-1", name: "A" }];
  const two = [
    { id: "acc-1", name: "A" },
    { id: "acc-2", name: "B" },
  ];

  it("utilise initialAccountId lorsqu’il est dans la liste accessible", () => {
    expect(resolveInitialAxeliaAccountContext("acc-1", one)).toBe("acc-1");
  });

  it("avec une seule ligne accessible, utilise ce compte même sans initialAccountId", () => {
    expect(resolveInitialAxeliaAccountContext(null, one)).toBe("acc-1");
    expect(resolveInitialAxeliaAccountContext(undefined, one)).toBe("acc-1");
  });

  it("avec une seule ligne, ignore un initialAccountId inconnu et garde ce compte", () => {
    expect(resolveInitialAxeliaAccountContext("autre", one)).toBe("acc-1");
  });

  it("avec plusieurs lignes et sans initial valide, retombe sur tous les comptes", () => {
    expect(resolveInitialAxeliaAccountContext(null, two)).toBe(
      AXELIA_ACCOUNT_SCOPE_ALL,
    );
    expect(resolveInitialAxeliaAccountContext("inconnu", two)).toBe(
      AXELIA_ACCOUNT_SCOPE_ALL,
    );
  });
});
