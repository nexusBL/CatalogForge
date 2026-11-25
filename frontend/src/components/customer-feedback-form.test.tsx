import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { CustomerFeedbackForm } from "@/components/customer-feedback-form";

describe("customer feedback form", () => {
  it("requires written feedback and keeps photo optional", () => {
    const html = renderToStaticMarkup(
      <CustomerFeedbackForm catalogueId="cat_1" organizationId="org_1" restaurantName="Harbor Kitchen" />,
    );
    expect(html).toContain("Feedback for Harbor Kitchen");
    expect(html).toContain("Your feedback");
    expect(html).toContain("Photo (optional)");
    expect(html).toContain("required");
  });
});
