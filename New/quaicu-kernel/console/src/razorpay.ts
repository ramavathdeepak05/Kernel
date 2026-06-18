// Lazily load Razorpay Checkout (their hosted, PCI-compliant widget) — only when a payment is due.

export function loadRazorpayScript(): Promise<void> {
  return new Promise((resolve, reject) => {
    if ((window as unknown as { Razorpay?: unknown }).Razorpay) return resolve();
    const existing = document.getElementById("rzp-checkout-js");
    if (existing) {
      existing.addEventListener("load", () => resolve());
      existing.addEventListener("error", () => reject(new Error("load failed")));
      return;
    }
    const s = document.createElement("script");
    s.id = "rzp-checkout-js";
    s.src = "https://checkout.razorpay.com/v1/checkout.js";
    s.onload = () => resolve();
    s.onerror = () => reject(new Error("load failed"));
    document.body.appendChild(s);
  });
}

// Format paise → "₹10,000" (Indian grouping).
export const inr = (paise?: number) => `₹${Math.round((paise ?? 0) / 100).toLocaleString("en-IN")}`;
