import { describe, expect, it } from "vitest";
import { hasErrors, ListingForm, validateListing } from "./validation";

const ok: ListingForm = { title: "Veg biryani", food_category: "cooked_meal", storage_condition: "room", is_veg: true, quantity_meals: "40", cooked_minutes_ago: "30", expiry_at: "", pickup_address: "" };
const v = (o: Partial<ListingForm>) => validateListing({ ...ok, ...o });

describe("validateListing", () => {
  it("accepts a normal cooked-food listing", () => expect(hasErrors(v({}))).toBe(false));
  it("rejects short titles", () => expect(v({ title: "ab" }).title).toBeTruthy());
  it.each(["", "0", "-5", "2.5", "abc", "5001"])("rejects quantity %p", (q) => expect(v({ quantity_meals: q }).quantity_meals).toBeTruthy());
  it("accepts the quantity limits 1 and 5000", () => { expect(v({ quantity_meals: "1" }).quantity_meals).toBeUndefined(); expect(v({ quantity_meals: "5000" }).quantity_meals).toBeUndefined(); });
  it("does not allow cooked non-veg to be flagged veg", () => expect(v({ food_category: "nonveg_cooked", is_veg: true }).is_veg).toBeTruthy());
  it("requires an expiry for sealed food, and not a cooked time", () => {
    const s = { food_category: "sealed_packaged", storage_condition: "sealed_packaged", cooked_minutes_ago: "" };
    expect(v(s).expiry_at).toBeTruthy();
    expect(v({ ...s, expiry_at: "2026-12-01T10:00" })).toEqual({});
  });
  it("keeps sealed category and sealed storage consistent", () => {
    expect(v({ food_category: "sealed_packaged", storage_condition: "room", expiry_at: "2026-12-01T10:00" }).storage_condition).toBeTruthy();
    expect(v({ storage_condition: "sealed_packaged" }).storage_condition).toBeTruthy();
  });
  it("bounds the cooked-minutes field", () => {
    expect(v({ cooked_minutes_ago: "" }).cooked_minutes_ago).toBeTruthy();
    expect(v({ cooked_minutes_ago: "-1" }).cooked_minutes_ago).toBeTruthy();
    expect(v({ cooked_minutes_ago: "4321" }).cooked_minutes_ago).toBeTruthy();
    expect(v({ cooked_minutes_ago: "0" }).cooked_minutes_ago).toBeUndefined();
  });
});
