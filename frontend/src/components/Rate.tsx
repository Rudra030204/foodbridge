import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { api, ApiError } from "../api/client";
import { Notice } from "./ui";

/** Inline 1-5 star rating for one participant of a delivered pickup. */
export default function Rate({ pickupId, toUser, name }: { pickupId: number; toUser: number; name: string }) {
  const [stars, setStars] = useState(5);
  const [msg, setMsg] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const m = useMutation({
    mutationFn: () => api("/ratings", { method: "POST", body: { pickup_id: pickupId, to_user: toUser, stars } }),
    onSuccess: () => setMsg({ kind: "success", text: `Thanks, you rated ${name}.` }),
    onError: (e) => setMsg({ kind: "error", text: e instanceof ApiError ? e.message : "Could not save rating." }),
  });
  if (msg?.kind === "success") return <Notice kind="success">{msg.text}</Notice>;
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <span>Rate {name}:</span>
      <select aria-label={`Stars for ${name}`} className="input w-20 py-1" value={stars} onChange={(e) => setStars(Number(e.target.value))}>
        {[5, 4, 3, 2, 1].map((s) => <option key={s} value={s}>{s} ★</option>)}
      </select>
      <button className="btn-outline btn-sm" disabled={m.isPending} onClick={() => m.mutate()}>Submit</button>
      {msg && <span className="text-xs text-red-600">{msg.text}</span>}
    </div>
  );
}
