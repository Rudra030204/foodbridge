/** Pure client-side validation for the "Post surplus" form (the server re-validates everything). */
export interface ListingForm {
  title: string; food_category: string; storage_condition: string; is_veg: boolean; quantity_meals: string;
  cooked_minutes_ago: string; expiry_at: string; pickup_address: string;
}
export type FormErrors = Partial<Record<keyof ListingForm, string>>;

export function validateListing(f: ListingForm): FormErrors {
  const e: FormErrors = {};
  if (f.title.trim().length < 3) e.title = "Give the food a short name (at least 3 characters).";
  const q = Number(f.quantity_meals);
  if (!f.quantity_meals.trim() || !Number.isInteger(q) || q < 1 || q > 5000) e.quantity_meals = "Enter a whole number of meals between 1 and 5000.";
  const sealed = f.food_category === "sealed_packaged";
  if (sealed && f.storage_condition !== "sealed_packaged") e.storage_condition = "Sealed packaged food must use the 'Sealed package' storage.";
  if (!sealed && f.storage_condition === "sealed_packaged") e.storage_condition = "Choose how the food is stored.";
  if (f.food_category === "nonveg_cooked" && f.is_veg) e.is_veg = "Cooked non-veg food cannot be marked veg.";
  if (sealed && !f.expiry_at) e.expiry_at = "Enter the printed expiry date and time.";
  if (!sealed) {
    const m = Number(f.cooked_minutes_ago);
    if (f.cooked_minutes_ago.trim() === "" || !Number.isFinite(m) || m < 0 || m > 72 * 60) e.cooked_minutes_ago = "Minutes since cooking (0 to 4320).";
  }
  return e;
}

export const hasErrors = (e: FormErrors): boolean => Object.keys(e).length > 0;
