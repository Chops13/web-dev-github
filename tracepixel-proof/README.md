# TracePixel — Conversion Tracking Proof

## Can you prove what actually fired after a conversion action?

TracePixel runs the real customer journey in a browser and observes the tracking behaviour that follows.

### Test

**Journey:** Ecommerce product page → Add to cart  
**Action:** Add to cart clicked successfully  
**Method:** Remote Chromium browser with runtime network inspection

### What TracePixel observed

GA4 was active on the page.

Before and during the journey, TracePixel captured live GA4 requests including:

- `page_view`
- `view_item`
- `scroll`

The product was then successfully added to the cart.

After that action:

**`add_to_cart` was not observed in the captured GA4 traffic.**

### What does that mean?

It does **not automatically mean the site's tracking is broken**.

TracePixel separates what can be proven from what can only be assumed.

If the measurement specification says:

**Expected:** GA4 `add_to_cart` fires after a successful cart addition

then the audit result would be:

**FAIL — Expected event not observed**

If `add_to_cart` is not an expected event, TracePixel simply reports:

**NOT OBSERVED**

### Why this matters

Seeing GA4 installed is not the same as proving conversion measurement works.

TracePixel tests the actual user action and records the resulting browser-level tracking evidence.

**Expected behaviour → real browser action → observed tracking → evidence-backed result**

No advertising-platform access is required for the initial browser-level audit.

---

**TracePixel**  
Know whether your conversion tracking actually works.
